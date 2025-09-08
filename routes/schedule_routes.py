from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from database.db_manager import DatabaseManager
from utils.scheduler import SchedulerManager
from datetime import datetime, timedelta
import json
from utils.decorators import login_required
from utils.simple_cache import cache

schedule_bp = Blueprint('schedule', __name__)
db = DatabaseManager()
scheduler = SchedulerManager(db)

@schedule_bp.route('/')
@login_required
def schedule_page():
    """Página de agendamentos"""
    user_id = session['user_id']
    agendamentos = db.get_active_schedules(user_id)
    
    # Se não há agendamentos, redireciona para configuração inicial
    if not agendamentos:
        return redirect(url_for('schedule.setup_default'))
    
    # Converter datas string para datetime
    from datetime import datetime
    def parse_dt(val):
        if isinstance(val, str):
            try:
                # Tenta formatos ISO e outros comuns
                return datetime.fromisoformat(val.replace('Z', '+00:00'))
            except Exception:
                return val
        return val

    agendamentos_json = []
    for ag in agendamentos:
        if 'criado_em' in ag:
            ag['criado_em'] = parse_dt(ag['criado_em'])
        if 'ultima_execucao' in ag and ag['ultima_execucao']:
            ag['ultima_execucao'] = parse_dt(ag['ultima_execucao'])
        if 'proxima_execucao' in ag and ag['proxima_execucao']:
            ag['proxima_execucao'] = parse_dt(ag['proxima_execucao'])
        # Mapeia termo_pesquisa para termo_busca para o template
        if 'termo_pesquisa' in ag:
            ag['termo_busca'] = ag['termo_pesquisa']
        elif 'termo_busca' not in ag:
            ag['termo_busca'] = ''

        agendamentos_json.append({
            'id': ag['id'],
            'termo_busca': ag['termo_busca'],
            'intervalo_horas': ag['intervalo_horas'],
            'ativo': ag['ativo']
        })

    return render_template('schedule/schedule.html', agendamentos=agendamentos, agendamentos_json=json.dumps(agendamentos_json))

@schedule_bp.route('/setup')
@login_required
def setup_default():
    """Página de configuração inicial de agendamentos"""
    user_id = session['user_id']
    agendamentos = db.get_active_schedules(user_id)
    
    # Se já tem agendamentos, redireciona para página principal
    if agendamentos:
        return redirect(url_for('schedule.schedule_page'))
    
    return render_template('schedule/setup_default.html')

@schedule_bp.route('/manage')
@login_required
def manage_schedules():
    """Página de gerenciamento de agendamentos (quando já tem agendamentos)"""
    user_id = session['user_id']
    agendamentos = db.get_active_schedules(user_id)
    
    # Se não há agendamentos, redireciona para configuração inicial
    if not agendamentos:
        return redirect(url_for('schedule.setup_default'))

    # Converter datas string para datetime
    from datetime import datetime
    def parse_dt(val):
        if isinstance(val, str):
            try:
                # Tenta formatos ISO e outros comuns
                return datetime.fromisoformat(val.replace('Z', '+00:00'))
            except Exception:
                return val
        return val

    agendamentos_json = []
    for ag in agendamentos:
        if 'criado_em' in ag:
            ag['criado_em'] = parse_dt(ag['criado_em'])
        if 'ultima_execucao' in ag and ag['ultima_execucao']:
            ag['ultima_execucao'] = parse_dt(ag['ultima_execucao'])
        if 'proxima_execucao' in ag and ag['proxima_execucao']:
            ag['proxima_execucao'] = parse_dt(ag['proxima_execucao'])
        # Mapeia termo_pesquisa para termo_busca para o template
        if 'termo_pesquisa' in ag:
            ag['termo_busca'] = ag['termo_pesquisa']
        elif 'termo_busca' not in ag:
            ag['termo_busca'] = ''

        agendamentos_json.append({
            'id': ag['id'],
            'termo_busca': ag['termo_busca'],
            'intervalo_horas': ag['intervalo_horas'],
            'ativo': ag['ativo']
        })

    return render_template('schedule/schedule.html', agendamentos=agendamentos, agendamentos_json=json.dumps(agendamentos_json))

@schedule_bp.route('/refresh')
@login_required
def refresh_schedules():
    """Limpa o cache e atualiza os dados da página de agendamentos."""
    user_id = session['user_id']
    cache_key = f"active_schedules_{user_id}"
    cache.invalidate(cache_key)
    flash('Os dados dos agendamentos foram atualizados.', 'success')
    return redirect(url_for('schedule.schedule_page'))

