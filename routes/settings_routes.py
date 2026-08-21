from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from werkzeug.security import generate_password_hash, check_password_hash
import os
import json
from dateutil.parser import isoparse

settings_bp = Blueprint('settings', __name__)
db = DatabaseManager()

@settings_bp.route('/')
def settings_page():
    """Página principal de configurações"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    
    # Buscar configurações do usuário
    user_configs = db.get_user_configs(user_id)
    alertas = db.get_user_alerts(user_id)
    
    # Variáveis de ambiente disponíveis (mascaradas)
    env_vars = {
        'SUPABASE_URL': '***' if os.environ.get('SUPABASE_URL') else '',
        'SUPABASE_KEY': '***' if os.environ.get('SUPABASE_KEY') else '',
        'SERPAPI_KEY': '***' if os.environ.get('SERPAPI_KEY') else '',
        'SECRET_KEY': '***' if os.environ.get('SECRET_KEY') else '',
        'FLASK_DEBUG': os.environ.get('FLASK_DEBUG', 'False'),
        'PORT': os.environ.get('PORT', '5000'),
        'EVOLUTION_API_INSTANCE': os.environ.get('EVOLUTION_API_INSTANCE', ''),
        'EVOLUTION_API_KEY': '***' if os.environ.get('EVOLUTION_API_KEY') else ''
    }
    
    return render_template('settings/settings.html', 
                         user_configs=user_configs,
                         alertas=alertas,
                         env_vars=env_vars)

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