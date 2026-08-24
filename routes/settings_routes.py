from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from dateutil.parser import isoparse
from services.meli.auth import MeliAuthManager

settings_bp = Blueprint('settings', __name__)
db = DatabaseManager()
meli_auth = MeliAuthManager(db=db)

@settings_bp.route('/')
def settings_page():
    """Página principal de configurações"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    # Buscar configurações do usuário
    user_configs = db.get_user_configs(user_id)
    alertas = db.get_user_alerts(user_id)
    
    # Adiciona o MIN_PRICE_FILTER
    min_price_filter = next((item['valor'] for item in user_configs if item['chave'] == 'MIN_PRICE_FILTER'), 400)

    # Status da conexão oficial do Mercado Livre
    meli_status = meli_auth.get_status(user_id)

    # Variáveis de ambiente disponíveis (mascaradas)
    env_vars = {
        'SUPABASE_URL': '***' if os.environ.get('SUPABASE_URL') else '',
        'SUPABASE_KEY': '***' if os.environ.get('SUPABASE_KEY') else '',
        'SERPAPI_KEY': '***' if os.environ.get('SERPAPI_KEY') else '',
        'SECRET_KEY': '***' if os.environ.get('SECRET_KEY') else '',
        'FLASK_DEBUG': os.environ.get('FLASK_DEBUG', 'False'),
        'PORT': os.environ.get('PORT', '5000'),
        'EVOLUTION_API_INSTANCE': os.environ.get('EVOLUTION_API_INSTANCE', ''),
        'EVOLUTION_API_KEY': '***' if os.environ.get('EVOLUTION_API_KEY') else '',
        'MELI_APP_ID': os.environ.get('MELI_APP_ID', meli_auth.DEFAULT_APP_ID)
    }
    
    is_admin = db.is_user_admin(user_id)
    team_members = db.get_all_team_members() if is_admin else []
    
    return render_template('settings/settings.html', 
                         user_configs=user_configs,
                         alertas=alertas,
                         env_vars=env_vars,
                         min_price_filter=min_price_filter,
                         is_admin=is_admin,
                         team_members=team_members,
                         meli_status=meli_status)


# === ROTAS OAUTH DA API OFICIAL DO MERCADO LIVRE ===

@settings_bp.route('/meli/connect')
def meli_connect():
    """Inicia o fluxo OAuth 2.0 com o Mercado Livre"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    # Monta a URL de callback com base no host atual
    redirect_uri = request.host_url.rstrip('/') + url_for('settings.meli_callback')
    auth_url = meli_auth.get_authorization_url(redirect_uri=redirect_uri, state=str(session['user_id']))
    return redirect(auth_url)


@settings_bp.route('/meli/callback')
def meli_callback():
    """Recebe o authorization_code do Mercado Livre e troca por tokens"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    code = request.args.get('code')
    error = request.args.get('error')
    error_description = request.args.get('error_description')

    if error:
        print(f"❌ [Meli OAuth Callback] Erro retornado: {error} - {error_description}")
        return redirect(url_for('settings.settings_page') + f'?meli_error={error}')

    if not code:
        return redirect(url_for('settings.settings_page') + '?meli_error=no_code')

    user_id = session['user_id']
    redirect_uri = request.host_url.rstrip('/') + url_for('settings.meli_callback')
    
    success, result = meli_auth.exchange_code_for_tokens(code=code, redirect_uri=redirect_uri, user_id=user_id)
    if success:
        return redirect(url_for('settings.settings_page') + '?meli_connected=1')
    else:
        err_msg = result.get('error', 'Falha ao obter tokens')
        return redirect(url_for('settings.settings_page') + f'?meli_error=exchange_failed')


@settings_bp.route('/meli/status', methods=['GET'])
def meli_status():
    """Retorna o status JSON da integração Mercado Livre"""
    if 'user_id' not in session:
        return jsonify({'connected': False, 'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    status = meli_auth.get_status(user_id=user_id)
    return jsonify(status)


@settings_bp.route('/meli/refresh', methods=['POST'])
def meli_refresh():
    """Força a renovação do access_token"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    success, result = meli_auth.refresh_access_token(user_id=user_id)
    if success:
        return jsonify({'success': True, 'message': 'Token do Mercado Livre renovado com sucesso!'})
    else:
        return jsonify({'success': False, 'error': result.get('error', 'Falha ao renovar token')}), 400


