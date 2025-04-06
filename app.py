# -*- coding: utf-8 -*-
import os
import json
import traceback # Import traceback for better error logging
import pandas as pd # Импортируем pandas для проверки типа
# Добавляем session и logging
from flask import Flask, request, render_template, flash, redirect, url_for, jsonify, session
from dotenv import load_dotenv
import logging # Импортируем стандартный логгер

# Загружаем переменные окружения (API ключ и секретный ключ)
load_dotenv()

# Импортируем утилиты
# Добавляем get_data_completeness_report
from utils.data_loader import save_uploaded_file, load_data_from_path, cleanup_file, get_data_completeness_report
# Используем НОВЫЕ функции для Gemini
from utils.llm_handler import get_initial_assessment, get_detailed_plan_proposal #, summarize_results (опционально)
from utils.stats_processor import get_descriptive_stats, perform_t_test, perform_chi_square
# dataframe_to_html импортируется внутри get_data_completeness_report и stats_processor теперь

# --- Настройка Flask ---
app = Flask(__name__)
# !!! ВАЖНО: Устанавливаем секретный ключ для сессий !!!
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your-very-secret-key-please-change-it') # Замените на надежный ключ
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB Max Upload Size

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO) # Устанавливаем уровень для логгера Flask

# Создаем папку для загрузок, если ее нет
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'])
        app.logger.info(f"Создана папка для загрузок: {app.config['UPLOAD_FOLDER']}")
    except OSError as e:
        app.logger.critical(f"Не удалось создать папку для загрузок '{app.config['UPLOAD_FOLDER']}': {e}")
        # Можно здесь завершить приложение, если папка критична

# --- Маршруты ---

@app.route('/', methods=['GET'])
def index():
    """Отображает главную страницу и очищает сессию от предыдущего анализа."""
    keys_to_clear = ['filepath', 'original_query', 'column_names_original', 'columns_to_display',
                     'completeness_html', 'missing_info_str', 'llm_suggestions',
                     'confirmed_columns', 'user_clarifications', 'proposed_plan',
                     'final_results']
    for key in keys_to_clear:
        session.pop(key, None)
    app.logger.info("Сессия очищена для нового анализа.")
    return render_template('index.html')

