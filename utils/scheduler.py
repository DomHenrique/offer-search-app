import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import sys
import os

# Adiciona o diretório raiz ao path para importar módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.run_scraper import buscar_e_salvar_ofertas
from utils.evolution_api import send_message

# Import moved inside the function to avoid circular imports
# from routes.search_routes import search_status

class SchedulerManager:
    """Gerenciador de agendamentos automáticos"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.running = False
        self.thread = None
    
    def start(self):
        """Inicia o scheduler"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self.thread.start()
            print("Scheduler iniciado")
    
    def stop(self):
        """Para o scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("Scheduler parado")
    
    def is_running(self) -> bool:
        """Verifica se o scheduler está rodando"""
        return self.running and self.thread and self.thread.is_alive()
    
    def _run_scheduler(self):
        """Loop principal do scheduler"""
        while self.running:
            try:
                self.check_and_execute_schedules()
                time.sleep(300)  # Verifica a cada 5 minutos
            except Exception as e:
                print(f"Erro no scheduler: {e}")
                time.sleep(60)  # Aguarda 1 minuto em caso de erro
    
    def check_and_execute_schedules(self):
        """Verifica e executa agendamentos pendentes"""
        try:
            # Busca agendamentos que devem ser executados
            now = datetime.now()
            
            response = self.db_manager.supabase.table("agendamentos").select("*").eq("ativo", True).lte("proxima_execucao", now.isoformat()).execute()
            
            schedules_to_execute = response.data or []
            
            for schedule in schedules_to_execute:
                try:
                    self._execute_schedule(schedule)
                except Exception as e:
                    print(f"Erro ao executar agendamento {schedule['id']}: {e}")
            
            if schedules_to_execute:
                print(f"Executados {len(schedules_to_execute)} agendamentos")
        
        except Exception as e:
            print(f"Erro ao verificar agendamentos: {e}")
    
    def _execute_schedule(self, schedule: dict):
        """Executa um agendamento específico"""
        try:
            schedule_id = schedule['id']
            user_id = schedule['user_id']
            termo_pesquisa = schedule['termo_pesquisa']
            intervalo_horas = schedule['intervalo_horas']
            
            print(f"Executando agendamento {schedule_id}: '{termo_pesquisa}'")
            
            # Busca configurações do usuário
            configs = self.db_manager.get_user_configs(user_id)
            config_dict = {config['chave']: config['valor'] for config in configs}
            
            # Verifica se tem as configurações necessárias
            if not config_dict.get('SERPAPI_KEY'):
                print(f"SERPAPI_KEY não configurada para usuário {user_id}")
                return
            
            # Configura variáveis de ambiente temporariamente
            original_env = {}
            for key, value in config_dict.items():
                if value:  # Só configura se tem valor
                    original_env[key] = os.environ.get(key)
                    os.environ[key] = value
            
            try:
                # Executa a busca
                start_time = time.time()
                
                # Se termo_pesquisa estiver vazio, usa busca padrão (ofertas do dia)
                if not termo_pesquisa or termo_pesquisa.strip() == "":
                    print(f"Executando busca padrão (ofertas do dia) para agendamento {schedule_id}")
                    from scraping.run_scraper import buscar_ofertas_do_dia_ml
                    results = buscar_ofertas_do_dia_ml(paginas_ml=1)
                    termo_pesquisa = "ofertas_do_dia"  # Para histórico
                else:
                    print(f"Executando busca específica: '{termo_pesquisa}' para agendamento {schedule_id}")
                    results = buscar_e_salvar_ofertas(termo_pesquisa, paginas_ml=1)
                
                execution_time = int(time.time() - start_time)
                
                # Calcula estatísticas
                stats = {
                    'total_produtos': len(results),
                    'amazon_produtos': len([r for r in results if r.get('marketplace') == 'Amazon']),
                    'ml_produtos': len([r for r in results if r.get('marketplace') == 'MercadoLivre']),
                    'preco_medio': sum(r.get('preco_numerico', 0) for r in results) / len(results) if results else 0,
                    'preco_minimo': min(r.get('preco_numerico', 0) for r in results) if results else 0,
                    'preco_maximo': max(r.get('preco_numerico', 0) for r in results) if results else 0,
                    'tempo_execucao': execution_time
                }
                
                # Salva no histórico
                search_id = self.db_manager.save_search_history(user_id, termo_pesquisa, stats, schedule_id)
                
                # Salva os resultados no cache de status para que possam ser acessados na página de resultados
                try:
                    # Import moved inside the function to avoid circular imports
                    from routes.search_routes import search_status
                    # Store results in search_status so they can be accessed by the results page
                    search_status[str(search_id)] = {
                        'status': 'concluida',
                        'progress': 100,
                        'message': f'Busca concluída! {len(results)} produtos encontrados.',
                        'results': results,
                        'stats': stats,
                        'error': None,
                        'completed': True
                    }
                except Exception as e:
                    print(f"Erro ao salvar resultados no cache de status: {e}")
                
                # Verifica alertas
                self.check_alerts(user_id, results)

                # Atualiza próxima execução
                proxima_execucao = datetime.now() + timedelta(hours=intervalo_horas)
                
                self.db_manager.supabase.table("agendamentos").update({
                    "proxima_execucao": proxima_execucao.isoformat(),
                    "ultima_execucao": datetime.now().isoformat(),
                    "total_execucoes": schedule.get('total_execucoes', 0) + 1
                }).eq("id", schedule_id).execute()
                
                print(f"Agendamento {schedule_id} executado com sucesso: {len(results)} produtos encontrados")
            
            finally:
                # Restaura variáveis de ambiente originais
                for key, original_value in original_env.items():
                    if original_value is not None:
                        os.environ[key] = original_value
                    elif key in os.environ:
                        del os.environ[key]
        
        except Exception as e:
            print(f"Erro na execução do agendamento {schedule['id']}: {e}")
            
            # Salva erro no histórico
            try:
                self.db_manager.supabase.table("historico_buscas").insert({
                    "user_id": schedule['user_id'],
                    "termo_pesquisa": schedule['termo_pesquisa'],
                    "status": "erro",
                    "erro_mensagem": str(e),
                    "agendamento_id": schedule['id']
                }).execute()
            except:
                pass
        """Verifica se algum produto atende aos critérios de alerta"""
        try:
            alerts = self.db_manager.get_user_alerts(user_id)
            if not alerts:
                return

            for alert in alerts:
                if not alert['ativo']:
                    continue

                for product in products:
                    if alert['produto_nome'].lower() in product['titulo'].lower():
                        if alert['tipo_alerta'] == 'menor_ou_igual' and product['preco_numerico'] <= alert['preco_alvo']:
                            message = f"Alerta de preço! O produto {product['titulo']} está com preço de {product['preco']}. Link: {product['url_produto']}"
                            send_message(alert['telefone'], message)
                        elif alert['tipo_alerta'] == 'maior_ou_igual' and product['preco_numerico'] >= alert['preco_alvo']:
                            message = f"Alerta de preço! O produto {product['titulo']} está com preço de {product['preco']}. Link: {product['url_produto']}"
                            send_message(alert['telefone'], message)
        except Exception as e:
            print(f"Erro ao verificar alertas: {e}")