@settings_bp.route('/meli/disconnect', methods=['POST'])
def meli_disconnect():
    """Desconecta a conta do Mercado Livre"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    meli_auth.disconnect(user_id=user_id)
    return jsonify({'success': True, 'message': 'Conta Mercado Livre desconectada com sucesso.'})

@settings_bp.route('/update-min-price', methods=['POST'])
def update_min_price():
    """Atualizar o filtro de preço mínimo"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    try:
        data = request.get_json()
        min_price = data.get('min_price')
        
        if not min_price or float(min_price) < 0:
            return jsonify({'success': False, 'message': 'Preço mínimo inválido'})
            
        user_id = session['user_id']
        db.save_user_config(user_id, 'MIN_PRICE_FILTER', str(min_price))
        
        return jsonify({'success': True, 'message': 'Filtro de preço mínimo atualizado com sucesso'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao atualizar filtro de preço: {str(e)}'})

@settings_bp.route('/update-env', methods=['POST'])
def update_environment():
    """Atualizar variáveis de ambiente"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    try:
        data = request.get_json()
        
        # Validar dados recebidos
        allowed_vars = ['SUPABASE_URL', 'SUPABASE_KEY', 'SERPAPI_KEY', 'SECRET_KEY', 'FLASK_DEBUG', 'PORT', 'EVOLUTION_API_INSTANCE', 'EVOLUTION_API_KEY']
        
        updated_vars = []
        for var_name, var_value in data.items():
            if var_name in allowed_vars and var_value.strip():
                # Não atualizar se o valor for mascarado
                if var_value != '***':
                    os.environ[var_name] = var_value.strip()
                    updated_vars.append(var_name)
        
        if updated_vars:
            return jsonify({
                'success': True, 
                'message': f'Variáveis atualizadas: {", ".join(updated_vars)}',
                'updated_vars': updated_vars
            })
        else:
            return jsonify({'success': False, 'message': 'Nenhuma variável foi atualizada'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao atualizar variáveis: {str(e)}'})

@settings_bp.route('/alerts', methods=['GET', 'POST'])
def manage_alerts():
    """Gerenciar alertas de preço"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validar dados
            produto_nome = data.get('produto_nome', '').strip()
            preco_alvo = data.get('preco_alvo')
            tipo_alerta = data.get('tipo_alerta', 'menor_que')
            ativo = data.get('ativo', True)
            
            if not produto_nome:
                return jsonify({'success': False, 'message': 'Nome do produto é obrigatório'})
            
            if not preco_alvo or float(preco_alvo) <= 0:
                return jsonify({'success': False, 'message': 'Preço alvo deve ser maior que zero'})
            
            # Criar alerta
            alert_id = db.create_price_alert(user_id, produto_nome, float(preco_alvo), tipo_alerta, ativo)
            
            if alert_id:
                return jsonify({'success': True, 'message': 'Alerta criado com sucesso'})
            else:
                return jsonify({'success': False, 'message': 'Erro ao criar alerta'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})
    
    # GET - Listar alertas
    alertas = db.get_user_alerts(user_id)
    return jsonify({'alertas': alertas})

@settings_bp.route('/alerts/<int:alert_id>', methods=['PUT', 'DELETE'])
def update_delete_alert(alert_id):
    """Atualizar ou excluir alerta"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    user_id = session['user_id']
    
    # Verificar se o alerta pertence ao usuário
    alert = db.get_alert_by_id(alert_id, user_id)
    if not alert:
        return jsonify({'success': False, 'message': 'Alerta não encontrado'})
    
    if request.method == 'PUT':
        try:
            data = request.get_json()
            
            produto_nome = data.get('produto_nome', alert['produto_nome']).strip()
            preco_alvo = data.get('preco_alvo', alert['preco_alvo'])
            tipo_alerta = data.get('tipo_alerta', alert['tipo_alerta'])
            ativo = data.get('ativo', alert['ativo'])
            
            if not produto_nome:
                return jsonify({'success': False, 'message': 'Nome do produto é obrigatório'})
            
            if float(preco_alvo) <= 0:
                return jsonify({'success': False, 'message': 'Preço alvo deve ser maior que zero'})
            
            # Atualizar alerta
            success = db.update_price_alert(alert_id, produto_nome, float(preco_alvo), tipo_alerta, ativo)
            
            if success:
                return jsonify({'success': True, 'message': 'Alerta atualizado com sucesso'})
            else:
                return jsonify({'success': False, 'message': 'Erro ao atualizar alerta'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})
    
    elif request.method == 'DELETE':
        try:
            success = db.delete_price_alert(alert_id)
            
            if success:
                return jsonify({'success': True, 'message': 'Alerta excluído com sucesso'})
            else:
                return jsonify({'success': False, 'message': 'Erro ao excluir alerta'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@settings_bp.route('/profile', methods=['GET', 'POST'])
def profile_settings():
    """Configurações do perfil do usuário"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Atualizar nome
            if 'nome' in data:
                nome = data['nome'].strip()
                if nome:
                    success = db.update_user_name(user_id, nome)
                    if success:
                        session['user_name'] = nome
                        return jsonify({'success': True, 'message': 'Nome atualizado com sucesso'})
            
            # Atualizar senha
            if 'senha_atual' in data and 'nova_senha' in data:
                senha_atual = data['senha_atual']
                nova_senha = data['nova_senha']
                
                # Verificar senha atual
                user = db.get_user_by_id(user_id)
                if not user or not check_password_hash(user['senha'], senha_atual):
                    return jsonify({'success': False, 'message': 'Senha atual incorreta'})
                
                # Atualizar senha
                senha_hash = generate_password_hash(nova_senha)
                success = db.update_user_password(user_id, senha_hash)
                
                if success:
                    return jsonify({'success': True, 'message': 'Senha atualizada com sucesso'})
                else:
                    return jsonify({'success': False, 'message': 'Erro ao atualizar senha'})
            
            return jsonify({'success': False, 'message': 'Dados inválidos'})
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})
    
    # GET - Buscar dados do usuário
    user = db.get_user_by_id(user_id)
    if user:
        return jsonify({
            'nome': user['nome'],
            'email': user['email'],
            'criado_em': isoparse(user['criado_em']).isoformat() if user['criado_em'] else None
        })
    else:
        return jsonify({'success': False, 'message': 'Usuário não encontrado'})

