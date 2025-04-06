# -*- coding: utf-8 -*-
import os
import json
import re
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from google.api_core import exceptions as google_api_exceptions
from flask import current_app # Для логирования

# Конфигурация Gemini (остается без изменений)
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Ошибка: API ключ Gemini не найден в .env файле.")
        # current_app еще может быть недоступен здесь, используем print
    else:
        genai.configure(api_key=api_key)
        print("Gemini API ключ успешно сконфигурирован.")
except Exception as e:
    print(f"Критическая ошибка при конфигурации Gemini API: {e}")

# --- НОВАЯ ФУНКЦИЯ: Этап 0 - Первичная оценка ---
def get_initial_assessment(query: str, column_names: list[str], completeness_info: str) -> dict | None:
    """
    Этап 0: Запрашивает у LLM первичную оценку запроса, выбор релевантных столбцов
            и уточняющие вопросы пользователю.

    Args:
        query (str): Исходный запрос пользователя.
        column_names (list[str]): Список имен столбцов.
        completeness_info (str): Строка с информацией о % пропусков.

    Returns:
        dict | None: Словарь с результатом LLM или None/словарь с ошибкой.
           Ожидаемый формат успешного ответа:
           {
               "suggested_columns": ["Список", "столбцов", "которые", "LLM", "считает", "релевантными"],
               "questions_to_user": ["Список", "уточняющих", "вопросов", "если", "нужны"]
           }
           В случае ошибки: {"error": "Сообщение об ошибке"}
    """
    if not os.getenv("GEMINI_API_KEY"):
        current_app.logger.error("Ошибка LLM: Попытка вызова LLM без API ключа.")
        return {"error": "API ключ Gemini не сконфигурирован."}

    model_name = 'gemini-1.5-flash' # Или 'gemini-1.5-pro-latest' если Flash не справляется
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        current_app.logger.error(f"Ошибка инициализации модели Gemini ('{model_name}'): {e}")
        return {"error": f"Ошибка инициализации модели Gemini ('{model_name}'): {e}"}

    prompt = f"""
Ты - ИИ-ассистент для хирурга-онколога. Помогаешь подготовить данные для стат. анализа.
Задача: Проанализируй данные и запрос пользователя, предложи релевантные столбцы и задай уточняющие вопросы.

Доступные столбцы в данных:
{column_names}

Информация о пропущенных значениях:
{completeness_info}

Запрос пользователя:
"{query}"

Твои действия:
1.  Внимательно прочитай запрос пользователя. Выдели ключевые понятия, которые нужно измерить или сравнить (например, 'возраст', 'тип лечения', 'осложнения').
2.  Проанализируй список доступных столбцов. Определи, какие из них **наиболее вероятно** соответствуют ключевым понятиям из запроса. Учитывай синонимы и возможные неточные названия ('пол' может быть 'sex', 'осложнения' могут быть 'comp_dindo'). Обрати внимание на столбцы с большим процентом пропусков - они менее предпочтительны.
3.  Если запрос неясен, или есть несколько столбцов, подходящих под одно понятие, или ты не уверен в выборе - сформулируй **четкие и краткие** уточняющие вопросы пользователю.
4.  Сформируй ответ СТРОГО в формате JSON. JSON должен содержать два ключа:
    *   `"suggested_columns"`: Список (list) **строк** с названиями столбцов, которые ты считаешь наиболее релевантными для анализа по данному запросу. Включи только те, что есть в списке доступных столбцов.
    *   `"questions_to_user"`: Список (list) **строк** с уточняющими вопросами к пользователю. Если вопросов нет, передай пустой список `[]`.

Пример JSON ответа:
{{
  "suggested_columns": ["Возраст", "Группа_исследования", "Осложнения_ClavinDindo"],
  "questions_to_user": ["Правильно ли я понял, что под 'эффективностью лечения' вы подразумеваете столбец 'Ответ_на_терапию'?", "Какой столбец использовать для группировки по 'типу операции': 'Тип_ОП_код' или 'Тип_ОП_текст'?"]
}}

ВАЖНО: Верни ТОЛЬКО JSON объект, без markdown (```json), без пояснений до или после.

Твой JSON ответ:
"""

    generation_config = GenerationConfig(
        temperature=0.2, # Чуть больше креативности для вопросов
        response_mime_type="application/json"
    )

    try:
        current_app.logger.info(f"LLM Этап 0: Запрос к {model_name}...")
        response = model.generate_content(prompt, generation_config=generation_config)

        if not response.parts:
             block_reason = response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else "Неизвестно"
             current_app.logger.error(f"LLM Этап 0: Ответ не содержит частей. Блокировка: {block_reason}. Feedback: {response.prompt_feedback}")
             return {"error": f"Запрос заблокирован Gemini: {block_reason}"}

        raw_response_text = response.text
        current_app.logger.info(f"LLM Этап 0: Получен сырой ответ:\n{raw_response_text}")

        # Прямой парсинг JSON
        result = json.loads(raw_response_text)

        # Проверка формата ответа
        if not isinstance(result, dict) or "suggested_columns" not in result or "questions_to_user" not in result:
             current_app.logger.error(f"LLM Этап 0: Ответ не соответствует ожидаемому формату JSON. Ответ: {result}")
             return {"error": "LLM вернула ответ в некорректном формате.", "raw_response": raw_response_text}
        if not isinstance(result["suggested_columns"], list) or not isinstance(result["questions_to_user"], list):
             current_app.logger.error(f"LLM Этап 0: Ключи 'suggested_columns' или 'questions_to_user' не являются списками. Ответ: {result}")
             return {"error": "LLM вернула некорректные типы данных в JSON.", "raw_response": raw_response_text}

        current_app.logger.info("LLM Этап 0: Ответ успешно распарсен.")
        return result

    except json.JSONDecodeError as e:
        current_app.logger.error(f"LLM Этап 0: Ошибка декодирования JSON: {e}. Ответ: {raw_response_text}")
        # Можно добавить попытку ручной очистки, но с application/json это менее вероятно
        return {"error": f"Ошибка парсинга JSON ответа LLM: {e}", "raw_response": raw_response_text}
    except (google_api_exceptions.GoogleAPIError, google_api_exceptions.RetryError) as e:
        current_app.logger.error(f"LLM Этап 0: Ошибка Google API или сети: {e}")
        return {"error": f"Ошибка API Google Gemini или сети: {e}"}
    except ValueError as ve: # Обработка случая, если response_mime_type не сработал
        current_app.logger.warning(f"LLM Этап 0: ValueError (возможно, response_mime_type не поддерживается): {ve}. Пробуем без него.")
        # Сюда можно добавить логику повторной попытки без mime_type,
        # аналогично той, что была в вашей исходной функции get_analysis_plan_gemini
        # Для краткости пока возвращаем ошибку
        return {"error": f"Ошибка конфигурации запроса к Gemini: {ve}. Попробуйте другую модель или удалите response_mime_type."}
    except Exception as e:
        current_app.logger.error(f"LLM Этап 0: Неожиданная ошибка: {e}", exc_info=True) # Логируем traceback
        return {"error": f"Неожиданная ошибка API Gemini: {e}"}
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---


