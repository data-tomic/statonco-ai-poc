# StatOnco PoC - Interactive Data Analysis Assistant

A prototype web application designed to assist pediatric oncology surgeons in obtaining statistical information from Excel file data. The application utilizes Google Gemini to interpret natural language queries and generate an analysis plan, which is then confirmed by the user before execution.

## Core Features

*   Upload data from Excel files (.xlsx).
*   Interactive multi-step analysis workflow with user involvement:
    *   **Step 0:** Upload, initial data completeness check, LLM suggestions for relevant columns, and clarifying questions.
    *   **Step 1:** User confirmation of columns, answers to questions, LLM generation of a detailed analysis plan.
    *   **Step 2:** User confirmation of the plan and execution of statistical calculations.
*   Statistical Analysis (Implemented):
    *   Independent Samples T-test (Welch's).
    *   Chi-square Test of Independence (with low frequency warning).
    *   Descriptive Statistics calculation.
*   Filtering of columns with 100% missing values from the UI and LLM input.
*   Basic visualization of results (histograms, boxplots, contingency tables).
*   Integration with Google Gemini (Flash/Pro) for query processing and planning.
*   Web interface built with Flask and Bootstrap.

## Technology Stack

*   Python 3.11+
*   Flask
*   Pandas
*   Google Generative AI (google-generativeai)
*   SciPy
*   Matplotlib / Seaborn (for plotting)
*   python-dotenv
*   openpyxl
*   Werkzeug, Jinja2, itsdangerous, click (Flask dependencies)

## Installation and Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd statonco-poc
    ```
2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure environment variables:**
    *   Create a file named `.env` in the project's root directory.
    *   Add the following lines, replacing the placeholder values with your actual credentials:
        ```dotenv
        GEMINI_API_KEY=YOUR_GEMINI_API_KEY
        FLASK_SECRET_KEY=YOUR_VERY_STRONG_RANDOM_SECRET_KEY # Generate a strong random key!
        # FLASK_DEBUG=True # Uncomment for Flask debug mode
        ```
    *   **Important:** `FLASK_SECRET_KEY` is crucial for session management. Use a strong, randomly generated key.

5.  **Run the application:**
    ```bash
    flask run
    ```
6.  Open your web browser and navigate to `http://127.0.0.1:5000` (or the address provided in the terminal output).

## Current Status and Known Issues

This application is a **Proof of Concept (PoC)**. The core interactive workflow is implemented but requires further refinement and testing.

**Known Issues (See GitHub Issues for details):**

1.  **Data Validation Errors Before Analysis:** T-tests frequently fail validation due to:
    *   Incorrect values in the grouping column (more than 2 unique values found, presence of text/garbage values).
    *   Non-numeric data types detected in columns intended for numerical analysis (e.g., 'weight (kg)').
    *   **Needed:** Improved input data cleaning/preprocessing or stricter type validation and conversion before executing tests.
2.  **Chi-square Test Warning:** The Chi-square test issues a warning (`min_expected_freq < 5`) when expected cell frequencies are low, indicating potential inaccuracy of the p-value.
    *   **Needed:** Consider implementing Fisher's Exact Test as an alternative for small samples/frequencies, or provide options for category merging.
3.  **LLM Handling of Queries/Columns:** The LLM might not always correctly identify the intended columns or may skip analysis steps if it doesn't find a precise match in the user-confirmed columns.
    *   **Needed:** Potential prompt engineering improvements, perhaps incorporating few-shot examples.
4.  **Inefficiency:** Reloading the DataFrame when navigating back during the column confirmation step (if no columns are selected) is inefficient.
5.  **UI/UX:** The user interface is basic. Error reporting and step visualization can be improved. There's currently no way to edit the LLM-proposed analysis plan.

## Future Development

*   Implement more robust data cleaning and validation routines.
*   Add Fisher's Exact Test as an alternative or default for appropriate Chi-square scenarios.
*   Enhance LLM prompts for better column mapping and plan generation.
*   Optimize data loading and handling between steps.
*   Improve UI/UX, including clearer error displays and potentially allowing users to edit the analysis plan.
*   Incorporate additional statistical tests (e.g., ANOVA, correlation analysis).
*   Prepare for deployment using a production-ready WSGI server (like Gunicorn or Waitress) and potentially a reverse proxy (like Nginx).
