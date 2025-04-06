import pandas as pd
from scipy import stats
import numpy as np
from .plot_utils import (
    plot_histogram,
    plot_boxplot,
    plot_countplot,
    plot_contingency_table,
    dataframe_to_html
)

def format_p_value(p_value):
    """Форматирует p-value для вывода."""
    if p_value < 0.001:
        return "< 0.001"
    else:
        return f"{p_value:.3f}" # Округляем до 3 знаков

def get_descriptive_stats(df: pd.DataFrame, variable_col: str) -> dict | None:
    """
    Рассчитывает описательные статистики и генерирует график.
    Возвращает словарь с результатами и данными графика (base64).
    """
    if variable_col not in df.columns:
        return {"error": f"Столбец '{variable_col}' не найден в данных."}

    column_data = df[variable_col].dropna()

    if column_data.empty:
        return {"warning": f"Столбец '{variable_col}' не содержит данных после удаления пропусков."}

    results = {"column": variable_col, "plot_data": None, "table_html": None}
    plot_title = f"Распределение переменной '{variable_col}'"

    if pd.api.types.is_numeric_dtype(column_data):
        stats_data = {
            "Тип": "Числовой",
            "Количество валидных": int(column_data.count()),
            "Среднее": f"{column_data.mean():.2f}",
            "Стандартное отклонение": f"{column_data.std():.2f}",
            "Минимум": f"{column_data.min():.2f}",
            "25% Квантиль": f"{column_data.quantile(0.25):.2f}",
            "Медиана (50%)": f"{column_data.median():.2f}",
            "75% Квантиль": f"{column_data.quantile(0.75):.2f}",
            "Максимум": f"{column_data.max():.2f}",
        }
        results["stats"] = stats_data
        results["plot_data"] = plot_histogram(column_data, title=plot_title)
        results["table_html"] = dataframe_to_html(pd.Series(stats_data, name="Статистика"))

    else: # Категориальная/текстовая
        value_counts = column_data.value_counts()
        frequencies = (value_counts / column_data.count() * 100)
        stats_df = pd.DataFrame({
            'Количество': value_counts,
            'Процент': frequencies.map('{:.2f}%'.format) # Форматируем проценты
        })
        stats_data = {
            "Тип": "Категориальный/Текстовый",
            "Количество валидных": int(column_data.count()),
            "Уникальных значений": int(column_data.nunique()),
        }
        results["stats"] = stats_data
        results["table_html"] = dataframe_to_html(stats_df)
        results["plot_data"] = plot_countplot(column_data, title=plot_title)

    return results


def perform_t_test(df: pd.DataFrame, variable_col: str, group_col: str) -> dict | None:
    """
    Выполняет t-тест, генерирует график.
    Возвращает словарь с результатами и данными графика (base64).
    """
    if variable_col not in df.columns:
        return {"error": f"Числовой столбец '{variable_col}' не найден."}
    if group_col not in df.columns:
        return {"error": f"Группирующий столбец '{group_col}' не найден."}

    if not pd.api.types.is_numeric_dtype(df[variable_col]):
         return {"error": f"Столбец '{variable_col}' должен быть числовым для t-теста."}

    groups = df[group_col].dropna().unique()
    if len(groups) != 2:
        return {"error": f"Группирующий столбец '{group_col}' должен содержать ровно 2 группы (обнаружено {len(groups)}: {groups})."}

    group1_data = df[df[group_col] == groups[0]][variable_col].dropna()
    group2_data = df[df[group_col] == groups[1]][variable_col].dropna()

    if group1_data.empty or group2_data.empty:
         return {"warning": f"Одна из групп для t-теста пуста после удаления пропусков в '{variable_col}'."}

    try:
        t_stat, p_value = stats.ttest_ind(group1_data, group2_data, equal_var=False) # Welch's t-test

        results = {
            "test_type": "t-тест для независимых выборок (Уэлча)",
            "variable": variable_col,
            "grouping_variable": group_col,
            "groups": list(groups),
            "stats": {},
            "metrics": {},
            "plot_data": None,
            "interpretation": ""
        }

        group1_stats = {
            "Группа": groups[0],
            "N": len(group1_data),
            "Среднее": f"{group1_data.mean():.2f}",
            "Стд.откл.": f"{group1_data.std():.2f}"
        }
        group2_stats = {
             "Группа": groups[1],
            "N": len(group2_data),
            "Среднее": f"{group2_data.mean():.2f}",
            "Стд.откл.": f"{group2_data.std():.2f}"
        }
        results["stats"]["group1"] = group1_stats
        results["stats"]["group2"] = group2_stats

        results["metrics"] = {
            "t-статистика": f"{t_stat:.3f}",
            "p-value": format_p_value(p_value)
        }

        if p_value < 0.05:
            results["interpretation"] = f"Обнаружены статистически значимые различия в '{variable_col}' между группами '{groups[0]}' и '{groups[1]}' (p={format_p_value(p_value)})."
            results["significance"] = True
        else:
            results["interpretation"] = f"Статистически значимых различий в '{variable_col}' между группами '{groups[0]}' и '{groups[1]}' не обнаружено (p={format_p_value(p_value)})."
            results["significance"] = False

        plot_title = f"Сравнение '{variable_col}' по группам '{group_col}'"
        results["plot_data"] = plot_boxplot(df, variable_col, group_col, title=plot_title)

        # Добавим HTML таблицу для описательных статистик по группам
        stats_df = pd.DataFrame([group1_stats, group2_stats]).set_index("Группа")
        results["table_html"] = dataframe_to_html(stats_df)

        return results

    except Exception as e:
        print(f"Ошибка при выполнении t-теста: {e}")
        return {"error": f"Ошибка при выполнении t-теста: {e}"}


