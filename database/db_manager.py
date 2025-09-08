import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd

class DatabaseManager:
    """Gerenciador centralizado para operações de banco de dados"""
    
    def __init__(self):
        """Inicializa conexão com Supabase"""
        self.supabase_url = os.environ.get('SUPABASE_URL')
        self.supabase_key = os.environ.get('SUPABASE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Variáveis SUPABASE_URL e SUPABASE_KEY são obrigatórias")
        
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    def test_connection(self) -> bool:
        """Testa conexão com o banco de dados"""
        try:
            response = self.supabase.table("users").select("id").limit(1).execute()
            return True
        except Exception as e:
            print(f"Erro na conexão com banco: {e}")
            return False
    
    def salvar_ofertas(self, df_ofertas: pd.DataFrame) -> bool:
        """
        Salva um DataFrame de ofertas na tabela 'ofertas' do Supabase.
        
        Args:
            df_ofertas (pd.DataFrame): DataFrame contendo os dados das ofertas.
            
        Returns:
            bool: True se as ofertas foram salvas com sucesso, False caso contrário.
        """
        if df_ofertas.empty:
            print("Nenhum dado de oferta para salvar.")
            return True
        
        # Converte o DataFrame para uma lista de dicionários (registros)
        ofertas_para_inserir = df_ofertas.to_dict(orient='records')
        
        try:
            # Insere os dados na tabela 'ofertas'
            # Supabase pode ter um limite para o número de linhas em uma única inserção.
            # Para grandes volumes, pode ser necessário dividir em lotes.
            # Por simplicidade, vamos tentar inserir tudo de uma vez.
            response = self.supabase.table("ofertas").insert(ofertas_para_inserir).execute()
            
            # Verifica se a inserção foi bem-sucedida
            if response.data:
                print(f"✅ {len(response.data)} ofertas salvas com sucesso no Supabase.")
                return True
            else:
                print(f"⚠️ Nenhuma oferta foi salva. Resposta do Supabase: {response}")
                return False
        except Exception as e:
            print(f"❌ Erro ao salvar ofertas no Supabase: {e}")
            return False

    # === MÉTODOS DE USUÁRIO ===
    
    def create_user(self, email: str, password: str, nome: str) -> Optional[str]:
        """Cria novo usuário"""
        try:
            password_hash = generate_password_hash(password)
            
            response = self.supabase.table("users").insert({
                "email": email,
                "password_hash": password_hash,
                "nome": nome
            }).execute()
            
            if response.data:
                user_id = response.data[0]['id']
                # Cria configurações padrão para o usuário
                self._create_default_configs(user_id)
                return user_id
            
            return None
        
        except Exception as e:
            print(f"Erro ao criar usuário: {e}")
            # Check if it's a table not found error
            if "Could not find the table" in str(e):
                print("Possível causa: Tabelas do banco de dados não foram criadas.")
            return None
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """Autentica usuário"""
        try:
            response = self.supabase.table("users").select("*").eq("email", email).eq("ativo", True).execute()
            
            if response.data and len(response.data) > 0:
                user = response.data[0]
                if check_password_hash(user['password_hash'], password):
                    # Atualiza último login
                    self.supabase.table("users").update({
                        "ultimo_login": datetime.now().isoformat()
                    }).eq("id", user['id']).execute()
                    
                    return {
                        'id': user['id'],
                        'email': user['email'],
                        'nome': user['nome']
                    }
            
            return None
        
        except Exception as e:
            print(f"Erro na autenticação: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Busca usuário pelo ID"""
        try:
            response = self.supabase.table("users").select("*").eq("id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Erro ao buscar usuário por ID: {e}")
            return None

    def update_user_name(self, user_id: str, name: str) -> bool:
        """Atualiza o nome do usuário"""
        try:
            response = self.supabase.table("users").update({"nome": name}).eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao atualizar nome do usuário: {e}")
            return False

    def update_user_password(self, user_id: str, password_hash: str) -> bool:
        """Atualiza a senha do usuário"""
        try:
            response = self.supabase.table("users").update({"password_hash": password_hash}).eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao atualizar senha do usuário: {e}")
            return False

    def get_schedule_executions(self, schedule_id: int) -> List[Dict]:
        """Busca histórico de execuções de um agendamento específico"""
        try:
            response = self.supabase.table("historico_buscas").select("*").eq("agendamento_id", schedule_id).order("executado_em", desc=True).execute()
            return response.data or []
        except Exception as e:
            print(f"Erro ao buscar execuções do agendamento: {e}")
            return []

    def get_user_stats(self, user_id: str) -> Dict:
        """Busca estatísticas do usuário"""
        try:
            stats = {
                'total_searches': 0,
                'total_approved': 0,
                'active_schedules': 0,
                'active_alerts': 0
            }
            
            # Total de buscas
            searches = self.supabase.table("historico_buscas").select("id", count="exact").eq("user_id", user_id).execute()
            stats['total_searches'] = searches.count or 0
            
            # Total de produtos aprovados
            approved = self.supabase.table("produtos_aprovados").select("id", count="exact").eq("user_id", user_id).eq("status", "ativo").execute()
            stats['total_approved'] = approved.count or 0
            
            # Agendamentos ativos
            schedules = self.supabase.table("agendamentos").select("id", count="exact").eq("user_id", user_id).eq("ativo", True).execute()
            stats['active_schedules'] = schedules.count or 0
            
            # Alertas ativos
            alerts = self.supabase.table("alertas").select("id", count="exact").eq("user_id", user_id).eq("ativo", True).execute()
            stats['active_alerts'] = alerts.count or 0
            
            return stats
        
        except Exception as e:
            print(f"Erro ao buscar estatísticas: {e}")
            return {'total_searches': 0, 'total_approved': 0, 'active_schedules': 0, 'active_alerts': 0}
    
    # === MÉTODOS DE BUSCA ===
    
    def save_search_history(self, user_id: str, termo_pesquisa: str, stats: Dict, agendamento_id: Optional[int] = None) -> Optional[int]:
        """Salva histórico de busca"""
        try:
            print(f"💾 Salvando histórico de busca para usuário {user_id}, termo: {termo_pesquisa}")
            response = self.supabase.table("historico_buscas").insert({
                "user_id": user_id,
                "termo_pesquisa": termo_pesquisa,
                "total_produtos_encontrados": stats.get('total_produtos', 0),
                "marketplace_amazon": stats.get('amazon_produtos', 0),
                "marketplace_mercadolivre": stats.get('ml_produtos', 0),
                "preco_medio": stats.get('preco_medio', 0),
                "preco_minimo": stats.get('preco_minimo', 0),
                "preco_maximo": stats.get('preco_maximo', 0),
                "tempo_execucao_segundos": stats.get('tempo_execucao', 0),
                "status": "concluida",
                "agendamento_id": agendamento_id
            }).execute()
            
            if response.data:
                search_id = response.data[0]['id']
                print(f"✅ Histórico de busca salvo com ID: {search_id}")
                return search_id
            print("⚠️ Nenhum dado retornado ao salvar histórico")
            return None
        
        except Exception as e:
            print(f"❌ Erro ao salvar histórico: {e}")
            return None
    
    def get_recent_searches(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Busca histórico recente de buscas"""
        try:
            response = self.supabase.table("historico_buscas").select("*").eq("user_id", user_id).order("executado_em", desc=True).limit(limit).execute()
            return response.data or []
        
        except Exception as e:
            print(f"Erro ao buscar histórico: {e}")
            return []
    
    def delete_search_history(self, user_id: str, search_id: int) -> bool:
        """Exclui busca específica do histórico"""
        try:
            response = self.supabase.table("historico_buscas").delete().eq("user_id", user_id).eq("id", search_id).execute()
            return len(response.data) > 0
        
        except Exception as e:
            print(f"Erro ao excluir busca: {e}")
            return False
            
    def get_search_history_paginated(self, user_id: str, page: int, per_page: int) -> List[Dict]:
        """Busca histórico de buscas com paginação"""
        try:
            offset = (page - 1) * per_page
            response = self.supabase.table("historico_buscas").select("*", count="exact").eq("user_id", user_id).order("executado_em", desc=True).range(offset, offset + per_page - 1).execute()
            return response.data or []
        except Exception as e:
            print(f"Erro ao buscar histórico paginado: {e}")
            return []

    def get_search_history_count(self, user_id: str) -> int:
        """Conta o total de registros no histórico de buscas do usuário"""
        try:
            response = self.supabase.table("historico_buscas").select("id", count="exact").eq("user_id", user_id).execute()
            return response.count or 0
        except Exception as e:
            print(f"Erro ao contar histórico: {e}")
            return 0
    
    # === MÉTODOS DE PRODUTOS APROVADOS ===
    
    def approve_products(self, user_id: str, products_data: List[Dict]) -> int:
        """Aprova múltiplos produtos a partir de seus dados"""
        try:
            approved_count = 0
            
            for product_data in products_data:
                # O 'id' do produto nos resultados da busca é o 'id_oferta'
                id_oferta = product_data.get('id')
                if not id_oferta:
                    continue

                # Verifica se já não foi aprovado
                existing = self.supabase.table("produtos_aprovados").select("id").eq("user_id", user_id).eq("id_oferta", id_oferta).execute()
                
                if not existing.data:
                    # Mapeia os dados do produto para as colunas da tabela
                    approval_data = {
                        "user_id": user_id,
                        "id_oferta": id_oferta,
                        "titulo": product_data.get('titulo'),
                        "preco": product_data.get('preco'),
                        "preco_numerico": product_data.get('preco_numerico'),
                        "url_produto": product_data.get('url_produto'),
                        "imagem": product_data.get('imagem'),
                        "marketplace": product_data.get('marketplace'),
                        "termo_pesquisa": product_data.get('termo_pesquisa'),
                        "prime": product_data.get('prime', False),
                        "patrocinado": product_data.get('patrocinado', False),
                        "desconto_percent": product_data.get('desconto_percent'),
                        "preco_antigo": product_data.get('preco_antigo'),
                        "avaliacao": product_data.get('avaliacao'),
                        "avaliacoes": product_data.get('avaliacoes'),
                        "categoria_preco": product_data.get('categoria_preco'),
                        "score_produto": product_data.get('score_produto'),
                        "link_afiliado": product_data.get('link_afiliado')
                    }
                    
                    response = self.supabase.table("produtos_aprovados").insert(approval_data).execute()
                    if response.data:
                        approved_count += 1
            
            return approved_count
        
        except Exception as e:
            print(f"Erro ao aprovar produtos: {e}")
            return 0
    
    def get_approved_products(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Busca produtos aprovados"""
        try:
            response = self.supabase.table("produtos_aprovados").select("*").eq("user_id", user_id).eq("status", "ativo").order("aprovado_em", desc=True).limit(limit).execute()
            return response.data or []
        
        except Exception as e:
            print(f"Erro ao buscar produtos aprovados: {e}")
            return []
    
    def get_recent_approved_products(self, user_id: str, limit: int = 5) -> List[Dict]:
        """Busca produtos aprovados recentes"""
        return self.get_approved_products(user_id, limit)
    
    def remove_approved_product(self, user_id: str, product_id: int) -> bool:
        """Remove produto da lista de aprovados"""
        try:
            response = self.supabase.table("produtos_aprovados").update({"status": "removido"}).eq("user_id", user_id).eq("id", product_id).execute()
            return len(response.data) > 0
        
        except Exception as e:
            print(f"Erro ao remover produto aprovado: {e}")
            return False
    
    # === MÉTODOS DE AGENDAMENTO ===
    
    def create_schedule(self, user_id: str, termo_pesquisa: str, intervalo_horas: int) -> Optional[int]:
        """Cria novo agendamento"""
        try:
            if intervalo_horas not in [6, 12]:
                raise ValueError("Intervalo deve ser 6 ou 12 horas")
            
            proxima_execucao = datetime.now() + timedelta(hours=intervalo_horas)
            
            response = self.supabase.table("agendamentos").insert({
                "user_id": user_id,
                "termo_pesquisa": termo_pesquisa,
                "intervalo_horas": intervalo_horas,
                "proxima_execucao": proxima_execucao.isoformat(),
                "ativo": True
            }).execute()
            
            if response.data:
                return response.data[0]['id']
            return None
        
        except Exception as e:
            print(f"Erro ao criar agendamento: {e}")
            return None
    
    def get_active_schedules(self, user_id: str) -> List[Dict]:
        """Busca agendamentos ativos"""
        try:
            response = self.supabase.table("agendamentos").select("*").eq("user_id", user_id).eq("ativo", True).order("criado_em", desc=True).execute()
            return response.data or []
        
        except Exception as e:
            print(f"Erro ao buscar agendamentos: {e}")
            return []
    
    def update_schedule(self, user_id: str, schedule_id: int, termo_pesquisa: str, intervalo_horas: int) -> bool:
        """Atualiza agendamento"""
        try:
            if intervalo_horas not in [6, 12]:
                raise ValueError("Intervalo deve ser 6 ou 12 horas")
            
            proxima_execucao = datetime.now() + timedelta(hours=intervalo_horas)
            
            response = self.supabase.table("agendamentos").update({
                "termo_pesquisa": termo_pesquisa,
                "intervalo_horas": intervalo_horas,
                "proxima_execucao": proxima_execucao.isoformat()
            }).eq("user_id", user_id).eq("id", schedule_id).execute()
            
            return len(response.data) > 0
        
        except Exception as e:
            print(f"Erro ao atualizar agendamento: {e}")
            return False
    
    def delete_schedule(self, user_id: str, schedule_id: int) -> bool:
        """Exclui agendamento"""
        try:
            response = self.supabase.table("agendamentos").update({"ativo": False}).eq("user_id", user_id).eq("id", schedule_id).execute()
            return len(response.data) > 0
        
        except Exception as e:
            print(f"Erro ao excluir agendamento: {e}")
            return False
    
    def get_schedule_by_id(self, schedule_id: int, user_id: str) -> Optional[Dict]:
        """Busca um agendamento específico pelo ID, verificando se pertence ao usuário"""
        try:
            response = self.supabase.table("agendamentos").select("*").eq("id", schedule_id).eq("user_id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Erro ao buscar agendamento por ID: {e}")
            return None

    # === MÉTODOS DE ALERTAS ===

    def get_user_alerts(self, user_id: str) -> List[Dict]:
        """Busca todos os alertas de um usuário"""
        try:
            response = self.supabase.table("alertas").select("*").eq("user_id", user_id).order("criado_em", desc=True).execute()
            return response.data or []
        except Exception as e:
            print(f"Erro ao buscar alertas: {e}")
            return []

    def get_alert_by_id(self, alert_id: int, user_id: str) -> Optional[Dict]:
        """Busca um alerta específico pelo ID, verificando se pertence ao usuário"""
        try:
            response = self.supabase.table("alertas").select("*").eq("id", alert_id).eq("user_id", user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Erro ao buscar alerta por ID: {e}")
            return None

    def create_price_alert(self, user_id: str, produto_nome: str, preco_alvo: float, tipo_alerta: str, ativo: bool, telefone: str) -> Optional[int]:
        """Cria um novo alerta de preço"""
        try:
            response = self.supabase.table("alertas").insert({
                "user_id": user_id,
                "produto_nome": produto_nome,
                "preco_alvo": preco_alvo,
                "tipo_alerta": tipo_alerta,
                "ativo": ativo,
                "telefone": telefone
            }).execute()
            return response.data[0]['id'] if response.data else None
        except Exception as e:
            print(f"Erro ao criar alerta: {e}")
            return None

    def update_price_alert(self, alert_id: int, produto_nome: str, preco_alvo: float, tipo_alerta: str, ativo: bool, telefone: str) -> bool:
        """Atualiza um alerta de preço existente"""
        try:
            response = self.supabase.table("alertas").update({
                "produto_nome": produto_nome,
                "preco_alvo": preco_alvo,
                "tipo_alerta": tipo_alerta,
                "ativo": ativo,
                "telefone": telefone
            }).eq("id", alert_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao atualizar alerta: {e}")
            return False

    def delete_price_alert(self, alert_id: int) -> bool:
        """Exclui um alerta de preço"""
        try:
            response = self.supabase.table("alertas").delete().eq("id", alert_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao excluir alerta: {e}")
            return False

    # === MÉTODOS DE CONFIGURAÇÃO ===
    
    def _create_default_configs(self, user_id: str):
        """Cria configurações padrão para novo usuário"""
        default_configs = [
            {"chave": "SERPAPI_KEY", "valor": os.environ.get("SERPAPI_KEY", ""), "descricao": "Chave da API do SerpAPI para busca na Amazon", "tipo": "password", "obrigatorio": True},
            {"chave": "SUPABASE_URL", "valor": os.environ.get("SUPABASE_URL", ""), "descricao": "URL do projeto Supabase", "tipo": "string", "obrigatorio": True},
            {"chave": "SUPABASE_KEY", "valor": os.environ.get("SUPABASE_KEY", ""), "descricao": "Chave de serviço do Supabase", "tipo": "password", "obrigatorio": True}
        ]
        
        for config in default_configs:
            config["user_id"] = user_id
            try:
                self.supabase.table("configuracoes").insert(config).execute()
            except:
                pass  # Ignora se já existe
    
    def get_user_configs(self, user_id: str) -> List[Dict]:
        """Busca configurações do usuário"""
        try:
            response = self.supabase.table("configuracoes").select("*").eq("user_id", user_id).order("chave").execute()
            return response.data or []
        
        except Exception as e:
            print(f"Erro ao buscar configurações: {e}")
            return []

    def save_user_config(self, user_id: str, key: str, value: Any) -> bool:
        """Salva ou atualiza uma configuração de usuário."""
        try:
            # Tenta atualizar primeiro
            response = self.supabase.table("configuracoes").update({"valor": value}).eq("user_id", user_id).eq("chave", key).execute()
            
            # Se nada foi atualizado, insere um novo registro
            if not response.data:
                self.supabase.table("configuracoes").insert({
                    "user_id": user_id,
                    "chave": key,
                    "valor": value,
                    "descricao": f"Configuração para {key}",
                    "tipo": "string" 
                }).execute()
                
            return True
        except Exception as e:
            print(f"Erro ao salvar configuração: {e}")
            return False
    
    def update_config(self, user_id: str, chave: str, valor: str) -> bool:
        """Atualiza configuração específica"""
        try:
            response = self.supabase.table("configuracoes").update({"valor": valor}).eq("user_id", user_id).eq("chave", chave).execute()
            return len(response.data) > 0
        
        except Exception as e:
            print(f"Erro ao atualizar configuração: {e}")
            return False

    def get_notification_settings(self, user_id: str) -> Optional[Dict]:
        """Busca as configurações de notificação do usuário"""
        try:
            response = self.supabase.table("configuracoes").select("valor").eq("user_id", user_id).eq("chave", "notification_settings").execute()
            if response.data:
                return response.data[0]['valor']
            return None
        except Exception as e:
            print(f"Erro ao buscar configurações de notificação: {e}")
            return None

    def update_notification_settings(self, user_id: str, settings: Dict) -> bool:
        """Atualiza as configurações de notificação do usuário"""
        try:
            # Upsert (Update or Insert)
            response = self.supabase.table("configuracoes").upsert({
                "user_id": user_id,
                "chave": "notification_settings",
                "valor": settings,
                "descricao": "Configurações de notificação do usuário",
                "tipo": "json"
            }).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao atualizar configurações de notificação: {e}")
            return False