@app.route('/analyze/start', methods=['POST'])
def start_analysis():
    """
    Этап 0: Принимает файл и запрос, проводит первичный анализ,
           запрашивает у LLM оценку и вопросы, рендерит страницу подтверждения.
    """
    uploaded_filepath = None
    try:
        # 1. Проверка файла и запроса
        if 'file' not in request.files: flash('Файл не был загружен.', 'warning'); return redirect(url_for('index'))
        file = request.files['file']
        query = request.form.get('query', '').strip()
        if file.filename == '': flash('Не выбран файл для загрузки.', 'warning'); return redirect(url_for('index'))
        if not query: flash('Необходимо ввести запрос для анализа.', 'warning'); return redirect(url_for('index'))

        # 2. Сохранение и загрузка данных
        uploaded_filepath = save_uploaded_file(file)
        if not uploaded_filepath: return redirect(url_for('index'))
        df = load_data_from_path(uploaded_filepath) # Должен использовать header=0, skiprows=[1]
        if df is None: cleanup_file(uploaded_filepath); return redirect(url_for('index'))

        column_names_original = df.columns.tolist()
        if not column_names_original:
             flash(f'В файле "{file.filename}" не найдено заголовков столбцов или файл пуст.', 'danger')
             cleanup_file(uploaded_filepath); return redirect(url_for('index'))
        session['column_names_original'] = column_names_original

        # 3. Анализ полноты данных
        completeness_report = get_data_completeness_report(df)

        # 4. Извлечение данных И ФИЛЬТРАЦИЯ СТОЛБЦОВ
        completeness_html_for_template = "<p class='text-warning'>Не удалось рассчитать отчет о полноте.</p>"
        missing_info_str_for_llm = "Не удалось получить информацию о пропусках."
        report_df_full = None
        columns_to_display = column_names_original[:]
        report_df_filtered_for_template = None

        if completeness_report:
             completeness_html_for_template = completeness_report.get('html_table', completeness_html_for_template)
             missing_info_str_for_llm = completeness_report.get('missing_info_str', missing_info_str_for_llm)
             report_df_full = completeness_report.get('report_df')

             if report_df_full is not None:
                 app.logger.info(f"Полный отчет о полноте данных:\n{report_df_full.to_string()}")
                 report_df_filtered = report_df_full[report_df_full['% пропусков'] < 100.0]
                 if not report_df_filtered.empty:
                    columns_to_display = report_df_filtered['Столбец'].tolist()
                    report_df_filtered_for_template = report_df_filtered
                 else:
                    app.logger.warning("Внимание: Все столбцы имеют 100% пропусков.")
                    columns_to_display = []
                    report_df_filtered_for_template = pd.DataFrame(columns=['Столбец', 'Кол-во пропусков', '% пропусков'])
                 app.logger.info(f"Столбцы для отображения и LLM ({len(columns_to_display)}): {columns_to_display}")
             else:
                 app.logger.warning("Отчет о полноте не содержит DataFrame.")
        else:
             app.logger.warning("Не удалось создать отчет о полноте данных.")

        if not columns_to_display and completeness_report: # Показываем предупреждение только если отчет был, но все отфильтровалось
             flash("Внимание: Все столбцы в файле имеют 100% пропусков или не удалось прочитать данные.", "warning")

        # 5. Сохранение в сессию
        session['filepath'] = uploaded_filepath
        session['original_query'] = query
        session['columns_to_display'] = columns_to_display
        session['completeness_html'] = completeness_html_for_template
        session['missing_info_str'] = missing_info_str_for_llm

        # 6. Запрос к LLM
        llm_suggestions = get_initial_assessment(query, columns_to_display, missing_info_str_for_llm)

        if not llm_suggestions:
             flash("Не удалось связаться с LLM. Попробуйте позже.", "danger")
             cleanup_file(uploaded_filepath); session.clear(); return redirect(url_for('index'))
        elif llm_suggestions.get("error"):
             flash(f"Ошибка LLM: {llm_suggestions['error']}", "warning")

        session['llm_suggestions'] = llm_suggestions

        # 7. Рендеринг страницы подтверждения
        return render_template('confirm_columns.html',
                               original_query=query,
                               completeness_html=completeness_html_for_template,
                               report_df=report_df_filtered_for_template,
                               llm_suggestions=llm_suggestions,
                               all_columns=columns_to_display)

    except Exception as e:
        error_traceback = traceback.format_exc()
        app.logger.error(f"Критическая ошибка в /analyze/start: {e}\n{error_traceback}")
        flash(f'Произошла внутренняя ошибка сервера на этапе 0: {e}', 'danger')
        cleanup_file(uploaded_filepath or session.get('filepath'))
        session.clear()
        return redirect(url_for('index'))

