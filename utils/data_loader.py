# -*- coding: utf-8 -*-
import pandas as pd
import os
from werkzeug.utils import secure_filename
# !!! Убираем импорт current_app и flash на уровне модуля, если он не нужен в глобальной области !!!
# Оставляем только если он нужен ВНУТРИ функций
from flask import current_app, flash

# !!! УБРАТЬ ПРОВЕРКУ ПАПКИ НА УРОВНЕ МОДУЛЯ !!!
# # Проблемный код удален:
# upload_folder_on_load = current_app.config.get('UPLOAD_FOLDER', 'uploads') if current_app else 'uploads'
# if not os.path.exists(upload_folder_on_load):
#     try:
#         os.makedirs(upload_folder_on_load)
#     except OSError as e:
#          print(f"Предупреждение: Не удалось создать папку {upload_folder_on_load} при загрузке модуля: {e}")
# !!! КОНЕЦ УДАЛЕНИЯ !!!


def save_uploaded_file(uploaded_file):
    """Сохраняет загруженный файл локально и возвращает путь."""
    if uploaded_file and uploaded_file.filename != '':
        filename = secure_filename(uploaded_file.filename)
        try:
            # Получаем папку из config ВНУТРИ функции, когда current_app доступен
            upload_folder = current_app.config['UPLOAD_FOLDER']
            # Проверка и создание папки лучше оставить в app.py,
            # но можно добавить запасную проверку здесь, если очень нужно
            if not os.path.exists(upload_folder):
                try:
                    os.makedirs(upload_folder)
                    current_app.logger.warning(f"Папка {upload_folder} создана функцией save_uploaded_file.")
                except OSError as e:
                    flash(f"Критическая ошибка: Не удалось создать папку для загрузок '{upload_folder}': {e}", "danger")
                    current_app.logger.error(f"Ошибка создания папки '{upload_folder}' в save_uploaded_file: {e}")
                    return None

            filepath = os.path.join(upload_folder, filename)
            uploaded_file.save(filepath)
            current_app.logger.info(f"Файл '{filename}' сохранен как '{filepath}'")
            return filepath
        except KeyError:
             flash("Ошибка конфигурации: UPLOAD_FOLDER не задан.", "danger")
             current_app.logger.error("UPLOAD_FOLDER не найден в app.config")
             return None
        except Exception as e:
            flash(f"Ошибка сохранения файла '{filename}': {e}", "danger")
            current_app.logger.error(f"Ошибка сохранения файла '{filename}': {e}", exc_info=True)
            return None
    return None

def load_data_from_path(filepath: str) -> pd.DataFrame | None:
    """
    Загружает данные из Excel файла по указанному пути.
    (Использует header=0, skiprows=[1] как в последней удачной версии)
    """
    if not filepath or not os.path.exists(filepath):
        flash(f"Ошибка: Файл '{os.path.basename(filepath)}' не найден для загрузки данных.", "danger")
        current_app.logger.error(f"Ошибка load_data_from_path: Файл не найден '{filepath}'")
        return None
    try:
        # Читаем заголовок из ПЕРВОЙ строки (индекс 0)
        # Пропускаем ВТОРУЮ строку (индекс 1) с описаниями
        df = pd.read_excel(filepath, engine='openpyxl', header=0, skiprows=[1])

        current_app.logger.info(f"Файл '{os.path.basename(filepath)}' прочитан (header=0, skiprows=[1]).")

        # Очистка имен столбцов
        original_columns = df.columns.tolist()
        df.columns = df.columns.str.strip()
        cleaned_columns = df.columns.tolist()
        if original_columns != cleaned_columns:
             current_app.logger.info(f"Очищенные заголовки: {cleaned_columns}")
        else:
             current_app.logger.info(f"Заголовки столбцов: {cleaned_columns}")

        # Логирование для проверки
        # current_app.logger.info(f"--- DEBUG: Первые 2 строки DataFrame ПОСЛЕ пропуска строки описаний:\n{df.head(2).to_string()}")

        # Проверки df.empty
        if df.empty and not df.columns.empty:
             flash(f"Предупреждение: Файл '{os.path.basename(filepath)}' содержит заголовки, но не содержит данных (или все данные были в пропущенной строке).", "warning")
             current_app.logger.warning(f"Файл '{os.path.basename(filepath)}' пуст после skiprows.")
        elif df.empty:
             flash(f"Ошибка: Не удалось прочитать данные из файла '{os.path.basename(filepath)}'.", "danger")
             current_app.logger.error(f"Файл '{os.path.basename(filepath)}' пуст или не удалось прочитать.")
             return None

        return df
    except Exception as e:
        flash(f"Ошибка при чтении данных из файла '{os.path.basename(filepath)}': {e}", "danger")
        current_app.logger.error(f"Ошибка чтения Excel '{filepath}': {e}", exc_info=True)
        return None