@settings_bp.route('/notifications', methods=['GET', 'POST'])
def notification_settings():
    """Configurações de notificações"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Configurações de notificação
            email_alerts = data.get('email_alerts', True)
            browser_notifications = data.get('browser_notifications', True)
            daily_summary = data.get('daily_summary', False)
            
            # Salvar configurações
            success = db.update_notification_settings(user_id, {
                'email_alerts': email_alerts,
                'browser_notifications': browser_notifications,
                'daily_summary': daily_summary
            })
            
            if success:
                return jsonify({'success': True, 'message': 'Configurações de notificação atualizadas'})
            else:
                return jsonify({'success': False, 'message': 'Erro ao atualizar configurações'})
                
        except Exception as e:
            return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})
    
    # GET - Buscar configurações atuais
    configs = db.get_notification_settings(user_id)
    return jsonify(configs or {
        'email_alerts': True,
        'browser_notifications': True,
        'daily_summary': False
    })


# ─── Gestão de Membros da Equipe (Admin Only) ──────────────────────────────────

@settings_bp.route('/team', methods=['GET'])
def get_team_members():
    """Lista todos os membros da equipe (exclusivo para administradores)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    if not db.is_user_admin(user_id):
        return jsonify({'success': False, 'error': 'Acesso restrito a administradores.'}), 403
    
    members = db.get_all_team_members()
    return jsonify({'success': True, 'members': members})


