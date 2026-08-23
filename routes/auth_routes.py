from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
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
            session['user_role'] = user.get('role') or ('admin' if str(user['id']) in ('1', 1) else 'member')
            session['user_cargo'] = user.get('cargo') or ''
            session['user_telefone'] = user.get('telefone') or ''
            
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
    
    user_id = session['user_id']
    user = db_manager.get_user_by_id(user_id) or {
        'id': user_id,
        'nome': session.get('user_name', 'Usuário'),
        'email': session.get('user_email', ''),
        'role': session.get('user_role', 'member'),
        'cargo': session.get('user_cargo', ''),
        'telefone': session.get('user_telefone', ''),
        'criado_em': None
    }
    stats = db_manager.get_user_stats(user_id)
    return render_template('auth/profile.html', user=user, stats=stats)

@auth_bp.route('/profile/update', methods=['POST'])
def update_profile():
    """Atualiza dados cadastrais do perfil"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Não autenticado'}), 401
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        nome = (data.get('nome') or '').strip()
        cargo = (data.get('cargo') or '').strip()
        telefone = (data.get('telefone') or '').strip()

        if not nome or len(nome) < 2:
            return jsonify({'success': False, 'message': 'O nome deve ter pelo menos 2 caracteres.'}), 400

        user_id = session['user_id']
        success = db_manager.update_user_profile(user_id, nome=nome, cargo=cargo, telefone=telefone)

        if success:
            session['user_name'] = nome
            session['user_cargo'] = cargo
            session['user_telefone'] = telefone
            return jsonify({'success': True, 'message': 'Dados cadastrais atualizados com sucesso!'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao atualizar dados no banco.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'}), 500

@auth_bp.route('/profile/change-password', methods=['POST'])
def change_password():
    """Alteração segura de senha do próprio usuário"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Não autenticado'}), 401
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        senha_atual = data.get('senha_atual') or ''
        nova_senha = data.get('nova_senha') or ''
        confirmar_senha = data.get('confirmar_senha') or ''

        if not senha_atual or not nova_senha:
            return jsonify({'success': False, 'message': 'Preencha a senha atual e a nova senha.'}), 400

        if len(nova_senha) < 6:
            return jsonify({'success': False, 'message': 'A nova senha deve conter pelo menos 6 caracteres.'}), 400

        if nova_senha != confirmar_senha:
            return jsonify({'success': False, 'message': 'A confirmação de senha não confere.'}), 400

        user_id = session['user_id']
        user = db_manager.get_user_by_id(user_id)
        if not user or not check_password_hash(user.get('password_hash', ''), senha_atual):
            return jsonify({'success': False, 'message': 'A senha atual informada está incorreta.'}), 400

        success = db_manager.reset_user_password(user_id, nova_senha)
        if success:
            return jsonify({'success': True, 'message': 'Senha atualizada com sucesso!'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao atualizar senha no banco.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'}), 500


# ─── Sincronização de Sessão Mercado Livre (Extensão Chrome / API) ─────────────

@auth_bp.route('/sync-ml-session', methods=['POST'])
def sync_ml_session():
    """
    Recebe os cookies capturados pela extensão Chrome do Mercado Livre
    e armazena na tabela de configurações do Supabase.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        cookies = data.get('cookies') or []

        if not cookies:
            return jsonify({'success': False, 'error': 'Nenhum cookie recebido no payload.'}), 400

        user_id = session.get('user_id') or data.get('user_id') or "1"
        user_email = session.get('user_email') or data.get('user_email')

        success = db_manager.save_ml_session(cookies=cookies, user_email=user_email, user_id=str(user_id))

        if success:
            return jsonify({
                'success': True,
                'message': f'{len(cookies)} cookies do Mercado Livre sincronizados com sucesso!',
                'count': len(cookies),
                'updated_at': datetime.now().isoformat()
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao persistir sessão no banco de dados.'}), 500

    except Exception as e:
        print(f"Erro ao sincronizar sessão ML: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/ml-session-status', methods=['GET'])
def ml_session_status():
    """
    Retorna o status atual da sessão do Mercado Livre.
    """
    try:
        user_id = session.get('user_id') or "1"
        session_data = db_manager.get_ml_session(user_id=str(user_id))

        if not session_data:
            return jsonify({
                'connected': False,
                'status': 'disconnected',
                'message': 'Nenhuma sessão do Mercado Livre sincronizada.'
            })

        updated_at = session_data.get('updated_at')
        total_cookies = session_data.get('total_cookies', 0)

        # Considera recente se sincronizado nas últimas 48 horas
        is_recent = True
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at.replace('Z', ''))
                diff_hours = (datetime.now() - dt).total_seconds() / 3600
                is_recent = diff_hours < 48
            except Exception:
                pass

        return jsonify({
            'connected': True,
            'status': 'active' if is_recent else 'outdated',
            'updated_at': updated_at,
            'total_cookies': total_cookies,
            'user_email': session_data.get('user_email'),
            'message': 'Sessão ativa e pronta para uso.' if is_recent else 'Sessão desatualizada (mais de 48h).'
        })

    except Exception as e:
        return jsonify({'connected': False, 'error': str(e)}), 500


@auth_bp.route('/sync-amazon-session', methods=['POST'])
def sync_amazon_session():
    """
    Recebe os cookies capturados pela extensão Chrome da Amazon Brasil
    e armazena na tabela de configurações do Supabase.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        cookies = data.get('cookies') or []

        if not cookies:
            return jsonify({'success': False, 'error': 'Nenhum cookie recebido no payload.'}), 400

        user_id = session.get('user_id') or data.get('user_id') or "1"
        user_email = session.get('user_email') or data.get('user_email')

        success = db_manager.save_amazon_session(cookies=cookies, user_email=user_email, user_id=str(user_id))

        if success:
            return jsonify({
                'success': True,
                'message': f'{len(cookies)} cookies da Amazon sincronizados com sucesso!',
                'count': len(cookies),
                'updated_at': datetime.now().isoformat()
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao persistir sessão Amazon no banco de dados.'}), 500

    except Exception as e:
        print(f"Erro ao sincronizar sessão Amazon: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@auth_bp.route('/amazon-session-status', methods=['GET'])
def amazon_session_status():
    """
    Retorna o status atual da sessão da Amazon Brasil.
    """
    try:
        user_id = session.get('user_id') or "1"
        session_data = db_manager.get_amazon_session(user_id=str(user_id))

        if not session_data:
            return jsonify({
                'connected': False,
                'status': 'disconnected',
                'message': 'Nenhuma sessão da Amazon sincronizada.'
            })

        updated_at = session_data.get('updated_at')
        total_cookies = session_data.get('total_cookies', 0)

        # Considera recente se sincronizado nas últimas 48 horas
        is_recent = True
        if updated_at:
            try:
                dt = datetime.fromisoformat(updated_at.replace('Z', ''))
                diff_hours = (datetime.now() - dt).total_seconds() / 3600
                is_recent = diff_hours < 48
            except Exception:
                pass

        return jsonify({
            'connected': True,
            'status': 'active' if is_recent else 'outdated',
            'updated_at': updated_at,
            'total_cookies': total_cookies,
            'user_email': session_data.get('user_email'),
            'message': 'Sessão Amazon ativa e pronta para uso.' if is_recent else 'Sessão Amazon desatualizada (mais de 48h).'
        })

    except Exception as e:
        return jsonify({'connected': False, 'error': str(e)}), 500