@schedule_bp.route('/create', methods=['POST'])
@login_required
def create_schedule():
    """Criar novo agendamento"""
    try:
        data = request.get_json()
        user_id = session['user_id']

        # Validar dados
        termo_busca = data.get('termo_busca', '').strip()
        intervalo = data.get('intervalo')
        ativo = data.get('ativo', True)

        # Se termo_busca estiver vazio, será usado busca padrão (ofertas do dia)
        if not termo_busca:
            termo_busca = ""  # Busca padrão

        if intervalo not in [6, 12]:
            return jsonify({'success': False, 'message': 'Intervalo deve ser 6 ou 12 horas'})

        # Criar agendamento
        schedule_id = db.create_schedule(user_id, termo_busca, intervalo)

        if schedule_id:
            # O agendamento será executado pelo scheduler em background
            return jsonify({'success': True, 'message': 'Agendamento criado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao criar agendamento'})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/update/<int:schedule_id>', methods=['POST'])
@login_required
def update_schedule(schedule_id):
    """Atualizar agendamento existente"""
    try:
        data = request.get_json()
        user_id = session['user_id']
        
        # Verificar se o agendamento pertence ao usuário
        schedule = db.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return jsonify({'success': False, 'message': 'Agendamento não encontrado'})
        
        # Validar dados
        termo_busca = data.get('termo_busca', '').strip()
        intervalo = data.get('intervalo')
        ativo = data.get('ativo', True)
        
        # Se termo_busca estiver vazio, será usado busca padrão (ofertas do dia)
        if not termo_busca:
            termo_busca = ""  # Busca padrão
        
        if intervalo not in [6, 12]:
            return jsonify({'success': False, 'message': 'Intervalo deve ser 6 ou 12 horas'})
        
        # Atualizar agendamento
        success = db.update_schedule(user_id, schedule_id, termo_busca, intervalo)
        
        if success:
            return jsonify({'success': True, 'message': 'Agendamento atualizado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao atualizar agendamento'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/delete/<int:schedule_id>', methods=['DELETE'])
@login_required
def delete_schedule(schedule_id):
    """Excluir agendamento"""
    try:
        user_id = session['user_id']
        
        # Verificar se o agendamento pertence ao usuário
        schedule = db.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return jsonify({'success': False, 'message': 'Agendamento não encontrado'})
        
        # Excluir agendamento
        success = db.delete_schedule(user_id, schedule_id)
        
        if success:
            return jsonify({'success': True, 'message': 'Agendamento excluído com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao excluir agendamento'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/toggle/<int:schedule_id>', methods=['POST'])
@login_required
def toggle_schedule(schedule_id):
    """Ativar/desativar agendamento"""
    try:
        user_id = session['user_id']
        
        # Verificar se o agendamento pertence ao usuário
        schedule = db.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return jsonify({'success': False, 'message': 'Agendamento não encontrado'})
        
        # Alternar status
        new_status = not schedule['ativo']
        success = db.toggle_schedule_status(schedule_id, new_status)
        
        if success:
            return jsonify({'success': True, 'ativo': new_status})
        else:
            return jsonify({'success': False, 'message': 'Erro ao alterar status'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/create-default', methods=['POST'])
@login_required
def create_default_schedule():
    """Criar agendamento padrão (ofertas do dia, 2x por dia)"""
    try:
        user_id = session['user_id']
        
        # Verificar se já existe agendamento padrão
        existing_schedules = db.get_active_schedules(user_id)
        for schedule in existing_schedules:
            if not schedule.get('termo_pesquisa') or schedule.get('termo_pesquisa').strip() == "":
                return jsonify({'success': False, 'message': 'Já existe um agendamento padrão ativo'})
        
        # Criar agendamento padrão (busca padrão, 12 horas = 2x por dia)
        schedule_id = db.create_schedule(user_id, "", 12)  # Termo vazio = busca padrão
        
        if schedule_id:
            return jsonify({'success': True, 'message': 'Agendamento padrão criado com sucesso! Buscará ofertas do dia 2 vezes por dia.'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao criar agendamento padrão'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/history/<int:schedule_id>')
@login_required
def schedule_history(schedule_id):
    """Histórico de execuções de um agendamento"""
    user_id = session['user_id']
    
    # Verificar se o agendamento pertence ao usuário
    schedule = db.get_schedule_by_id(schedule_id, user_id)
    if not schedule:
        return redirect(url_for('schedule.schedule_page'))
    
    # Buscar histórico de execuções
    execucoes = db.get_schedule_executions(schedule_id)
    
    return render_template('schedule/history.html', 
                         schedule=schedule, 
                         execucoes=execucoes)