@app.route('/analyze/confirm_columns', methods=['POST'])
def confirm_columns():
    """
    Этап 1: Принимает подтвержденные столбцы и уточнения,
           запрашивает у LLM детальный план, рендерит страницу подтверждения плана.
    """
    try:
        # 1. Получение данных из сессии и формы
        original_query = session.get('original_query')
        columns_to_display = session.get('columns_to_display')
        filepath = session.get('filepath')
        completeness_html = session.get('completeness_html')
        llm_suggestions_prev = session.get('llm_suggestions')

        if not all([original_query, isinstance(columns_to_display, list), filepath]):
            flash("Ошибка сессии: Не найдены данные предыдущего шага. Начните анализ заново.", "danger")
            app.logger.warning("Ошибка сессии в confirm_columns, не хватает данных или неверный тип.")
            return redirect(url_for('index'))

        confirmed_columns = request.form.getlist('confirmed_columns')
        user_clarifications = request.form.get('clarifications', '').strip()

        if not confirmed_columns:
            flash("Необходимо выбрать хотя бы один столбец для анализа.", "warning")
            df_for_rerender = load_data_from_path(filepath)
            report_for_rerender = get_data_completeness_report(df_for_rerender) if df_for_rerender is not None else None
            report_df_filtered_rerender = None
            if report_for_rerender and report_for_rerender.get('report_df') is not None:
                report_df_full_rerender = report_for_rerender['report_df']
                report_df_filtered_rerender = report_df_full_rerender[report_df_full_rerender['% пропусков'] < 100.0]

            return render_template('confirm_columns.html',
                                    original_query=original_query,
                                    completeness_html=completeness_html,
                                    report_df=report_df_filtered_rerender,
                                    llm_suggestions=llm_suggestions_prev,
                                    all_columns=columns_to_display,
                                    user_clarifications_input=user_clarifications)

        app.logger.info(f"Подтвержденные столбцы: {confirmed_columns}")
        app.logger.info(f"Уточнения пользователя: {user_clarifications if user_clarifications else 'Нет'}")

        # 2. Сохранение в сессию
        session['confirmed_columns'] = confirmed_columns
        session['user_clarifications'] = user_clarifications

        # 3. Запрос к LLM для получения детального плана
        proposed_plan = get_detailed_plan_proposal(original_query, confirmed_columns, user_clarifications)

        if isinstance(proposed_plan, dict) and proposed_plan.get('error'):
            flash(f"Ошибка LLM при генерации плана: {proposed_plan['error']}", "warning")
        elif not isinstance(proposed_plan, list):
             flash("LLM вернула план в неожиданном формате.", "danger")
             app.logger.error(f"Неожиданный формат плана от LLM: {type(proposed_plan)}, План: {proposed_plan}")
             proposed_plan = {"error": "Неожиданный формат ответа LLM."}

        session['proposed_plan'] = proposed_plan

        # 4. Рендеринг страницы подтверждения плана
        return render_template('confirm_plan.html', proposed_plan=proposed_plan)

    except Exception as e:
        error_traceback = traceback.format_exc()
        app.logger.error(f"Критическая ошибка в /analyze/confirm_columns: {e}\n{error_traceback}")
        flash(f'Произошла внутренняя ошибка сервера на этапе 1: {e}', 'danger')
        cleanup_file(session.get('filepath'))
        session.clear()
        return redirect(url_for('index'))