def perform_chi_square(df: pd.DataFrame, var1_col: str, var2_col: str) -> dict | None:
    """
    Выполняет тест хи-квадрат, генерирует график таблицы сопряженности.
    Возвращает словарь с результатами и данными графика (base64).
    """
    if var1_col not in df.columns:
        return {"error": f"Столбец '{var1_col}' не найден."}
    if var2_col not in df.columns:
        return {"error": f"Столбец '{var2_col}' не найден."}
    if var1_col == var2_col:
         return {"error": "Для теста хи-квадрат нужны два разных столбца."}

    try:
        contingency_table = pd.crosstab(df[var1_col], df[var2_col])

        if contingency_table.empty or contingency_table.sum().sum() == 0 :
             return {"warning": f"Таблица сопряженности для '{var1_col}' и '{var2_col}' пуста или содержит только нули."}


        chi2, p, dof, expected = stats.chi2_contingency(contingency_table)

        min_expected_freq = expected.min()
        warning_message = ""
        if min_expected_freq < 5:
            warning_message = f"Предупреждение: Минимальная ожидаемая частота ({min_expected_freq:.2f}) < 5. Результаты хи-квадрат могут быть неточными."

        results = {
            "test_type": "Тест Хи-квадрат Пирсона",
            "variable1": var1_col,
            "variable2": var2_col,
            "metrics": {},
            "interpretation": "",
            "warning": warning_message if warning_message else None,
            "table_html": dataframe_to_html(contingency_table), # HTML таблицы сопряженности
            "plot_data": None
        }

        results["metrics"] = {
            "Хи-квадрат": f"{chi2:.3f}",
            "Степени свободы (dof)": dof,
            "p-value": format_p_value(p)
        }

        if p < 0.05:
             results["interpretation"] = f"Обнаружена статистически значимая связь между '{var1_col}' и '{var2_col}' (p={format_p_value(p)})."
             results["significance"] = True
        else:
             results["interpretation"] = f"Статистически значимая связь между '{var1_col}' и '{var2_col}' не обнаружена (p={format_p_value(p)})."
             results["significance"] = False

        plot_title = f"Связь между '{var1_col}' и '{var2_col}'"
        results["plot_data"] = plot_contingency_table(contingency_table, title=plot_title)

        return results

    except ValueError as ve:
         print(f"Ошибка при расчете хи-квадрат (возможно, из-за нулевых строк/столбцов): {ve}")
         # Возвращаем таблицу, чтобы показать проблему
         cont_table_html = dataframe_to_html(contingency_table) if 'contingency_table' in locals() else "<p>Не удалось создать таблицу сопряженности.</p>"
         return {"error": f"Ошибка расчета хи-квадрат: {ve}", "table_html": cont_table_html}
    except Exception as e:
        print(f"Ошибка при выполнении теста хи-квадрат: {e}")
        return {"error": f"Ошибка при выполнении теста хи-квадрат: {e}"}
