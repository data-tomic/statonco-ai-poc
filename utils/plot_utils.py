import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import io
import base64

plt.switch_backend('Agg') # Используем бэкенд, не требующий GUI

def dataframe_to_html(df):
    """Конвертирует DataFrame в HTML таблицу с базовыми стилями."""
    if df is None:
        return ""
    # Добавляем классы для возможного CSS-стилирования
    return df.to_html(classes=['table', 'table-striped', 'table-bordered', 'table-hover', 'dataframe'], index=True, border=0)


def plot_to_base64(fig):
    """Конвертирует фигуру Matplotlib в строку Base64."""
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight')
    plt.close(fig) # Закрываем фигуру, чтобы освободить память
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    buf.close()
    return f"data:image/png;base64,{img_base64}"

def plot_histogram(series: pd.Series, title: str) -> str | None:
    """Строит гистограмму и возвращает ее в Base64."""
    if not pd.api.types.is_numeric_dtype(series):
        print("Гистограмма строится только для числовых данных.")
        return None
    if series.dropna().empty:
        print("Нет данных для построения гистограммы.")
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.histplot(series.dropna(), kde=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel(series.name)
    ax.set_ylabel('Частота')
    fig.tight_layout()
    return plot_to_base64(fig)

def plot_boxplot(df: pd.DataFrame, variable_col: str, group_col: str, title: str) -> str | None:
    """Строит boxplot для сравнения групп и возвращает Base64."""
    if not pd.api.types.is_numeric_dtype(df[variable_col]):
         print("Box plot строится только для числовых данных.")
         return None
    if df[variable_col].dropna().empty or df[group_col].dropna().empty:
         print("Нет данных для построения box plot.")
         return None

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.boxplot(x=df[group_col], y=df[variable_col], ax=ax, palette="Set2")
    ax.set_title(title)
    ax.set_xlabel(group_col)
    ax.set_ylabel(variable_col)
    fig.tight_layout()
    return plot_to_base64(fig)

def plot_countplot(series: pd.Series, title: str) -> str | None:
    """Строит столбчатую диаграмму частот и возвращает Base64."""
    if series.dropna().empty:
        print("Нет данных для построения count plot.")
        return None

    fig, ax = plt.subplots(figsize=(10, 6)) # Увеличим размер для возможных длинных меток
    order = series.value_counts().index # Сортируем по убыванию частоты
    sns.countplot(y=series, ax=ax, order=order, palette="viridis") # Горизонтальная для лучшей читаемости меток
    ax.set_title(title)
    ax.set_xlabel('Количество')
    ax.set_ylabel(series.name)

    # Добавим значения на бары
    for container in ax.containers:
        ax.bar_label(container)

    fig.tight_layout()
    return plot_to_base64(fig)

def plot_contingency_table(cont_table: pd.DataFrame, title: str) -> str | None:
    """Строит тепловую карту или столбчатую диаграмму для таблицы сопряженности."""
    if cont_table.empty:
        print("Нет данных для построения графика таблицы сопряженности.")
        return None

    # Вариант 1: Тепловая карта
    # fig, ax = plt.subplots(figsize=(8, 6))
    # sns.heatmap(cont_table, annot=True, fmt="d", cmap="Blues", ax=ax)
    # ax.set_title(title)
    # fig.tight_layout()

    # Вариант 2: Сгруппированная столбчатая диаграмма (может быть нагляднее)
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        cont_table.plot(kind='bar', ax=ax, rot=0) # rot=0 для горизонтальных меток оси X
        ax.set_title(title)
        ax.set_ylabel('Частота')
        ax.legend(title=cont_table.columns.name) # Имя колонки как заголовок легенды
        fig.tight_layout()
        return plot_to_base64(fig)
    except Exception as e:
        print(f"Ошибка при построении графика для таблицы сопряженности: {e}")
        # Может возникнуть, если данные не подходят для bar plot
        # Возвращаем None или пробуем heatmap как запасной вариант
        return None