def cleanup_file(filepath: str):
    """Удаляет файл по указанному пути, если он существует."""
    # Здесь current_app не используется, можно оставить как есть
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
            # Используем logger, если доступен, иначе print
            logger = current_app.logger if current_app else logging.getLogger(__name__)
            logger.info(f"Файл '{filepath}' удален.")
        except Exception as e:
            logger = current_app.logger if current_app else logging.getLogger(__name__)
            logger.error(f"Не удалось удалить файл '{filepath}': {e}")
    elif filepath:
         logger = current_app.logger if current_app else logging.getLogger(__name__)
         logger.warning(f"Попытка удалить файл '{filepath}', но он не существует.")


def get_data_completeness_report(df: pd.DataFrame) -> dict | None:
    """
    Рассчитывает отчет о полноте данных (пропущенных значениях) в DataFrame.
    (Код этой функции остается без изменений, как в предыдущем ответе,
     но импорт plot_utils лучше сделать наверху файла)
    """
    # Добавим импорт здесь, если он не был наверху
    try:
        from .plot_utils import dataframe_to_html
    except ImportError:
        # Обработка на случай, если .plot_utils не найден
        current_app.logger.error("Не удалось импортировать dataframe_to_html из .plot_utils")
        def dataframe_to_html(df_in): # Заглушка
            return "<p>Ошибка: функция dataframe_to_html не найдена.</p>"

    # Логгер для использования внутри функции
    logger = current_app.logger if current_app else logging.getLogger(__name__)

    if df is None or df.empty:
        if df is not None and not df.columns.empty:
              report_df = pd.DataFrame({ 'Столбец': df.columns, 'Кол-во пропусков': 0, '% пропусков': 0.0 })
              missing_info_str = "Данные отсутствуют."
              html_table = "<p class='text-info'>Файл не содержит строк данных.</p>"
              return { 'report_df': report_df, 'html_table': html_table, 'missing_info_str': missing_info_str }
        else:
             logger.warning("DataFrame пуст или None, отчет о полноте не создан.")
             return None

    try:
        missing_values = df.isnull().sum()
        if len(df) == 0:
             missing_percentage = pd.Series([0.0] * len(df.columns), index=df.columns)
        else:
            missing_percentage = (missing_values / len(df)) * 100

        report_df = pd.DataFrame({
            'Столбец': df.columns,
            'Кол-во пропусков': missing_values,
            '% пропусков': missing_percentage
        }).sort_values(by='% пропусков', ascending=False)

        # --- Отбор строк для LLM ---
        missing_info_for_llm = report_df[report_df['% пропусков'] > 0]
        if not missing_info_for_llm.empty:
             missing_info_filtered_llm = missing_info_for_llm[missing_info_for_llm['% пропусков'] < 100.0]
             if not missing_info_filtered_llm.empty:
                 missing_info_str = ". ".join([f"Столбец '{rec['Столбец']}' имеет {rec['% пропусков']:.1f}% пропусков"
                                            for rec in missing_info_filtered_llm.to_dict('records')]) + "."
             else:
                 missing_info_str = "Все столбцы либо не имеют пропусков, либо пропуски составляют 100%."
        elif len(df) == 0:
            missing_info_str = "Данные отсутствуют."
        else:
             missing_info_str = "Пропущенные значения во всех столбцах отсутствуют."

        # --- Создание DataFrame для ОТОБРАЖЕНИЯ (HTML) ---
        report_df_display = report_df.copy()
        report_df_display['% пропусков'] = report_df_display['% пропусков'].round(2)
        report_df_display_filtered = report_df_display[report_df_display['% пропусков'] < 100.0]

        if not report_df_display_filtered.empty:
            html_table = dataframe_to_html(report_df_display_filtered.set_index('Столбец'))
        else:
            html_table = "<p class='text-info'>Все столбцы имеют 100% пропусков или пропуски отсутствуют.</p>"

        return {
            'report_df': report_df,
            'html_table': html_table,
            'missing_info_str': missing_info_str
        }
    except Exception as e:
        logger.error(f"Ошибка при расчете отчета о полноте данных: {e}", exc_info=True)
        # Используем flash только если current_app доступен (т.е. вызывается из контекста запроса)
        if current_app:
            flash(f"Ошибка при расчете полноты данных: {e}", "warning")
        return None
