from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from database.db_manager import DatabaseManager
from utils.scheduler import SchedulerManager
from datetime import datetime, timedelta
import json

schedule_bp = Blueprint('schedule', __name__)
db = DatabaseManager()
scheduler = SchedulerManager(db)

@schedule_bp.route('/schedule')
def schedule_page():
    """Página de agendamentos"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    user_id = session['user_id']
    agendamentos = db.get_user_schedules(user_id)
    
    return render_template('schedule/schedule.html', agendamentos=agendamentos)

@schedule_bp.route('/schedule/create', methods=['POST'])
def create_schedule():
    """Criar novo agendamento"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    try:
        data = request.get_json()
        user_id = session['user_id']
        
        # Validar dados
        termo_busca = data.get('termo_busca', '').strip()
        intervalo = data.get('intervalo')
        ativo = data.get('ativo', True)
        
        if not termo_busca:
            return jsonify({'success': False, 'message': 'Termo de busca é obrigatório'})
        
        if intervalo not in [6, 12]:
            return jsonify({'success': False, 'message': 'Intervalo deve ser 6 ou 12 horas'})
        
        # Criar agendamento
        schedule_id = db.create_schedule(user_id, termo_busca, intervalo, ativo)
        
        if schedule_id:
            # Agendar tarefa
            scheduler.schedule_search(schedule_id, termo_busca, intervalo)
            return jsonify({'success': True, 'message': 'Agendamento criado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao criar agendamento'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/schedule/update/<int:schedule_id>', methods=['POST'])
def update_schedule(schedule_id):
    """Atualizar agendamento existente"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
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
        
        if not termo_busca:
            return jsonify({'success': False, 'message': 'Termo de busca é obrigatório'})
        
        if intervalo not in [6, 12]:
            return jsonify({'success': False, 'message': 'Intervalo deve ser 6 ou 12 horas'})
        
        # Atualizar agendamento
        success = db.update_schedule(schedule_id, termo_busca, intervalo, ativo)
        
        if success:
            # Reagendar tarefa
            scheduler.reschedule_search(schedule_id, termo_busca, intervalo, ativo)
            return jsonify({'success': True, 'message': 'Agendamento atualizado com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao atualizar agendamento'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/schedule/delete/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Excluir agendamento"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
    try:
        user_id = session['user_id']
        
        # Verificar se o agendamento pertence ao usuário
        schedule = db.get_schedule_by_id(schedule_id, user_id)
        if not schedule:
            return jsonify({'success': False, 'message': 'Agendamento não encontrado'})
        
        # Excluir agendamento
        success = db.delete_schedule(schedule_id)
        
        if success:
            # Cancelar tarefa agendada
            scheduler.cancel_search(schedule_id)
            return jsonify({'success': True, 'message': 'Agendamento excluído com sucesso'})
        else:
            return jsonify({'success': False, 'message': 'Erro ao excluir agendamento'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/schedule/toggle/<int:schedule_id>', methods=['POST'])
def toggle_schedule(schedule_id):
    """Ativar/desativar agendamento"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Usuário não autenticado'})
    
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
            # Reagendar ou cancelar tarefa
            if new_status:
                scheduler.schedule_search(schedule_id, schedule['termo_busca'], schedule['intervalo_horas'])
            else:
                scheduler.cancel_search(schedule_id)
                
            return jsonify({'success': True, 'ativo': new_status})
        else:
            return jsonify({'success': False, 'message': 'Erro ao alterar status'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'})

@schedule_bp.route('/schedule/history/<int:schedule_id>')
def schedule_history(schedule_id):
    """Histórico de execuções de um agendamento"""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
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