# --- НОВАЯ ФУНКЦИЯ: Этап 1 - Генерация детального плана ---
def get_detailed_plan_proposal(query: str, confirmed_columns: list[str], clarifications: str | None) -> list | dict | None:
    """
    Этап 1: Запрашивает у LLM детальный пошаговый план анализа на основе
            подтвержденных столбцов и уточнений пользователя.

    Args:
        query (str): Исходный запрос пользователя.
        confirmed_columns (list[str]): Список столбцов, подтвержденных пользователем.
        clarifications (str | None): Ответы пользователя на уточняющие вопросы LLM (или None).

    Returns:
        list | dict | None: Список словарей с шагами плана,
                            словарь с ошибкой от LLM (analysis_type='error'),
                            или None/словарь с ошибкой API/парсинга.
    """
    if not os.getenv("GEMINI_API_KEY"):
        current_app.logger.error("Ошибка LLM: Попытка вызова LLM без API ключа.")
        return {"error": "API ключ Gemini не сконфигурирован."}

    model_name = 'gemini-1.5-flash' # Или 'gemini-1.5-pro-latest'
    try:
        model = genai.GenerativeModel(model_name)
    except Exception as e:
        current_app.logger.error(f"Ошибка инициализации модели Gemini ('{model_name}'): {e}")
        return {"error": f"Ошибка инициализации модели Gemini ('{model_name}'): {e}"}

    clarifications_prompt_part = ""
    if clarifications and clarifications.strip():
        clarifications_prompt_part = f"\nОтветы пользователя на уточняющие вопросы:\n\"{clarifications}\"\n"

    prompt = f"""
Ты - ИИ-ассистент для хирурга-онколога. Твоя задача - составить детальный план статистического анализа.

Исходный запрос пользователя:
"{query}"

Столбцы, которые пользователь подтвердил для использования в анализе:
{confirmed_columns}
{clarifications_prompt_part}
Твои действия:
1.  Используя ТОЛЬКО подтвержденные столбцы, сопоставь их с частями исходного запроса.
2.  Для каждой части запроса, которую можно выполнить с помощью подтвержденных столбцов, определи конкретный статистический тест и переменные.
3.  Поддерживаемые тесты: 't-test' (сравнение числовой переменной 'variable' между 2 группами 'grouping_variable'), 'chi-square' (связь двух категориальных 'variable1', 'variable2'), 'descriptive_stats' (описательные статистики для 'variable').
4.  Если какая-то часть запроса НЕ МОЖЕТ быть выполнена с подтвержденными столбцами (например, нет нужного столбца), создай шаг с `analysis_type: "error"` и четким описанием проблемы в поле `message`.
5.  Сгенерируй ответ СТРОГО в формате JSON **списка** ([...]) словарей. Каждый словарь - это один шаг анализа или сообщение об ошибке.
6.  Каждый словарь должен содержать ключ 'analysis_type' и другие необходимые ключи в зависимости от типа ('variable', 'grouping_variable', 'variable1', 'variable2', 'message').

Пример JSON ответа (список словарей):
[
  {{
    "analysis_type": "t-test",
    "variable": "Возраст",
    "grouping_variable": "Группа_исследования"
  }},
  {{
    "analysis_type": "chi-square",
    "variable1": "Осложнения_ClavinDindo",
    "variable2": "Группа_исследования"
  }},
  {{
    "analysis_type": "error",
    "message": "Не найден подтвержденный столбец для анализа показателя 'Выживаемость'."
  }}
]

ВАЖНО: Верни ТОЛЬКО JSON список, без markdown (```json), без пояснений до или после.

Твой JSON ответ (список):
"""

    generation_config = GenerationConfig(
        temperature=0.1, # Низкая температура для строгости
        response_mime_type="application/json"
    )

    try:
        current_app.logger.info(f"LLM Этап 1: Запрос к {model_name}...")
        response = model.generate_content(prompt, generation_config=generation_config)

        if not response.parts:
             block_reason = response.prompt_feedback.block_reason.name if response.prompt_feedback.block_reason else "Неизвестно"
             current_app.logger.error(f"LLM Этап 1: Ответ не содержит частей. Блокировка: {block_reason}. Feedback: {response.prompt_feedback}")
             # Возвращаем ошибку в формате словаря, а не списка
             return {"error": f"Запрос заблокирован Gemini: {block_reason}"}

        raw_response_text = response.text
        current_app.logger.info(f"LLM Этап 1: Получен сырой ответ:\n{raw_response_text}")

        # Прямой парсинг JSON (ожидаем список)
        analysis_plan_list = json.loads(raw_response_text)

        # Проверка формата ответа (должен быть список словарей)
        if not isinstance(analysis_plan_list, list):
            current_app.logger.error(f"LLM Этап 1: Ответ не является списком JSON. Ответ: {analysis_plan_list}")
            # Возвращаем ошибку в формате словаря
            return {"error": "LLM вернула ответ не в формате списка.", "raw_response": raw_response_text}
        # Дополнительная проверка, что элементы списка - словари (можно добавить)
        # for item in analysis_plan_list:
        #    if not isinstance(item, dict): ...

        current_app.logger.info("LLM Этап 1: Ответ успешно распарсен.")
        return analysis_plan_list # Возвращаем СПИСОК

    # Обработка ошибок аналогична предыдущей функции
    except json.JSONDecodeError as e:
        current_app.logger.error(f"LLM Этап 1: Ошибка декодирования JSON: {e}. Ответ: {raw_response_text}")
        return {"error": f"Ошибка парсинга JSON ответа LLM: {e}", "raw_response": raw_response_text}
    except (google_api_exceptions.GoogleAPIError, google_api_exceptions.RetryError) as e:
        current_app.logger.error(f"LLM Этап 1: Ошибка Google API или сети: {e}")
        return {"error": f"Ошибка API Google Gemini или сети: {e}"}
    except ValueError as ve:
        current_app.logger.warning(f"LLM Этап 1: ValueError: {ve}. Пробуем без mime_type.")
        # Здесь тоже можно добавить повторную попытку
        return {"error": f"Ошибка конфигурации запроса к Gemini: {ve}."}
    except Exception as e:
        current_app.logger.error(f"LLM Этап 1: Неожиданная ошибка: {e}", exc_info=True)
        return {"error": f"Неожиданная ошибка API Gemini: {e}"}

# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---

# Старая функция get_analysis_plan_gemini БОЛЬШЕ НЕ НУЖНА для новой логики,
# но можно ее пока оставить или закомментировать, если нужна для отладки/сравнения.
# def get_analysis_plan_gemini(query: str, column_names: list[str]) -> dict | None:
#     ... (старый код) ...
