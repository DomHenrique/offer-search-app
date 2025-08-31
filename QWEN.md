# Offer Search App - Project Context

## Project Overview

This is a Flask-based web application called "Offer Search App" designed to help users search for products across multiple marketplaces (currently Amazon and Mercado Livre), save preferred products, and schedule automatic searches. The application uses Supabase as its primary database for storing user data, search history, approved products, and scheduling configurations. It integrates web scraping components to fetch product data from marketplaces using SerpAPI for Amazon and custom scrapers for Mercado Livre.

### Key Technologies

- **Backend Framework**: Flask (Python)
- **Database**: Supabase (PostgreSQL)
- **Frontend**: HTML/CSS/JavaScript with Bootstrap
- **Web Scraping**: Selenium, BeautifulSoup, requests, SerpAPI
- **Authentication**: Custom session-based authentication with Werkzeug security
- **Environment Management**: python-dotenv
- **Task Scheduling**: Custom background scheduler using threading

## Project Structure

- `app.py`: Main application file with Flask initialization and core routes
- `database/`: Contains database management logic (Supabase client and DB manager)
- `routes/`: Modular Flask blueprints for different application sections (auth, search, approval, schedule, settings, history)
- `scraping/`: Web scraping modules for collecting product data
- `utils/`: Utility functions and scheduler
- `templates/`: HTML templates for the web interface
- `static/`: Static assets (CSS, JS, images)
- `requirements.txt`: Python dependencies

## Building and Running

### Prerequisites

1. Python 3.8+
2. Virtual environment (recommended)
3. Supabase account and project
4. SerpAPI key for Amazon searches

### Setup

1. **Create and activate virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env` file in the project root with:
   ```env
   SECRET_KEY=your-secret-key-here
   SUPABASE_URL=your-supabase-project-url
   SUPABASE_KEY=your-supabase-service-role-key
   SERPAPI_KEY=your-serpapi-key
   ```

4. **Initialize Supabase tables**:
   The application will automatically attempt to create all required tables on startup. If direct database access is available, it will create them automatically. If not, follow the manual instructions below:
   
   a. Run the manual table creation script:
   ```bash
   python scripts/create_tables_manual.py
   ```
   
   b. Or manually execute the SQL scripts in the `scripts/` directory in the following order:
      - `01_create_users_table.sql`
      - `02_create_ofertas_table.sql`
      - `03_create_produtos_aprovados_table.sql`
      - `04_create_agendamentos_table.sql`
      - `05_create_historico_buscas_table.sql`
      - `06_create_alertas_table.sql`
      - `07_create_configuracoes_table.sql`
      - `08_create_triggers_and_functions.sql`

### Running the Application

```bash
python app.py
```

By default, the application will start on `http://localhost:5000` in development mode. Set `FLASK_DEBUG=true` in your `.env` file to enable debug mode.

## Development Conventions

### Code Organization

- Uses Flask blueprints for modular route organization
- Separates database logic from route handlers
- Uses a custom database manager (`DatabaseManager`) to encapsulate all Supabase interactions
- Implements utility functions for common operations (currency formatting, time ago, etc.)
- Uses environment variables for configuration (via python-dotenv)

### Authentication

- Custom session-based authentication
- Decorator `@login_required` for protecting routes
- Password hashing using Werkzeug security

### Data Handling

- Web scraping is performed in separate threads to prevent blocking the main application
- Search results are saved to the "ofertas" table in Supabase
- Users can "approve" products to save them to the "produtos_aprovados" table
- Implements robust data type conversion when saving to Supabase (especially for numeric and boolean fields)

### Scheduling

- Custom scheduler that runs in a background thread
- Schedules are stored in the "agendamentos" table
- Supports 6-hour and 12-hour intervals for automatic searches
- Scheduler checks for pending jobs every 5 minutes

### Error Handling

- Comprehensive try/except blocks around critical operations
- User-friendly error messages via Flask flash
- JSON error responses for API endpoints
- Graceful degradation when optional features are not configured