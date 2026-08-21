import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from supabase import create_client, Client
from werkzeug.security import generate_password_hash, check_password_hash

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
    
    def approve_products(self, user_id: str, product_ids: List[str]) -> int:
        """Aprova múltiplos produtos"""
        try:
            approved_count = 0
            
            for product_id in product_ids:
                # Busca dados do produto original
                offer_response = self.supabase.table("ofertas").select("*").eq("id", product_id).execute()
                
                if offer_response.data:
                    offer = offer_response.data[0]
                    
                    # Verifica se já não foi aprovado
                    existing = self.supabase.table("produtos_aprovados").select("id").eq("user_id", user_id).eq("oferta_id", product_id).eq("status", "ativo").execute()
                    
                    if not existing.data:
                        # Insere na tabela de aprovados
                        approval_data = {
                            "user_id": user_id,
                            "oferta_id": product_id,
                            "titulo": offer['titulo'],
                            "preco": offer['preco'],
                            "preco_numerico": offer['preco_numerico'],
                            "loja": offer['loja'],
                            "marketplace": offer['marketplace'],
                            "imagem": offer['imagem'],
                            "url_produto": offer['url_produto'],
                            "avaliacao": offer['avaliacao'],
                            "avaliacoes": offer['avaliacoes'],
                            "termo_pesquisa": offer['termo_pesquisa'],
                            "categoria_preco": offer.get('categoria_preco', ''),
                            "score_produto": offer.get('score_produto', 0),
                            "prime": offer.get('prime', False),
                            "patrocinado": offer.get('patrocinado', False),
                            "desconto_percent": offer.get('desconto_percent', 0),
                            "preco_antigo": offer.get('preco_antigo', ''),
                            "etiquetas": offer.get('etiquetas', ''),
                            "ofertas_especiais": offer.get('ofertas_especiais', ''),
                            "vendidos_mes": offer.get('vendidos_mes', ''),
                            "status": "ativo"
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

    # === MÉTODOS DE CATÁLOGOS ===

    def save_catalog(self, catalog_data: Dict) -> bool:
        """
        Salva (upsert) um catálogo na tabela catalogos.
        Se já existir pelo catalog_id, atualiza nome e imagem.
        
        Args:
            catalog_data: dict com catalog_id, nome, imagem, termo_pesquisa, user_id
        Returns:
            bool: True se salvo com sucesso
        """
        try:
            response = self.supabase.table("catalogos").upsert(
                {
                    "catalog_id": catalog_data.get("catalog_id"),
                    "nome": catalog_data.get("nome", ""),
                    "imagem": catalog_data.get("imagem", ""),
                    "termo_pesquisa": catalog_data.get("termo_pesquisa", ""),
                    "user_id": catalog_data.get("user_id"),
                    "coletado_em": datetime.now().isoformat(),
                },
                on_conflict="catalog_id"
            ).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao salvar catálogo {catalog_data.get('catalog_id')}: {e}")
            return False

    def save_catalog_sellers(self, catalog_id: str, sellers: List[Dict]) -> int:
        """
        Insere vendedores de um catálogo na tabela catalog_sellers.
        Cada coleta gera novos registros (preserva histórico temporal).
        
        Args:
            catalog_id: ID do catálogo (ex: MLB45231994)
            sellers: lista de dicts com dados de cada seller
        Returns:
            int: Número de sellers inseridos
        """
        if not sellers:
            return 0
        try:
            now = datetime.now().isoformat()
            records = []
            for s in sellers:
                records.append({
                    "catalog_id": catalog_id,
                    "seller_name": s.get("seller_name", ""),
                    "seller_id_ml": s.get("seller_id_ml", ""),
                    "preco": float(s.get("preco", 0) or 0),
                    "preco_str": s.get("preco_str", ""),
                    "frete_gratis": bool(s.get("frete_gratis", False)),
                    "frete_full": bool(s.get("frete_full", False)),
                    "reputacao": s.get("reputacao", ""),
                    "condicao": s.get("condicao", "novo"),
                    "is_best_offer": bool(s.get("is_best_offer", False)),
                    "posicao": int(s.get("posicao", 0) or 0),
                    "coletado_em": now,
                })
            response = self.supabase.table("catalog_sellers").insert(records).execute()
            return len(response.data)
        except Exception as e:
            print(f"Erro ao salvar sellers do catálogo {catalog_id}: {e}")
            return 0

    def get_catalog_sellers(self, catalog_id: str, limit: int = 50) -> List[Dict]:
        """
        Busca os sellers mais recentes de um catálogo (última coleta).
        
        Args:
            catalog_id: ID do catálogo
            limit: Número máximo de sellers
        Returns:
            List[Dict]: Lista de sellers ordenada por preço ascendente
        """
        try:
            # Busca o timestamp da coleta mais recente
            latest_response = (
                self.supabase.table("catalog_sellers")
                .select("coletado_em")
                .eq("catalog_id", catalog_id)
                .order("coletado_em", desc=True)
                .limit(1)
                .execute()
            )
            if not latest_response.data:
                return []

            latest_ts = latest_response.data[0]["coletado_em"]

            # Busca todos sellers dessa coleta, ordenados por preço
            response = (
                self.supabase.table("catalog_sellers")
                .select("*")
                .eq("catalog_id", catalog_id)
                .eq("coletado_em", latest_ts)
                .order("preco", desc=False)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            print(f"Erro ao buscar sellers do catálogo {catalog_id}: {e}")
            return []

    def get_user_catalogs(self, user_id: str, limit: int = 50) -> List[Dict]:
        """
        Lista catálogos buscados pelo usuário, ordenados por data mais recente.
        
        Args:
            user_id: ID do usuário
            limit: Número máximo de catálogos
        Returns:
            List[Dict]: Lista de catálogos
        """
        try:
            response = (
                self.supabase.table("catalogos")
                .select("*")
                .eq("user_id", user_id)
                .order("coletado_em", desc=True)
                .limit(limit)
                .execute()
            )
            return response.data or []
        except Exception as e:
            print(f"Erro ao buscar catálogos do usuário {user_id}: {e}")
            return []

    def get_catalog_by_id(self, catalog_id: str) -> Optional[Dict]:
        """
        Busca dados de um catálogo específico pelo catalog_id.
        
        Args:
            catalog_id: ID do catálogo (ex: MLB45231994)
        Returns:
            Dict ou None
        """
        try:
            response = (
                self.supabase.table("catalogos")
                .select("*")
                .eq("catalog_id", catalog_id)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Erro ao buscar catálogo {catalog_id}: {e}")
            return None

    def get_offers_by_search(self, busca_id: Optional[int] = None, termo: Optional[str] = None, limit: int = 200) -> Dict:
        """
        Recupera ofertas persistidas no Supabase a partir de um busca_id (histórico) ou termo de busca.
        Calcula estatísticas (preço médio, menor preço, contagem por marketplace).
        """
        try:
            busca_info = None
            termo_pesquisa = termo

            if busca_id:
                resp_busca = self.supabase.table("historico_buscas").select("*").eq("id", busca_id).limit(1).execute()
                if resp_busca.data:
                    busca_info = resp_busca.data[0]
                    termo_pesquisa = busca_info.get("termo_pesquisa")

            if not termo_pesquisa:
                return {'results': [], 'stats': {}, 'busca_info': None}

            # Busca ofertas salvas para esse termo (suporta busca exata ou parcial com ilike)
            query = self.supabase.table("ofertas").select("*")
            if busca_id:
                query = query.eq("termo_pesquisa", termo_pesquisa)
            else:
                query = query.ilike("termo_pesquisa", f"%{termo_pesquisa}%")

            resp_ofertas = query.order("criado_em", desc=True).limit(limit).execute()
            results = resp_ofertas.data or []

            # Se não vieram estatísticas salvas do histórico, calcula dinamicamente
            precos = [float(r.get('preco_numerico') or 0) for r in results if float(r.get('preco_numerico') or 0) > 0]
            stats = {
                'total_produtos': len(results),
                'amazon_produtos': len([r for r in results if str(r.get('marketplace', '')).lower() == 'amazon']),
                'ml_produtos': len([r for r in results if 'mercado' in str(r.get('marketplace', '')).lower()]),
                'preco_medio': round(sum(precos) / len(precos), 2) if precos else (busca_info.get('preco_medio') if busca_info else 0),
                'preco_minimo': min(precos) if precos else (busca_info.get('preco_minimo') if busca_info else 0),
                'preco_maximo': max(precos) if precos else (busca_info.get('preco_maximo') if busca_info else 0),
                'tempo_execucao': busca_info.get('tempo_execucao_segundos', 0) if busca_info else 0,
                'termo_pesquisa': termo_pesquisa
            }

            return {
                'results': results,
                'stats': stats,
                'busca_info': busca_info,
                'termo_pesquisa': termo_pesquisa
            }
        except Exception as e:
            print(f"Erro ao buscar ofertas por busca_id/termo: {e}")
            return {'results': [], 'stats': {}, 'busca_info': None, 'error': str(e)}

    def get_recent_search_terms(self, user_id: str, limit: int = 8) -> List[str]:
        """
        Retorna os termos de busca únicos mais recentes do usuário.
        """
        try:
            resp = (
                self.supabase.table("historico_buscas")
                .select("termo_pesquisa, executado_em")
                .eq("user_id", user_id)
                .order("executado_em", desc=True)
                .limit(50)
                .execute()
            )
            termos = []
            seen = set()
            for row in (resp.data or []):
                t = (row.get('termo_pesquisa') or '').strip()
                if t and t.lower() not in seen:
                    seen.add(t.lower())
                    termos.append(t)
                    if len(termos) >= limit:
                        break
            return termos
        except Exception as e:
            print(f"Erro ao buscar termos recentes: {e}")
            return []

    def extract_and_save_catalogs_from_offers(self, user_id: Optional[str] = None) -> List[Dict]:
        """
        Analisa as ofertas salvas do Mercado Livre na tabela 'ofertas',
        extrai links com padrão de catálogo (/p/MLB...) e salva na tabela 'catalogos'.
        """
        try:
            from scraping.web_scrap_catalog_ml import extract_catalog_id_from_url

            query = self.supabase.table("ofertas").select("titulo, imagem, url_produto, termo_pesquisa, criado_em")
            resp = query.order("criado_em", desc=True).limit(300).execute()
            ofertas = resp.data or []

            catalogs_found = []
            seen_ids = set()

            for item in ofertas:
                url = item.get("url_produto") or ""
                cat_id = extract_catalog_id_from_url(url)
                if cat_id and cat_id not in seen_ids:
                    seen_ids.add(cat_id)
                    catalog_data = {
                        "catalog_id": cat_id,
                        "nome": item.get("titulo") or f"Catálogo {cat_id}",
                        "imagem": item.get("imagem") or "",
                        "termo_pesquisa": item.get("termo_pesquisa") or "",
                        "user_id": user_id
                    }
                    self.save_catalog(catalog_data)
                    catalogs_found.append(catalog_data)

            print(f"✅ {len(catalogs_found)} catálogos extraídos e sincronizados das ofertas existentes")
            return catalogs_found
        except Exception as e:
            print(f"Erro ao extrair catálogos das ofertas: {e}")
            return []

    # === MÉTODOS DE SESSÃO DO MERCADO LIVRE ===

    def save_ml_session(self, cookies: List[Dict], user_email: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """
        Salva ou atualiza a sessão de cookies do Mercado Livre na tabela configuracoes.
        """
        try:
            now = datetime.now().isoformat()
            payload = {
                "cookies": cookies,
                "total_cookies": len(cookies),
                "user_email": user_email or "default",
                "updated_at": now,
                "status": "active"
            }
            # Upsert na tabela de configurações sob a chave 'ml_session_cookies'
            response = self.supabase.table("configuracoes").upsert({
                "user_id": user_id or "1",
                "chave": "ml_session_cookies",
                "valor": payload,
                "descricao": "Cookies de sessão ativa do Mercado Livre",
                "tipo": "json"
            }, on_conflict="user_id, chave").execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao salvar sessão ML: {e}")
            return False

    def get_ml_session(self, user_id: Optional[str] = None) -> Optional[Dict]:
        """
        Recupera a sessão de cookies do Mercado Livre salva no Supabase.
        """
        try:
            import json
            query = self.supabase.table("configuracoes").select("valor, atualizado_em").eq("chave", "ml_session_cookies")
            if user_id:
                query = query.eq("user_id", user_id)
            
            response = query.limit(1).execute()
            if response.data and response.data[0].get("valor"):
                val = response.data[0]["valor"]
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except Exception:
                        return None
                elif isinstance(val, dict):
                    return val
            return None
        except Exception as e:
            print(f"Erro ao buscar sessão ML: {e}")
            return None


