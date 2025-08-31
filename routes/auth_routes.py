from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from database.db_manager import DatabaseManager
from utils.helpers import validate_email, validate_password

auth_bp = Blueprint('auth', __name__)
db_manager = DatabaseManager()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    # Verifica se a conexão com o banco está funcionando
    try:
        db_status = db_manager.test_connection()
        if not db_status:
            flash('Erro de conexão com o banco de dados. Por favor, verifique as configurações.', 'error')
    except Exception as e:
        flash('Erro de conexão com o banco de dados. Por favor, verifique as configurações.', 'error')
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'
        
        # Validações básicas
        if not email or not password:
            flash('Email e senha são obrigatórios.', 'error')
            return render_template('auth/login.html')
        
        if not validate_email(email):
            flash('Formato de email inválido.', 'error')
            return render_template('auth/login.html')
        
        # Tenta autenticar
        user = db_manager.authenticate_user(email, password)
        
        if user:
            # Login bem-sucedido
            session.permanent = remember_me
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_name'] = user['nome']
            
            flash(f'Bem-vindo, {user["nome"]}!', 'success')
            
            # Redireciona para página solicitada ou dashboard
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou senha incorretos.', 'error')
    
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Página de registro"""
    # Verifica se a conexão com o banco está funcionando
    try:
        db_status = db_manager.test_connection()
        if not db_status:
            flash('Erro de conexão com o banco de dados. Por favor, verifique as configurações.', 'error')
            return render_template('auth/register.html')
    except Exception as e:
        flash('Erro de conexão com o banco de dados. Por favor, verifique as configurações.', 'error')
        return render_template('auth/register.html')
    
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validações
        errors = []
        
        if not nome or len(nome) < 2:
            errors.append('Nome deve ter pelo menos 2 caracteres.')
        
        if not email:
            errors.append('Email é obrigatório.')
        elif not validate_email(email):
            errors.append('Formato de email inválido.')
        
        if not password:
            errors.append('Senha é obrigatória.')
        else:
            is_valid, message = validate_password(password)
            if not is_valid:
                errors.append(message)
        
        if password != confirm_password:
            errors.append('Senhas não coincidem.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        # Verifica se email já existe
        try:
            existing_user_response = db_manager.supabase.table("users").select("id").eq("email", email).execute()
            if existing_user_response.data:
                flash('Este email já está cadastrado.', 'error')
                return render_template('auth/register.html')
        except Exception as e:
            print(f"Erro ao verificar email existente: {e}")
        
        # Cria usuário
        user_id = db_manager.create_user(email, password, nome)
        
        if user_id:
            flash('Conta criada com sucesso! Faça login para continuar.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Erro ao criar conta. Verifique se o banco de dados está configurado corretamente e tente novamente.', 'error')
    
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    """Logout do usuário"""
    user_name = session.get('user_name', 'Usuário')
    session.clear()
    flash(f'Até logo, {user_name}!', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
def profile():
    """Perfil do usuário"""
    if 'user_id' not in session:
        flash('Você precisa fazer login para acessar esta página.', 'warning')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/profile.html')
