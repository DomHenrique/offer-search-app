from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta
import threading
import time
from functools import wraps
from dotenv import load_dotenv
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Importa módulos locais
from database.db_manager import DatabaseManager
from database.table_manager import TableManager
from routes.auth_routes import auth_bp
from routes.search_routes import search_bp
from routes.approval_routes import approval_bp
from routes.schedule_routes import schedule_bp
from routes.settings_routes import settings_bp
from routes.history_routes import history_bp
from routes.alert_routes import alert_bp
from routes.catalog_routes import catalog_bp
from utils.scheduler import SchedulerManager
from utils.helpers import format_currency, time_ago
from utils.decorators import login_required

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configurações do Flask
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SECURE'] = False  # True em produção com HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Registra blueprints (rotas modulares)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(search_bp, url_prefix='/search')
app.register_blueprint(approval_bp, url_prefix='/approval')
app.register_blueprint(schedule_bp, url_prefix='/schedule')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(history_bp, url_prefix='/history')
app.register_blueprint(alert_bp, url_prefix='/alert')
app.register_blueprint(catalog_bp, url_prefix='/catalog')

# Inicializa gerenciador de banco de dados
db_manager = DatabaseManager()

# Inicializa gerenciador de tabelas
table_manager = TableManager(db_manager)

# Verifica e cria tabelas necessárias
def initialize_database():
    """Inicializa o banco de dados criando tabelas necessárias"""
    try:
        logger.info("🔄 Iniciando verificação e criação de tabelas...")
        
        # Verifica se as tabelas existem
        table_status = table_manager.verify_all_tables()
        
        # Cria tabelas que não existem
        missing_tables = [table for table, exists in table_status.items() if not exists]
        if missing_tables:
            logger.warning(f"⚠️ As seguintes tabelas estão faltando: {missing_tables}")
            creation_results = table_manager.create_all_tables()
            
            # Verifica se todas as tabelas foram criadas com sucesso
            failed_creations = [table for table, success in creation_results.items() if not success]
            if failed_creations:
                logger.error(f"❌ Falha ao criar as tabelas: {failed_creations}")
            else:
                logger.info("✅ Todas as tabelas necessárias foram criadas com sucesso!")
        else:
            logger.info("✅ Todas as tabelas necessárias já existem!")
            
        # Fecha a conexão temporária
        table_manager.close_connection()
            
    except Exception as e:
        logger.error(f"❌ Erro durante inicialização do banco de dados: {e}")
        # Fecha a conexão mesmo em caso de erro
        try:
            table_manager.close_connection()
        except:
            pass
        raise

# Executa a inicialização do banco de dados
try:
    initialize_database()
except Exception as e:
    logger.error(f"❌ Falha crítica na inicialização do banco de dados: {e}")
    # Decide se a aplicação deve parar ou continuar
    # Neste caso, vamos permitir que continue para que o erro seja visível
    pass

# Inicializa scheduler para agendamentos
scheduler_manager = SchedulerManager(db_manager)

# Filtros de template personalizados
@app.template_filter('currency')
def currency_filter(value):
    return format_currency(value)

@app.template_filter('timeago')
def timeago_filter(value):
    return time_ago(value)



# Rota principal - Dashboard
@app.route('/')
@login_required
def dashboard():
    """Dashboard principal com resumo das atividades"""
    try:
        user_id = session['user_id']
        
        # Busca estatísticas do usuário
        stats = db_manager.get_user_stats(user_id)
        
        # Busca últimas buscas
        recent_searches = db_manager.get_recent_searches(user_id, limit=5)
        
        # Busca produtos aprovados recentes
        recent_approved = db_manager.get_recent_approved_products(user_id, limit=5)
        
        # Busca agendamentos ativos
        active_schedules = db_manager.get_active_schedules(user_id)
        
        return render_template('dashboard.html',
                             stats=stats,
                             recent_searches=recent_searches,
                             recent_approved=recent_approved,
                             active_schedules=active_schedules)
    
    except Exception as e:
        flash(f'Erro ao carregar dashboard: {str(e)}', 'error')
        return render_template('dashboard.html', 
                             stats={}, 
                             recent_searches=[], 
                             recent_approved=[], 
                             active_schedules=[])

# Rota para verificar status do sistema
@app.route('/health')
def health_check():
    """Endpoint para verificar saúde do sistema"""
    try:
        # Testa conexão com banco
        db_status = db_manager.test_connection()
        
        # Testa scheduler
        scheduler_status = scheduler_manager.is_running()
        
        return jsonify({
            'status': 'healthy' if db_status and scheduler_status else 'unhealthy',
            'database': 'connected' if db_status else 'disconnected',
            'scheduler': 'running' if scheduler_status else 'stopped',
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# Manipulador de erro 404
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

# Manipulador de erro 500
@app.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500

# Context processor para variáveis globais nos templates
@app.context_processor
def inject_globals():
    return {
        'current_user': session.get('user_name', ''),
        'current_time': datetime.now(),
        'app_name': 'Offer Search App'
    }

def start_scheduler():
    """Inicia o scheduler em thread separada"""
    def run_scheduler():
        while True:
            try:
                scheduler_manager.check_and_execute_schedules()
                time.sleep(300)  # Verifica a cada 5 minutos
            except Exception as e:
                print(f"Erro no scheduler: {e}")
                time.sleep(60)  # Aguarda 1 minuto em caso de erro
    
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

if __name__ == '__main__':
    # Inicia scheduler em background
    start_scheduler()
    
    # Inicia aplicação Flask
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    
    print(f"Iniciando Offer Search App na porta {port}")
    print(f"Modo debug: {debug_mode}")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)