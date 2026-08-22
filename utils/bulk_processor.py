import threading
import time
import pandas as pd
import json
import os
from datetime import datetime

# Adiciona o diretório raiz ao path
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraping.unificar_dados import unificar_dados_amazon_mercadolivre
from database.db_manager import DatabaseManager

class BulkProcessor:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def start_bulk_search(self, lote_id: str, user_id: int):
        """Inicia o processamento em segundo plano do lote"""
        thread = threading.Thread(
            target=self._process_lote,
            args=(lote_id, user_id),
            daemon=True
        )
        thread.start()

    def _process_lote(self, lote_id: str, user_id: int):
        print(f"🚀 Iniciando processamento do lote {lote_id} para usuário {user_id}")
        
        # Atualiza status do lote para processando
        self.db_manager.supabase.table("lotes_busca").update({
            "status": "processando"
        }).eq("id", lote_id).execute()

        # Configura credenciais temporárias do usuário se existirem
        configs = self.db_manager.get_user_configs(user_id)
        config_dict = {config['chave']: config['valor'] for config in configs}
        
        original_env = {}
        for key, value in config_dict.items():
            if value:
                original_env[key] = os.environ.get(key)
                os.environ[key] = value

        try:
            # Pega todos os itens pendentes do lote
            response = self.db_manager.supabase.table("lote_itens").select("*").eq("lote_id", lote_id).eq("status", "pendente").execute()
            itens = response.data or []

            for index, item in enumerate(itens):
                termo = item['termo']
                print(f"🔍 Buscando termo ({index+1}/{len(itens)}): {termo}")
                
                try:
                    df = unificar_dados_amazon_mercadolivre(termo, paginas_ml=1, salvar_supabase=True)
                    
                    if df is not None and not df.empty and 'PRECO_NUM' in df.columns:
                        # Filtrar preços maiores que zero
                        df_valid = df[df['PRECO_NUM'] > 0]
                        
                        if not df_valid.empty:
                            # 5 Mais baratos
                            top_baratos = df_valid.nsmallest(5, 'PRECO_NUM')
                            # 5 Mais caros
                            top_caros = df_valid.nlargest(5, 'PRECO_NUM')
                            
                            baratos_json = top_baratos.to_dict(orient='records')
                            caros_json = top_caros.to_dict(orient='records')
                            
                            self.db_manager.supabase.table("lote_itens").update({
                                "status": "sucesso",
                                "top_5_baratos": baratos_json,
                                "top_5_caros": caros_json,
                                "concluido_em": datetime.now().isoformat()
                            }).eq("id", item['id']).execute()

                            # Grava no histórico individual de buscas
                            try:
                                stats = {
                                    'total_produtos': int(len(df_valid)),
                                    'amazon_produtos': int(len(df_valid[df_valid['MARKETPLACE'] == 'Amazon'])),
                                    'ml_produtos': int(len(df_valid[df_valid['MARKETPLACE'] == 'MercadoLivre'])),
                                    'preco_medio': float(df_valid['PRECO_NUM'].mean() or 0),
                                    'preco_minimo': float(df_valid['PRECO_NUM'].min() or 0),
                                    'preco_maximo': float(df_valid['PRECO_NUM'].max() or 0),
                                    'origem': 'busca_em_lote',
                                    'lote_id': lote_id
                                }
                                self.db_manager.save_search_history(user_id, termo, stats)
                            except Exception as hist_err:
                                print(f"⚠️ Erro ao salvar histórico individual do lote para {termo}: {hist_err}")
                        else:
                            self.db_manager.supabase.table("lote_itens").update({
                                "status": "erro",
                                "erro_mensagem": "Nenhum produto válido encontrado",
                                "concluido_em": datetime.now().isoformat()
                            }).eq("id", item['id']).execute()
                    else:
                        self.db_manager.supabase.table("lote_itens").update({
                            "status": "erro",
                            "erro_mensagem": "Falha ao buscar dados",
                            "concluido_em": datetime.now().isoformat()
                        }).eq("id", item['id']).execute()
                        
                except Exception as e:
                    print(f"❌ Erro no item {termo}: {e}")
                    self.db_manager.supabase.table("lote_itens").update({
                        "status": "erro",
                        "erro_mensagem": str(e),
                        "concluido_em": datetime.now().isoformat()
                    }).eq("id", item['id']).execute()
                
                # Atualizar progresso no lote
                self.db_manager.supabase.table("lotes_busca").update({
                    "itens_processados": index + 1
                }).eq("id", lote_id).execute()

            # Processamento finalizado, gerar excel
            self._gerar_relatorio_excel(lote_id)

        finally:
            # Restaurar credenciais originais
            for key, original_value in original_env.items():
                if original_value is not None:
                    os.environ[key] = original_value
                elif key in os.environ:
                    del os.environ[key]

    def _gerar_relatorio_excel(self, lote_id: str):
        # Buscar itens concluídos
        response = self.db_manager.supabase.table("lote_itens").select("*").eq("lote_id", lote_id).execute()
        itens = response.data or []
        
        linhas_baratos = []
        linhas_caros = []
        
        for item in itens:
            termo = item['termo']
            baratos = item.get('top_5_baratos') or []
            caros = item.get('top_5_caros') or []
            
            for b in baratos:
                b['TERMO_BUSCADO'] = termo
                b['TIPO'] = 'Mais Baratos'
                linhas_baratos.append(b)
                
            for c in caros:
                c['TERMO_BUSCADO'] = termo
                c['TIPO'] = 'Mais Caros'
                linhas_caros.append(c)
                
        df_baratos = pd.DataFrame(linhas_baratos)
        df_caros = pd.DataFrame(linhas_caros)
        
        # Garante que as pastas existam
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        
        file_name = f"lote_{lote_id}.xlsx"
        file_path = os.path.join(reports_dir, file_name)
        
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            if not df_baratos.empty:
                df_baratos.to_excel(writer, sheet_name='5 Mais Baratos', index=False)
            if not df_caros.empty:
                df_caros.to_excel(writer, sheet_name='5 Mais Caros', index=False)
                
            if df_baratos.empty and df_caros.empty:
                # Cria uma aba vazia caso não encontre nada
                pd.DataFrame([{"Aviso": "Nenhum dado encontrado"}]).to_excel(writer, sheet_name='Sem Resultados', index=False)
        
        file_url = f"/static/reports/{file_name}"
        
        # Atualiza lote
        self.db_manager.supabase.table("lotes_busca").update({
            "status": "concluido",
            "arquivo_resultado_url": file_url,
            "concluido_em": datetime.now().isoformat()
        }).eq("id", lote_id).execute()
        print(f"✅ Relatório do lote {lote_id} gerado em {file_path}")