@settings_bp.route('/team/add', methods=['POST'])
def add_team_member():
    """Adiciona um novo membro à equipe"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    user_id = session['user_id']
    if not db.is_user_admin(user_id):
        return jsonify({'success': False, 'error': 'Acesso restrito a administradores.'}), 403
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        nome = (data.get('nome') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        role = (data.get('role') or 'member').strip().lower()
        cargo = (data.get('cargo') or '').strip()
        telefone = (data.get('telefone') or '').strip()

        if not nome or len(nome) < 2:
            return jsonify({'success': False, 'error': 'Nome do membro deve ter pelo menos 2 caracteres.'}), 400
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Email corporativo inválido.'}), 400

        if not password or len(password) < 6:
            return jsonify({'success': False, 'error': 'A senha inicial deve ter no mínimo 6 caracteres.'}), 400

        # Verifica se email já existe
        try:
            existing = db.supabase.table("users").select("id").eq("email", email).execute()
            if existing.data:
                return jsonify({'success': False, 'error': 'Este email já está cadastrado no sistema.'}), 400
        except Exception:
            pass

        new_user_id = db.create_user(
            email=email,
            password=password,
            nome=nome,
            role=role,
            cargo=cargo,
            telefone=telefone
        )

        if new_user_id:
            return jsonify({
                'success': True,
                'message': f'Membro "{nome}" cadastrado com sucesso!',
                'user_id': new_user_id
            })
        else:
            return jsonify({'success': False, 'error': 'Erro ao registrar membro no banco de dados.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500


@settings_bp.route('/team/<user_id>', methods=['PUT', 'POST'])
def update_team_member(user_id):
    """Atualiza dados e status de um membro da equipe"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    admin_id = session['user_id']
    if not db.is_user_admin(admin_id):
        return jsonify({'success': False, 'error': 'Acesso restrito a administradores.'}), 403
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        nome = data.get('nome')
        role = data.get('role')
        cargo = data.get('cargo')
        telefone = data.get('telefone')
        ativo = data.get('ativo')

        # Se for desativar, não permitir desativar a si mesmo
        if ativo is False and str(user_id) == str(admin_id):
            return jsonify({'success': False, 'error': 'Você não pode desativar o seu próprio usuário.'}), 400

        success = db.update_team_member(
            user_id=user_id,
            nome=nome,
            role=role,
            cargo=cargo,
            telefone=telefone,
            ativo=ativo
        )

        if success:
            return jsonify({'success': True, 'message': 'Membro da equipe atualizado com sucesso!'})
        else:
            return jsonify({'success': False, 'error': 'Erro ao atualizar membro no banco de dados.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500


@settings_bp.route('/team/<user_id>/reset-password', methods=['POST'])
def reset_member_password(user_id):
    """Redefine a senha de um membro da equipe (Ação administrativa)"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    admin_id = session['user_id']
    if not db.is_user_admin(admin_id):
        return jsonify({'success': False, 'error': 'Acesso restrito a administradores.'}), 403
    
    try:
        data = request.get_json(force=True, silent=True) or {}
        new_password = data.get('new_password') or ''

        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'error': 'A nova senha deve ter no mínimo 6 caracteres.'}), 400

        success = db.reset_user_password(user_id, new_password)
        if success:
            return jsonify({'success': True, 'message': 'Senha do membro redefinida com sucesso!'})
        else:
            return jsonify({'success': False, 'error': 'Erro ao redefinir senha no banco de dados.'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro interno: {str(e)}'}), 500


@settings_bp.route('/team/<user_id>', methods=['DELETE'])
@settings_bp.route('/team/<user_id>/delete', methods=['POST'])
def delete_team_member(user_id):
    """Exclui um membro da equipe"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Não autenticado'}), 401
    
    admin_id = session['user_id']
    if not db.is_user_admin(admin_id):
        return jsonify({'success': False, 'error': 'Acesso restrito a administradores.'}), 403

    if str(user_id) == str(admin_id):
        return jsonify({'success': False, 'error': 'Você não pode excluir sua própria conta de administrador.'}), 400

    success = db.delete_team_member(user_id=user_id, requesting_user_id=admin_id)
    if success:
        return jsonify({'success': True, 'message': 'Membro da equipe excluído com sucesso.'})
    else:
        return jsonify({'success': False, 'error': 'Erro ao excluir membro ou auto-exclusão bloqueada.'}), 500