# Project Overview

This project is a Flask web application called "Offer Search App". Its main purpose is to scrape product offers from Amazon and Mercado Livre, allowing users to search for products, view and compare offers, approve products, and schedule recurring searches. The application uses a Supabase database to store user data, search history, approved products, and scheduled searches.

## Main Technologies

*   **Backend:** Flask, Python
*   **Database:** Supabase (PostgreSQL)
*   **Web Scraping:** Selenium, BeautifulSoup, Requests, SerpApi (for Google Search results)
*   **Data Processing:** Pandas, NumPy
*   **Frontend:** HTML, CSS, JavaScript (structure inferred from `templates` and `static` folders)
*   **Environment Management:** python-dotenv

## Architecture

The application is structured into several modules:

*   **`app.py`:** The main entry point of the application. It initializes the Flask app, registers blueprints for different routes, and sets up the database and scheduler.
*   **`database/`:** Contains modules for database interaction.
    *   `db_manager.py`: A `DatabaseManager` class that handles all communication with the Supabase database.
    *   `supabase_client.py`: A Supabase client.
*   **`routes/`:** Contains blueprints for different application routes, such as authentication, search, product approval, scheduling, settings, and history.
*   **`scraping/`:** Contains modules for web scraping.
    *   `run_scraper.py`: A script to run the scraper for a given search term.
    *   `unificar_dados.py`: The core scraping module that unifies data from Amazon and Mercado Livre.
    *   `serpapi_amazon_func.py`: A function to search for products on Amazon using SerpApi.
    *   `web_scrap_mercado_livre.py`: A function to scrape data from Mercado Livre.
*   **`static/`:** Contains static assets like CSS and JavaScript files.
*   **`templates/`:** Contains HTML templates for rendering the application's UI.
*   **`utils/`:** Contains utility modules, such as a scheduler and helper functions.

# Building and Running

To build and run this project, you need to have Python and pip installed.

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd offer-search-app
    ```

2.  **Create a virtual environment and activate it:**

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up the environment variables:**

    Create a `.env` file in the root of the project and add the following variables:

    ```
    SECRET_KEY=your-secret-key
    SUPABASE_URL=your-supabase-url
    SUPABASE_KEY=your-supabase-key
    SERPAPI_KEY=your-serpapi-key
    ```

5.  **Run the database migrations:**

    The SQL scripts to create the database tables are in the `scripts/` directory. You can run them using the `run_all_scripts.py` script.

    ```bash
    python scripts/run_all_scripts.py
    ```

6.  **Run the application:**

    ```bash
    python app.py
    ```

    The application will be available at `http://localhost:5000`.

# Development Conventions

*   **Coding Style:** The code follows the PEP 8 style guide for Python.
*   **Testing:** There are no tests in the project.
*   **Contribution:** There are no contribution guidelines in the project.

## Frontend Development Conventions

*   **Modals, Scripts and Styles:** When creating new templates that use modals, scripts or styles, make sure to place them inside the correct blocks. The modal HTML should be inside the `content` block, the scripts should be inside the `extra_scripts` block, and the styles should be inside the `extra_styles` block. This is important to avoid issues with the modal not appearing or the scripts and styles not being applied correctly.