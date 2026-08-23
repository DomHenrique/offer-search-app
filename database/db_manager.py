import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Union
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
    
    # === MÉTODOS DE USUÁRIO E EQUIPE ===
    
    def create_user(self, email: str, password: str, nome: str, role: str = "member", cargo: str = "", telefone: str = "") -> Optional[str]:
        """Cria novo usuário com suporte a role, cargo e telefone"""
        try:
            password_hash = generate_password_hash(password)
            
            payload = {
                "email": email.strip().lower(),
                "password_hash": password_hash,
                "nome": nome.strip()
            }
            if role:
                payload["role"] = role
            if cargo:
                payload["cargo"] = cargo
            if telefone:
                payload["telefone"] = telefone

            response = self.supabase.table("users").insert(payload).execute()
            
            if response.data:
                user_id = response.data[0]['id']
                self._create_default_configs(user_id)
                return user_id
            
            return None
        
        except Exception as e:
            # Fallback caso colunas opcionais (role, cargo, telefone) ainda não existam no schema
            if any(col in str(e) for col in ["role", "cargo", "telefone", "PGRST204"]):
                try:
                    response = self.supabase.table("users").insert({
                        "email": email.strip().lower(),
                        "password_hash": generate_password_hash(password),
                        "nome": nome.strip()
                    }).execute()
                    if response.data:
                        user_id = response.data[0]['id']
                        self._create_default_configs(user_id)
                        return user_id
                except Exception as e2:
                    print(f"Erro no fallback de criação de usuário: {e2}")
            print(f"Erro ao criar usuário: {e}")
            return None
    
    def authenticate_user(self, email: str, password: str) -> Optional[Dict]:
        """Autentica usuário e retorna dados com perfil/role"""
        try:
            response = self.supabase.table("users").select("*").eq("email", email.strip().lower()).eq("ativo", True).execute()
            
            if response.data and len(response.data) > 0:
                user = response.data[0]
                if check_password_hash(user['password_hash'], password):
                    # Atualiza último login
                    try:
                        self.supabase.table("users").update({
                            "ultimo_login": datetime.now().isoformat()
                        }).eq("id", user['id']).execute()
                    except Exception:
                        pass
                    
                    return {
                        'id': user['id'],
                        'email': user['email'],
                        'nome': user['nome'],
                        'role': user.get('role') or ('admin' if user['id'] in (1, '1') else 'member'),
                        'cargo': user.get('cargo') or '',
                        'telefone': user.get('telefone') or ''
                    }
            
            return None
        
        except Exception as e:
            print(f"Erro na autenticação: {e}")
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """Busca usuário pelo ID"""
        try:
            response = self.supabase.table("users").select("*").eq("id", user_id).execute()
            if response.data:
                u = response.data[0]
                u['role'] = u.get('role') or ('admin' if str(u.get('id')) == '1' else 'member')
                return u
            return None
        except Exception as e:
            print(f"Erro ao buscar usuário por ID: {e}")
            return None

    def is_user_admin(self, user_id: str) -> bool:
        """Verifica se o usuário tem privilégios de administrador"""
        try:
            user = self.get_user_by_id(user_id)
            if not user:
                return False
            role = str(user.get('role', '')).lower()
            return role == 'admin' or str(user.get('id')) in ('1', 1)
        except Exception:
            return False

    def get_all_team_members(self) -> List[Dict]:
        """Retorna lista de todos os membros da equipe"""
        try:
            response = self.supabase.table("users").select("*").order("id", desc=False).execute()
            members = response.data or []
            for m in members:
                m['role'] = m.get('role') or ('admin' if str(m.get('id')) == '1' else 'member')
                m['cargo'] = m.get('cargo') or ('Administrador' if m['role'] == 'admin' else 'Membro da Equipe')
                m['telefone'] = m.get('telefone') or ''
                # Remove o hash da senha por segurança
                if 'password_hash' in m:
                    del m['password_hash']
            return members
        except Exception as e:
            print(f"Erro ao listar membros da equipe: {e}")
            return []

    def update_user_profile(self, user_id: str, nome: str, cargo: Optional[str] = None, telefone: Optional[str] = None) -> bool:
        """Atualiza dados cadastrais do perfil do usuário"""
        try:
            payload = {"nome": nome.strip()}
            if cargo is not None:
                payload["cargo"] = cargo.strip()
            if telefone is not None:
                payload["telefone"] = telefone.strip()

            response = self.supabase.table("users").update(payload).eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            # Fallback caso colunas opcionais não existam
            if any(col in str(e) for col in ["cargo", "telefone", "PGRST204"]):
                try:
                    response = self.supabase.table("users").update({"nome": nome.strip()}).eq("id", user_id).execute()
                    return len(response.data) > 0
                except Exception:
                    pass
            print(f"Erro ao atualizar perfil do usuário: {e}")
            return False

    def update_team_member(self, user_id: str, nome: Optional[str] = None, role: Optional[str] = None, cargo: Optional[str] = None, telefone: Optional[str] = None, ativo: Optional[bool] = None) -> bool:
        """Atualiza informações de um membro da equipe (Ação administrativa)"""
        try:
            payload = {}
            if nome is not None:
                payload["nome"] = nome.strip()
            if role is not None:
                payload["role"] = role.strip()
            if cargo is not None:
                payload["cargo"] = cargo.strip()
            if telefone is not None:
                payload["telefone"] = telefone.strip()
            if ativo is not None:
                payload["ativo"] = bool(ativo)

            if not payload:
                return True

            response = self.supabase.table("users").update(payload).eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao atualizar membro da equipe: {e}")
            return False

    def reset_user_password(self, user_id: str, new_password: str) -> bool:
        """Redefine a senha de um usuário"""
        try:
            password_hash = generate_password_hash(new_password)
            response = self.supabase.table("users").update({"password_hash": password_hash}).eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao redefinir senha do usuário: {e}")
            return False

    def delete_team_member(self, user_id: str, requesting_user_id: str) -> bool:
        """Exclui um membro da equipe (com proteção contra auto-exclusão)"""
        if str(user_id) == str(requesting_user_id):
            print("⚠️ Auto-exclusão não permitida.")
            return False
        try:
            response = self.supabase.table("users").delete().eq("id", user_id).execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao excluir membro da equipe: {e}")
            return False

    def update_user_name(self, user_id: str, name: str) -> bool:
        """Atualiza o nome do usuário"""
        return self.update_user_profile(user_id, nome=name)

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
            cid = str(catalog_data.get("catalog_id") or "")
            uid = catalog_data.get("user_id")
            if uid is not None:
                try:
                    uid = int(uid)
                except Exception:
                    uid = None

            record = {
                "catalog_id": cid,
                "nome": catalog_data.get("nome") or catalog_data.get("titulo") or f"Catálogo {cid}",
                "imagem": catalog_data.get("imagem") or catalog_data.get("imagem_url") or "",
                "termo_pesquisa": catalog_data.get("termo_pesquisa") or "",
                "user_id": uid,
                "coletado_em": datetime.now().isoformat(),
            }

            response = self.supabase.table("catalogos").upsert(
                record,
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
            if response.data:
                cat = response.data[0]
                cid = cat.get("catalog_id", "")
                is_amz = not cid.startswith("MLB")
                cat["marketplace"] = "Amazon" if is_amz else "MercadoLivre"
                cat["url_produto"] = cat.get("url_produto") or (f"https://www.amazon.com.br/dp/{cid}" if is_amz else f"https://www.mercadolivre.com.br/p/{cid}")
                cat["titulo"] = cat.get("titulo") or cat.get("nome", "")
                cat["imagem_url"] = cat.get("imagem_url") or cat.get("imagem", "")
                return cat
            return None
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

    def delete_offers_by_ids(self, offer_ids: List[Union[int, str]]) -> int:
        """
        Exclui ofertas da tabela 'ofertas' pelos seus IDs.
        """
        if not offer_ids:
            return 0
        try:
            # Converte IDs válidos
            cleaned_ids = [int(i) for i in offer_ids if str(i).isdigit()]
            if not cleaned_ids:
                return 0
            
            resp = self.supabase.table("ofertas").delete().in_("id", cleaned_ids).execute()
            deleted = len(resp.data) if hasattr(resp, 'data') and resp.data else len(cleaned_ids)
            print(f"🗑️ [DB] {deleted} ofertas excluídas por ID do Supabase.")
            return deleted
        except Exception as e:
            print(f"❌ [DB] Erro ao excluir ofertas por ID: {e}")
            return 0

    def delete_offers_by_urls(self, urls: List[str]) -> int:
        """
        Exclui ofertas da tabela 'ofertas' pelas suas URLs de produto.
        """
        if not urls:
            return 0
        try:
            cleaned_urls = [u.strip() for u in urls if u and u.strip()]
            if not cleaned_urls:
                return 0
                
            resp = self.supabase.table("ofertas").delete().in_("url_produto", cleaned_urls).execute()
            deleted = len(resp.data) if hasattr(resp, 'data') and resp.data else len(cleaned_urls)
            print(f"🗑️ [DB] {deleted} ofertas excluídas por URL do Supabase.")
            return deleted
        except Exception as e:
            print(f"❌ [DB] Erro ao excluir ofertas por URL: {e}")
            return 0

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
        Analisa as ofertas salvas na tabela 'ofertas',
        extrai exclusivamente catálogos confirmados (/p/MLB... do Mercado Livre) e salva na tabela 'catalogos'.
        """
        try:
            import re
            from scraping.web_scrap_catalog_ml import extract_catalog_id_from_url

            query = self.supabase.table("ofertas").select("titulo, imagem, url_produto, termo_pesquisa, marketplace, criado_em")
            resp = query.order("criado_em", desc=True).limit(500).execute()
            ofertas = resp.data or []

            catalogs_found = []
            seen_ids = set()

            for item in ofertas:
                url = item.get("url_produto") or ""
                mp = item.get("marketplace") or "MercadoLivre"
                
                # Apenas produtos com /p/MLB... no ML são catálogos garantidos
                cat_id = None
                if mp == "MercadoLivre" or "mercadolivre.com" in url.lower():
                    cat_id = extract_catalog_id_from_url(url)
                    mp = "MercadoLivre"

                if cat_id and cat_id not in seen_ids:
                    seen_ids.add(cat_id)
                    catalog_data = {
                        "catalog_id": cat_id,
                        "nome": item.get("titulo") or f"Catálogo {cat_id}",
                        "titulo": item.get("titulo") or f"Catálogo {cat_id}",
                        "imagem": item.get("imagem") or "",
                        "imagem_url": item.get("imagem") or "",
                        "url_produto": url,
                        "marketplace": mp,
                        "termo_pesquisa": item.get("termo_pesquisa") or "",
                        "user_id": user_id or "1"
                    }
                    self.save_catalog(catalog_data)
                    catalogs_found.append(catalog_data)

            print(f"✅ {len(catalogs_found)} catálogos oficiais extraídos das ofertas existentes")
            return catalogs_found
        except Exception as e:
            print(f"Erro ao extrair catálogos das ofertas: {e}")
            return []

    def cleanup_single_seller_catalogs(self) -> int:
        """
        Remove catálogos da Amazon que possuem 1 ou nenhum vendedor concorrente,
        mantendo a aba de catálogos apenas com produtos que possuem concorrência ativa.
        """
        try:
            resp_cats = self.supabase.table("catalogos").select("catalog_id").execute()
            cats = resp_cats.data or []
            removed_count = 0

            for c in cats:
                cid = c.get("catalog_id", "")
                if not cid.startswith("MLB"): # É ASIN Amazon
                    sellers = self.get_catalog_sellers(cid)
                    if len(sellers) <= 1:
                        self.supabase.table("catalog_sellers").delete().eq("catalog_id", cid).execute()
                        self.supabase.table("catalogos").delete().eq("catalog_id", cid).execute()
                        removed_count += 1

            print(f"🧹 Limpeza concluída: {removed_count} catálogos de vendedor único removidos.")
            return removed_count
        except Exception as e:
            print(f"Erro na limpeza de catálogos: {e}")
            return 0

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

    # === MÉTODOS DE SESSÃO DA AMAZON ===

    def save_amazon_session(self, cookies: List[Dict], user_email: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """
        Salva ou atualiza a sessão de cookies da Amazon na tabela configuracoes.
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
            # Upsert na tabela de configurações sob a chave 'amazon_session_cookies'
            response = self.supabase.table("configuracoes").upsert({
                "user_id": user_id or "1",
                "chave": "amazon_session_cookies",
                "valor": payload,
                "descricao": "Cookies de sessão ativa da Amazon Brasil",
                "tipo": "json"
            }, on_conflict="user_id, chave").execute()
            return len(response.data) > 0
        except Exception as e:
            print(f"Erro ao salvar sessão Amazon: {e}")
            return False

    def get_amazon_session(self, user_id: Optional[str] = None) -> Optional[Dict]:
        """
        Recupera a sessão de cookies da Amazon salva no Supabase.
        """
        try:
            import json
            query = self.supabase.table("configuracoes").select("valor, atualizado_em").eq("chave", "amazon_session_cookies")
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
            print(f"Erro ao buscar sessão Amazon: {e}")
            return None

    # === MÉTODOS DE PEDIDOS DE COMPRA E ESTOQUE CONSOLIDADO ===

    def create_purchase_order(self, user_id: str, numero_pedido: str, fornecedor: Optional[str] = None, 
                              observacoes: Optional[str] = None, itens: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Cria um novo pedido de compra e seus itens associados.
        """
        try:
            order_data = {
                "user_id": user_id,
                "numero_pedido": (numero_pedido or "PED-SEM-NUMERO").strip(),
                "fornecedor": (fornecedor or "").strip(),
                "observacoes": (observacoes or "").strip()
            }
            order_res = self.supabase.table("pedidos_compra").insert(order_data).execute()
            if not order_res.data:
                return None
            
            created_order = order_res.data[0]
            order_id = created_order["id"]

            if itens and len(itens) > 0:
                items_payload = []
                for item in itens:
                    sku = str(item.get("sku") or "").strip().upper()
                    descricao = str(item.get("descricao") or item.get("nome") or sku).strip()
                    if not sku:
                        continue
                    
                    qtd = int(item.get("quantidade") or item.get("qtd") or 1)
                    preco_custo = float(item.get("preco_custo") or 0) if item.get("preco_custo") is not None else None
                    preco_revenda = float(item.get("preco_revenda") or item.get("preco_marketplace") or 0) if item.get("preco_revenda") or item.get("preco_marketplace") else None
                    preco_site_pix = float(item.get("preco_site_pix") or 0) if item.get("preco_site_pix") else None
                    ncm = str(item.get("ncm") or "").strip()
                    link_produto = str(item.get("link_produto") or item.get("link") or "").strip()

                    items_payload.append({
                        "pedido_id": order_id,
                        "sku": sku,
                        "descricao": descricao,
                        "ncm": ncm,
                        "quantidade": qtd,
                        "preco_custo": preco_custo,
                        "preco_revenda": preco_revenda,
                        "preco_site_pix": preco_site_pix,
                        "link_produto": link_produto
                    })
                
                if items_payload:
                    self.supabase.table("itens_pedido").insert(items_payload).execute()
            
            return created_order
        except Exception as e:
            print(f"Erro ao criar pedido de compra: {e}")
            return None

    def get_purchase_orders(self, user_id: str) -> List[Dict]:
        """
        Retorna a lista de pedidos de compra do usuário com estatísticas de itens.
        """
        try:
            orders_res = self.supabase.table("pedidos_compra").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            orders = orders_res.data or []

            # Busca contagem de itens por pedido
            for order in orders:
                items_res = self.supabase.table("itens_pedido").select("id, quantidade, preco_revenda").eq("pedido_id", order["id"]).execute()
                items = items_res.data or []
                order["total_itens_diferentes"] = len(items)
                order["total_quantidade_produtos"] = sum(int(it.get("quantidade") or 0) for it in items)
            
            return orders
        except Exception as e:
            print(f"Erro ao buscar pedidos de compra: {e}")
            return []

    def get_purchase_order_by_id(self, pedido_id: str, user_id: str) -> Optional[Dict]:
        """
        Retorna os detalhes de um pedido específico e todos os seus itens.
        """
        try:
            order_res = self.supabase.table("pedidos_compra").select("*").eq("id", pedido_id).eq("user_id", user_id).limit(1).execute()
            if not order_res.data:
                return None
            
            order = order_res.data[0]
            items_res = self.supabase.table("itens_pedido").select("*").eq("pedido_id", pedido_id).order("sku").execute()
            order["itens"] = items_res.data or []
            order["total_quantidade"] = sum(int(it.get("quantidade") or 0) for it in order["itens"])
            return order
        except Exception as e:
            print(f"Erro ao buscar pedido por ID: {e}")
            return None

    def delete_purchase_order(self, pedido_id: str, user_id: str) -> bool:
        """
        Exclui um pedido de compra (itens são excluídos via cascade).
        """
        try:
            res = self.supabase.table("pedidos_compra").delete().eq("id", pedido_id).eq("user_id", user_id).execute()
            return len(res.data) > 0
        except Exception as e:
            print(f"Erro ao excluir pedido: {e}")
            return False

    def get_consolidated_inventory(self, user_id: str) -> List[Dict]:
        """
        Retorna o estoque consolidado de produtos agrupado por SKU para o usuário,
        somando as quantidades de todos os pedidos de compra.
        """
        try:
            # 1. Busca todos os pedidos do usuário
            orders_res = self.supabase.table("pedidos_compra").select("id, numero_pedido, fornecedor, created_at").eq("user_id", user_id).execute()
            orders = orders_res.data or []
            if not orders:
                return []
            
            order_map = {o["id"]: o for o in orders}
            order_ids = list(order_map.keys())

            # 2. Busca todos os itens desses pedidos
            items_res = self.supabase.table("itens_pedido").select("*").in_("pedido_id", order_ids).execute()
            items = items_res.data or []

            # 3. Consolidação por SKU
            inventory_by_sku: Dict[str, Dict] = {}
            for item in items:
                sku = str(item.get("sku") or "").strip().upper()
                if not sku:
                    continue
                
                qtd = int(item.get("quantidade") or 0)
                ped_info = order_map.get(item.get("pedido_id"))

                if sku not in inventory_by_sku:
                    inventory_by_sku[sku] = {
                        "sku": sku,
                        "descricao": item.get("descricao") or sku,
                        "ncm": item.get("ncm") or "",
                        "quantidade_total": 0,
                        "preco_custo": item.get("preco_custo"),
                        "preco_revenda": item.get("preco_revenda"),
                        "preco_site_pix": item.get("preco_site_pix"),
                        "link_produto": item.get("link_produto"),
                        "pedidos": []
                    }
                
                # Se o item atual tem informações de preço mais completas, atualiza
                if item.get("preco_revenda"):
                    inventory_by_sku[sku]["preco_revenda"] = item.get("preco_revenda")
                if item.get("preco_site_pix"):
                    inventory_by_sku[sku]["preco_site_pix"] = item.get("preco_site_pix")
                if item.get("ncm") and not inventory_by_sku[sku]["ncm"]:
                    inventory_by_sku[sku]["ncm"] = item.get("ncm")
                if item.get("link_produto") and not inventory_by_sku[sku]["link_produto"]:
                    inventory_by_sku[sku]["link_produto"] = item.get("link_produto")

                inventory_by_sku[sku]["quantidade_total"] += qtd
                if ped_info:
                    inventory_by_sku[sku]["pedidos"].append({
                        "pedido_id": ped_info["id"],
                        "numero_pedido": ped_info["numero_pedido"],
                        "fornecedor": ped_info.get("fornecedor"),
                        "quantidade": qtd
                    })

            # 4. Busca os catálogos vinculados a cada SKU
            try:
                cat_links = self.get_sku_catalogs(user_id)
                cat_by_sku: Dict[str, List] = {}
                for cl in cat_links:
                    s = str(cl.get("sku") or "").strip().upper()
                    if s not in cat_by_sku:
                        cat_by_sku[s] = []
                    cat_by_sku[s].append(cl)
                
                for sku, inv_item in inventory_by_sku.items():
                    inv_item["catalogs"] = cat_by_sku.get(sku, [])
            except Exception as e:
                print(f"Aviso ao carregar catálogos do inventário: {e}")
                for sku, inv_item in inventory_by_sku.items():
                    inv_item["catalogs"] = []

            # Retorna como lista ordenada por SKU
            return sorted(list(inventory_by_sku.values()), key=lambda x: x["sku"])
        except Exception as e:
            print(f"Erro ao consolidar estoque: {e}")
            return []

    # === MÉTODOS DE VINCULAÇÃO DE CATÁLOGOS POR SKU (1-para-N) ===

    def link_catalog_to_sku(self, user_id: str, sku: str, catalog_id: str,
                            catalog_title: str = '', catalog_url: str = '',
                            catalog_image: str = '', buybox_winner: str = '',
                            buybox_min_price: float = 0.0, sellers_count: int = 1) -> Dict:
        """
        Vincula um catálogo do Mercado Livre a um SKU do inventário (relação 1 SKU para N Catálogos).
        """
        sku = str(sku).strip().upper()
        catalog_id = str(catalog_id).strip().upper()
        if not sku or not catalog_id:
            raise ValueError("SKU e Catalog ID são obrigatórios.")

        payload = {
            "user_id": user_id,
            "sku": sku,
            "catalog_id": catalog_id,
            "catalog_title": catalog_title or f"Catálogo {catalog_id}",
            "catalog_url": catalog_url or f"https://www.mercadolivre.com.br/p/{catalog_id}",
            "catalog_image": catalog_image or '',
            "buybox_winner": buybox_winner or 'Vendedor Oficial',
            "buybox_min_price": float(buybox_min_price or 0.0),
            "sellers_count": int(sellers_count or 1),
            "updated_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        try:
            # Tenta upsert na tabela sku_catalogs
            res = self.supabase.table("sku_catalogs").upsert(payload, on_conflict="user_id,sku,catalog_id").execute()
            if res.data:
                return res.data[0]
            return payload
        except Exception as e:
            print(f"Erro ao salvar link em sku_catalogs no Supabase: {e}")
            # Tenta insert simples se upsert falhar por índice
            try:
                res_ins = self.supabase.table("sku_catalogs").insert(payload).execute()
                if res_ins.data:
                    return res_ins.data[0]
            except Exception as e_ins:
                print(f"Falha secundária em insert sku_catalogs: {e_ins}")
            return payload

    def get_sku_catalogs(self, user_id: str, sku: Optional[str] = None) -> List[Dict]:
        """
        Retorna os catálogos vinculados a um SKU específico ou a todos os SKUs do usuário.
        """
        try:
            query = self.supabase.table("sku_catalogs").select("*").eq("user_id", user_id)
            if sku:
                query = query.eq("sku", str(sku).strip().upper())
            res = query.order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            print(f"Aviso ao consultar sku_catalogs: {e}")
            return []

    def unlink_catalog_from_sku(self, user_id: str, sku: str, catalog_id: str) -> bool:
        """
        Remove a vinculação de um catálogo com um SKU do inventário.
        """
        try:
            res = (self.supabase.table("sku_catalogs")
                   .delete()
                   .eq("user_id", user_id)
                   .eq("sku", str(sku).strip().upper())
                   .eq("catalog_id", str(catalog_id).strip().upper())
                   .execute())
            return True
        except Exception as e:
            print(f"Erro ao desvincular catálogo do SKU: {e}")
            return False

    def get_previous_search_identifiers(self, user_id: str, search_term: str) -> set:
        """
        Recupera os identificadores (URLs e catalog_ids) da pesquisa anterior mais recente
        para o mesmo termo/usuário, para fazer o diff e identificar os produtos novos.
        """
        try:
            clean_term = search_term.strip()
            if not clean_term:
                return set()

            # Busca ofertas salvas para esse termo no histórico
            resp = (self.supabase.table("ofertas")
                    .select("url_produto, titulo")
                    .ilike("termo_pesquisa", f"%{clean_term}%")
                    .limit(200)
                    .execute())
            
            identifiers = set()
            for item in (resp.data or []):
                u = item.get('url_produto') or ''
                if u:
                    identifiers.add(u.strip())
                    # Extrai catalog_id se presente
                    match_cat = re.search(r'/p/(MLB\d+)', u)
                    if match_cat:
                        identifiers.add(match_cat.group(1).upper())
            return identifiers
        except Exception as e:
            print(f"Aviso ao buscar identificadores anteriores para diff: {e}")
            return set()

    # ─── Sistema de Logs de Busca e Auditoria ─────────────────────────────────

    def save_search_log(self, log_data: Dict[str, Any]) -> bool:
        """
        Registra um log de auditoria de busca no banco de dados.
        Campos esperados:
          - user_id: str
          - user_email: str
          - termo_original: str
          - termo_utilizado: str
          - status: 'SUCCESS' | 'EMPTY' | 'ERROR' | 'FALLBACK_RECOVERED'
          - total_ofertas: int
          - ml_ofertas: int
          - amazon_ofertas: int
          - tempo_execucao_segundos: float
          - error_message: str (opcional)
        """
        try:
            raw_uid = log_data.get('user_id')
            # Se não for UUID com hifens (36 chars), define como None para nao violar o tipo UUID no postgres
            valid_uuid = str(raw_uid) if raw_uid and len(str(raw_uid)) == 36 and '-' in str(raw_uid) else None

            payload = {
                'user_id': valid_uuid,
                'user_email': log_data.get('user_email') or 'admin@local',
                'termo_original': str(log_data.get('termo_original') or '').strip(),
                'termo_utilizado': str(log_data.get('termo_utilizado') or '').strip(),
                'status': log_data.get('status') or 'SUCCESS',
                'total_ofertas': int(log_data.get('total_ofertas') or 0),
                'ml_ofertas': int(log_data.get('ml_ofertas') or 0),
                'amazon_ofertas': int(log_data.get('amazon_ofertas') or 0),
                'tempo_execucao_segundos': float(log_data.get('tempo_execucao_segundos') or 0.0),
                'error_message': log_data.get('error_message'),
                'created_at': datetime.utcnow().isoformat()
            }

            res = self.supabase.table("search_logs").insert(payload).execute()
            return bool(res.data)
        except Exception as e:
            print(f"ℹ️ Erro ao gravar search_logs no Supabase: {e}")
            return False

    def get_search_logs(self, user_id: Optional[str] = None, status_filter: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Retorna a lista de logs de busca com paginação e filtros.
        """
        try:
            query = self.supabase.table("search_logs").select("*")
            if user_id:
                query = query.eq("user_id", user_id)
            if status_filter and status_filter != 'ALL':
                query = query.eq("status", status_filter)

            res = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
            return res.data or []
        except Exception as e:
            print(f"Erro ao buscar search_logs: {e}")
            return []

    def get_search_logs_stats(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas consolidadas de logs de busca.
        """
        try:
            query = self.supabase.table("search_logs").select("status, total_ofertas, tempo_execucao_segundos")
            if user_id:
                query = query.eq("user_id", user_id)
            res = query.limit(500).execute()
            data = res.data or []

            total = len(data)
            success_count = sum(1 for d in data if d.get('status') in ['SUCCESS', 'FALLBACK_RECOVERED'])
            empty_count = sum(1 for d in data if d.get('status') == 'EMPTY' or (d.get('total_ofertas') or 0) == 0)
            error_count = sum(1 for d in data if d.get('status') == 'ERROR')
            recovered_count = sum(1 for d in data if d.get('status') == 'FALLBACK_RECOVERED')
            avg_time = (sum(d.get('tempo_execucao_segundos', 0) for d in data) / total) if total > 0 else 0.0

            success_rate = (success_count / total * 100) if total > 0 else 100.0

            return {
                'total_buscas': total,
                'sucesso_count': success_count,
                'empty_count': empty_count,
                'error_count': error_count,
                'recovered_count': recovered_count,
                'taxa_sucesso': round(success_rate, 1),
                'tempo_medio': round(avg_time, 1)
            }
        except Exception as e:
            print(f"Erro ao calcular stats de search_logs: {e}")
            return {
                'total_buscas': 0, 'sucesso_count': 0, 'empty_count': 0,
                'error_count': 0, 'recovered_count': 0, 'taxa_sucesso': 100.0, 'tempo_medio': 0.0
            }