@app.route('/analyze/execute_plan', methods=['POST'])
def execute_plan():
    """
    Этап 2: Выполняет подтвержденный план анализа, рендерит страницу с результатами.
    """
    final_results = []
    filepath = session.get('filepath')
    proposed_plan = session.get('proposed_plan')

    try:
        if not filepath or not proposed_plan:
            flash("Ошибка сессии: Не найдены данные для выполнения анализа. Начните заново.", "danger")
            app.logger.warning("Ошибка сессии в execute_plan: нет filepath или proposed_plan.")
            return redirect(url_for('index'))

        if not isinstance(proposed_plan, list):
             flash(f"Ошибка: Невозможно выполнить анализ, так как план недействителен.", "danger")
             app.logger.error(f"Попытка выполнить недействительный план: {proposed_plan}")
             return render_template('confirm_plan.html', proposed_plan=proposed_plan)

        df = load_data_from_path(filepath)
        if df is None:
            session.clear()
            return redirect(url_for('index'))

        app.logger.info(f"Начало выполнения {len(proposed_plan)} шагов анализа для файла {filepath}...")
        for step in proposed_plan:
            step_result = {"plan": step, "status": "pending"}
            try:
                if not isinstance(step, dict):
                    step_result["status"] = "error"
                    step_result["message"] = f"Ошибка формата: шаг плана не словарь ({type(step)})."
                    app.logger.warning(f"Пропуск шага: {step_result['message']}")
                    # ---> ИСПРАВЛЕНИЕ ОТСТУПА ЗДЕСЬ <---
                    final_results.append(step_result)
                    continue # ---> Добавил continue здесь, чтобы не выполнять блок ниже

                analysis_type = step.get("analysis_type")
                if not analysis_type:
                    step_result["status"] = "error"
                    step_result["message"] = "Тип анализа не указан в шаге."
                    app.logger.warning(f"Пропуск шага: {step_result['message']}")
                    # ---> ИСПРАВЛЕНИЕ ОТСТУПА ЗДЕСЬ <---
                    final_results.append(step_result)
                    continue # ---> Добавил continue

                app.logger.info(f"Выполнение шага: {analysis_type}")


                # --- Логика выполнения ---
                if analysis_type == "error":
                     step_result["status"] = "skipped"
                     step_result["message"] = step.get("message", "Шаг с ошибкой из плана LLM.")
                     flash(f"Пропущен шаг плана (ошибка LLM): {step_result['message']}", "info")

                elif analysis_type == "t-test":
                    variable = step.get("variable")
                    grouping_variable = step.get("grouping_variable")
                    if variable and grouping_variable:
                        error_msg = None
                        if variable not in df.columns: error_msg = f"Столбец '{variable}' не найден."
                        elif grouping_variable not in df.columns: error_msg = f"Столбец '{grouping_variable}' не найден."
                        elif not pd.api.types.is_numeric_dtype(df[variable]): error_msg = f"Столбец '{variable}' не числовой."
                        elif df[grouping_variable].nunique() != 2:
                             groups = df[grouping_variable].dropna().unique()
                             error_msg = f"Столбец '{grouping_variable}' должен иметь 2 группы (найдено {len(groups)}: {list(groups)})."

                        if error_msg:
                            step_result["status"] = "error"
                            step_result["message"] = error_msg
                            flash(f"Ошибка T-test (валидация): {error_msg}", "danger")
                        else:
                             result_data = perform_t_test(df, variable, grouping_variable)
                             step_result["data"] = result_data
                             step_result["status"] = "error" if result_data.get("error") else "success"
                             if result_data.get("warning"): flash(f"Предупреждение T-test ({variable} по {grouping_variable}): {result_data['warning']}", "warning")
                             if result_data.get("error"): flash(f"Ошибка T-test ({variable} по {grouping_variable}): {result_data['error']}", "danger")
                    else:
                         step_result["status"] = "error"; step_result["message"] = "Не указаны 'variable' или 'grouping_variable' для t-теста."
                         flash(f"Ошибка конфигурации t-теста: {step_result['message']}", "warning")

                elif analysis_type == "chi-square":
                    variable1 = step.get("variable1")
                    variable2 = step.get("variable2")
                    if variable1 and variable2:
                        error_msg = None
                        if variable1 not in df.columns: error_msg = f"Столбец '{variable1}' не найден."
                        elif variable2 not in df.columns: error_msg = f"Столбец '{variable2}' не найден."
                        elif variable1 == variable2: error_msg = "Нужны два разных столбца."

                        if error_msg:
                             step_result["status"] = "error"; step_result["message"] = error_msg
                             flash(f"Ошибка Chi-square (валидация): {error_msg}", "danger")
                        else:
                            result_data = perform_chi_square(df, variable1, variable2)
                            step_result["data"] = result_data
                            step_result["status"] = "error" if result_data.get("error") else "success"
                            if result_data.get("warning"): flash(f"Предупреждение Chi-Square ({variable1} vs {variable2}): {result_data['warning']}", "warning")
                            if result_data.get("error"): flash(f"Ошибка Chi-Square ({variable1} vs {variable2}): {result_data['error']}", "danger")
                    else:
                         step_result["status"] = "error"; step_result["message"] = "Не указаны 'variable1' или 'variable2' для хи-квадрат."
                         flash(f"Ошибка конфигурации хи-квадрат: {step_result['message']}", "warning")

                elif analysis_type == "descriptive_stats":
                    variable = step.get("variable")
                    if variable:
                        if variable not in df.columns:
                             step_result["status"] = "error"; step_result["message"] = f"Столбец '{variable}' не найден."
                             flash(f"Ошибка опис. стат. (валидация): {step_result['message']}", "danger")
                        else:
                             result_data = get_descriptive_stats(df, variable)
                             step_result["data"] = result_data
                             step_result["status"] = "error" if result_data.get("error") else "success"
                             if result_data.get("warning"): flash(f"Предупреждение опис. стат. ({variable}): {result_data['warning']}", "warning")
                             if result_data.get("error"): flash(f"Ошибка опис. стат. ({variable}): {result_data['error']}", "danger")
                    else:
                        step_result["status"] = "error"; step_result["message"] = "Не указана 'variable' для описательных статистик."
                        flash(f"Ошибка конфигурации опис. стат.: {step_result['message']}", "warning")

                else:
                    step_result["status"] = "skipped"
                    step_result["message"] = f"Неизвестный тип анализа '{analysis_type}' в плане."
                    flash(f"Пропущен шаг: Неизвестный тип анализа '{analysis_type}'", "info")
                    app.logger.warning(f"Пропущен шаг с неизвестным типом анализа: {analysis_type}")

            # --- Блок except для ошибок выполнения шага ---
            except Exception as step_e:
                 error_traceback_step = traceback.format_exc()
                 app.logger.error(f"Ошибка при выполнении шага {step}: {step_e}\n{error_traceback_step}")
                 step_result["status"] = "error"
                 step_result["message"] = f"Внутренняя ошибка сервера при выполнении шага: {step_e}"
                 flash(f"Ошибка при выполнении шага ({step.get('analysis_type', 'N/A')}): {step_e}", "danger")

            # ---> ИСПРАВЛЕНИЕ ОТСТУПА ЗДЕСЬ <---
            # Эта строка должна выполняться ПОСЛЕ try/except, но ВНУТРИ цикла for
            final_results.append(step_result)
        # --- Конец цикла обработки шагов ---

        # ... (остальная часть функции execute_plan без изменений: подсчет результатов, flash, рендеринг) ...
        num_steps = len(proposed_plan)
        num_success = sum(1 for r in final_results if r.get("status") == "success")
        num_errors = sum(1 for r in final_results if r.get("status") == "error")
        num_skipped = sum(1 for r in final_results if r.get("status") == "skipped")

        summary_message = f"Анализ завершен. Всего шагов в плане: {num_steps}. Успешно: {num_success}."
        if num_errors > 0: summary_message += f" С ошибками: {num_errors}."
        if num_skipped > 0: summary_message += f" Пропущено: {num_skipped}."

        flash_category = "success" if num_errors == 0 and num_skipped == 0 else ("warning" if num_errors > 0 else "info")
        flash(summary_message, flash_category)
        app.logger.info(summary_message)

        session['final_results'] = final_results
        return render_template('results.html', analysis_results=final_results)

    except Exception as e:
        # Общая ошибка на этапе выполнения
        error_traceback = traceback.format_exc()
        app.logger.error(f"Критическая ошибка в /analyze/execute_plan: {e}\n{error_traceback}")
        flash(f'Произошла внутренняя ошибка сервера на этапе выполнения анализа: {e}', 'danger')
        return redirect(url_for('index'))

    finally:
        # Окончательная очистка файла
        final_filepath = session.pop('filepath', filepath)
        if final_filepath:
            cleanup_file(final_filepath)
        else:
            app.logger.warning("Не найден путь к файлу для очистки в finally execute_plan.")


if __name__ == '__main__':
    # Рекомендуется установить debug=False для production
    app.run(debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true',
            host=os.getenv('FLASK_HOST', '127.0.0.1'),
            port=int(os.getenv('FLASK_PORT', 5000)))
