# supabase_client.py
import os
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

class SupabaseDB:
    def __init__(self):
        """
        Inicializa o cliente Supabase usando variáveis de ambiente do .env.
        Espera encontrar no .env:
        SUPABASE_URL=<sua_url>
        SUPABASE_KEY=<sua_service_role_key>
        """
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError("❌ Credenciais não encontradas. Verifique seu arquivo .env")

        self.supabase: Client = create_client(supabase_url, supabase_key)

    def verificar_tabela_aprovados(self):
        """
        Verifica se a tabela 'produtos_aprovados' existe.
        Esta tabela deve ser criada manualmente no Supabase usando o script SQL fornecido.
        """
        try:
            # Tenta fazer uma consulta simples para verificar se a tabela existe
            response = self.supabase.table("produtos_aprovados").select("id").limit(1).execute()
            print("✅ Tabela 'produtos_aprovados' encontrada e acessível!")
            return True
            
        except Exception as e:
            print(f"❌ Tabela 'produtos_aprovados' não encontrada: {e}")
            print("ℹ️ Execute o script SQL 'create_aprovados_table.sql' no seu projeto Supabase")
            print("ℹ️ Ou acesse: SQL Editor > New Query > Cole o script > Run")
            return False

    def salvar_produtos_aprovados(self, produtos_aprovados: list):
        """
        Salva produtos aprovados na tabela 'produtos_aprovados'.
        
        Args:
            produtos_aprovados: Lista de dicionários com dados dos produtos aprovados
        """
        if not produtos_aprovados:
            print("⚠️ Lista de produtos aprovados vazia, nada para salvar.")
            return 0
        
        print(f"💾 Iniciando salvamento de {len(produtos_aprovados)} produtos aprovados")
        
        # Prepara os dados para inserção
        dados_para_inserir = []
        for produto in produtos_aprovados:
            # Converte o ID para string se for necessário (UUID)
            oferta_id = produto.get('id')
            if oferta_id is not None:
                oferta_id = str(oferta_id)
            
            dados_produto = {
                'user_id': produto.get('user_id'),  # Adicionando o user_id
                'oferta_id': oferta_id,
                'titulo': produto.get('titulo', ''),
                'preco': produto.get('preco', ''),
                'preco_numerico': produto.get('preco_numerico', 0),
                'loja': produto.get('loja', ''),
                'marketplace': produto.get('marketplace', ''),
                'imagem': produto.get('imagem', ''),
                'url_produto': produto.get('url_produto', ''),
                'avaliacao': produto.get('avaliacao', 0),
                'avaliacoes': produto.get('avaliacoes', 0),
                'termo_pesquisa': produto.get('termo_pesquisa', ''),
                'categoria_preco': produto.get('categoria_preco', ''),
                'score_produto': produto.get('score_produto', 0),
                'prime': produto.get('prime', False),
                'patrocinado': produto.get('patrocinado', False),
                'desconto_percent': produto.get('desconto_percent', 0),
                'preco_antigo': produto.get('preco_antigo', ''),
                'etiquetas': produto.get('etiquetas', []),
                'ofertas_especiais': produto.get('ofertas_especiais', []),
                'vendidos_mes': produto.get('vendidos_mes', 0),
                'observacoes': produto.get('observacoes', ''),
                'status': 'ativo'
            }
            dados_para_inserir.append(dados_produto)
        
        try:
            # Insere os produtos aprovados
            response = self.supabase.table("produtos_aprovados").insert(dados_para_inserir).execute()
            
            if hasattr(response, 'data') and response.data:
                inseridos = len(response.data)
                print(f"✅ {inseridos} produtos aprovados salvos com sucesso!")
                return inseridos
            else:
                print("⚠️ Nenhum dado retornado na inserção.")
                return 0
                
        except Exception as e:
            print(f"❌ Erro ao salvar produtos aprovados: {e}")
            return 0

    def obter_produtos_aprovados(self, limit: int = 50):
        """
        Obtém a lista de produtos aprovados.
        
        Args:
            limit: Número máximo de produtos a retornar
            
        Returns:
            Lista de produtos aprovados
        """
        try:
            response = self.supabase.table("produtos_aprovados")\
                .select("*")\
                .eq("status", "ativo")\
                .order("aprovado_em", desc=True)\
                .limit(limit)\
                .execute()
            
            if hasattr(response, 'data') and response.data:
                print(f"✅ {len(response.data)} produtos aprovados encontrados")
                return response.data
            else:
                print("ℹ️ Nenhum produto aprovado encontrado")
                return []
                
        except Exception as e:
            print(f"❌ Erro ao buscar produtos aprovados: {e}")
            return []

    def contar_produtos_aprovados(self):
        """
        Retorna o número total de produtos aprovados ativos.
        
        Returns:
            Número de produtos aprovados
        """
        try:
            response = self.supabase.table("produtos_aprovados")\
                .select("id", count="exact")\
                .eq("status", "ativo")\
                .execute()
            
            if hasattr(response, 'count'):
                return response.count
            else:
                return 0
                
        except Exception as e:
            print(f"❌ Erro ao contar produtos aprovados: {e}")
            return 0

    def remover_produto_aprovado(self, produto_id: int):
        """
        Remove um produto da lista de aprovados (soft delete).
        
        Args:
            produto_id: ID do produto a ser removido
            
        Returns:
            True se removido com sucesso, False caso contrário
        """
        try:
            response = self.supabase.table("produtos_aprovados")\
                .update({"status": "removido"})\
                .eq("id", produto_id)\
                .execute()
            
            if hasattr(response, 'data') and response.data:
                print(f"✅ Produto {produto_id} removido com sucesso")
                return True
            else:
                print(f"⚠️ Produto {produto_id} não encontrado")
                return False
                
        except Exception as e:
            print(f"❌ Erro ao remover produto aprovado: {e}")
            return False

    def salvar_ofertas(self, df: pd.DataFrame, batch_size: int = 100):
        """
        Salva ofertas no Supabase na tabela 'ofertas'.
        """
        if df.empty:
            print("⚠️ DataFrame vazio, nada para salvar.")
            return
        
        print(f"💾 Iniciando salvamento de {len(df)} ofertas")
        print(f"🔍 Colunas recebidas: {list(df.columns)}")
        
        # Verifica quais colunas estão presentes no DataFrame
        colunas_disponiveis = set(df.columns)
        
        # Função para obter coluna com fallback e tratamento de tipos
        def get_column(dataframe, possible_names, default_value=""):
            for name in possible_names:
                if name in colunas_disponiveis:
                    serie = dataframe[name]
                    # Converte colunas categóricas para string para evitar erros
                    if hasattr(serie, 'dtype') and str(serie.dtype) == 'category':
                        serie = serie.astype(str)
                    return serie.fillna(default_value)
             
            return pd.Series([default_value] * len(dataframe))
        
        # Mapeia colunas obrigatórias e opcionais com múltiplos nomes possíveis
        df_supabase = pd.DataFrame({
            # Colunas obrigatórias
            "termo_pesquisa": get_column(df, ["termo_pesquisa", "TERMO_BUSCA"], ""),
            "titulo": get_column(df, ["titulo", "TITULO", "TITLE"], ""),
            "preco": get_column(df, ["preco", "PRECO_STR", "PRICE"], ""),
            "preco_numerico": get_column(df, ["preco_numerico", "PRECO_NUM", "PRICE_NUMERIC"], 0),
            "loja": get_column(df, ["loja", "CODIGO_PRODUTO", "STORE"], ""),
            "avaliacao": get_column(df, ["avaliacao", "AVALIACAO", "RATING"], 0),
            "avaliacoes": get_column(df, ["avaliacoes", "NUM_AVALIACOES", "REVIEWS"], 0),
            "imagem": get_column(df, ["imagem", "IMAGEM_URL", "IMAGE_URL"], ""),
            
            "url_produto": get_column(df, ["url_produto", "PRODUTO_URL", "PRODUCT_URL"], ""),
            "marketplace": get_column(df, ["marketplace", "MARKETPLACE"], ""),
            
            # Campos de controle
            "criado_em": [datetime.now().isoformat()] * len(df),
            "atualizado_em": [datetime.now().isoformat()] * len(df)
        })
        
        # Adiciona colunas opcionais se estiverem presentes no DataFrame
        colunas_opcionais_mapeamento = {
            "categoria_preco": ["categoria_preco", "CATEGORIA_PRECO"],
            "score_produto": ["score_produto", "SCORE_PRODUTO"],
            "prime": ["prime", "PRIME"],
            "patrocinado": ["patrocinado", "PATROCINADO"],
            "desconto_percent": ["desconto_percent", "DESCONTO_PERCENT"],
            "preco_antigo": ["preco_antigo", "PRECO_ANTIGO"],
            "etiquetas": ["etiquetas", "ETIQUETAS"],
            "ofertas_especiais": ["ofertas_especiais", "OFERTAS_ESPECIAIS"],
            "vendidos_mes": ["vendidos_mes", "VENDIDOS_MES"]
        }
        # Adicione perto do final da função salvar_ofertas, antes de converter para registros
# Limpa espaços em branco das URLs de imagem
        if "imagem" in df_supabase.columns:
         df_supabase["imagem"] = df_supabase["imagem"].astype(str).str.strip()
        for coluna_supabase, possiveis_nomes in colunas_opcionais_mapeamento.items():
            valor_coluna = get_column(df, possiveis_nomes, "")
            df_supabase[coluna_supabase] = valor_coluna

        # **CORREÇÃO DEFINITIVA**: Converte tipos explicitamente e com segurança
        def safe_convert_to_numeric(series, dtype='float'):
            """Converte série para numérico com tratamento seguro de erros"""
            try:
                converted = pd.to_numeric(series, errors='coerce').fillna(0)
                if dtype == 'int':
                    return converted.astype('int64')
                return converted
            except Exception as e:
                print(f"⚠️ Erro na conversão numérica: {e}")
                if dtype == 'int':
                    return pd.Series([0] * len(series), dtype='int64')
                return converted.astype('float64')
        
        def safe_convert_to_bool(series):
            """Converte série para booleano com tratamento seguro"""
            try:
                # Trata valores NaN como False
                series = series.fillna(False)
                # Converte strings para booleano
                if series.dtype == 'object':
                    return series.astype(str).str.lower().isin(['true', '1', 'yes', 'sim', 't', 'y'])
                # Converte números para booleano
                return series.astype(bool)
            except Exception as e:
                print(f"⚠️ Erro na conversão booleana: {e}")
                return pd.Series([False] * len(series), dtype=bool)
        
        # Converte tipos numéricos com segurança máxima
        df_supabase["preco_numerico"] = safe_convert_to_numeric(df_supabase["preco_numerico"], 'float')
        df_supabase["avaliacao"] = safe_convert_to_numeric(df_supabase["avaliacao"], 'float')
        df_supabase["avaliacoes"] = safe_convert_to_numeric(df_supabase["avaliacoes"], 'int')
        df_supabase["score_produto"] = safe_convert_to_numeric(df_supabase.get("score_produto", pd.Series([0] * len(df_supabase))), 'float')
        df_supabase["desconto_percent"] = safe_convert_to_numeric(df_supabase.get("desconto_percent", pd.Series([0] * len(df_supabase))), 'float')
        
        # Converte booleanos com segurança
        df_supabase["prime"] = safe_convert_to_bool(df_supabase.get("prime", pd.Series([False] * len(df_supabase))))
        df_supabase["patrocinado"] = safe_convert_to_bool(df_supabase.get("patrocinado", pd.Series([False] * len(df_supabase))))
        
        # Limpa espaços em branco das URLs de imagem (reforço)
        if "imagem" in df_supabase.columns:
            df_supabase["imagem"] = df_supabase["imagem"].astype(str).str.strip()
        # Mostra exemplo do que será salvo (com tipos corretos)
        print(f"🔍 Exemplo do que será salvo no Supabase:")
        if len(df_supabase) > 0:
            exemplo = df_supabase.iloc[0].to_dict()
            for key, value in exemplo.items():
                print(f"   {key}: {value} ({type(value).__name__})")

        # Converte para registros (dicionários)
        registros = df_supabase.to_dict(orient="records")

        # Inserir em lotes
        total_inseridos = 0
        for i in range(0, len(registros), batch_size):
            batch = registros[i:i+batch_size]
            try:
                response = self.supabase.table("ofertas").insert(batch).execute()
                
                if hasattr(response, 'data') and response.data:
                    inseridos = len(response.data)
                    total_inseridos += inseridos
                    print(f"✅ Inseridos {inseridos} registros no Supabase. (Batch {i//batch_size + 1})")
                else:
                    print("⚠️ Nenhum dado retornado ou dados vazios.")
                    
            except Exception as e:
                print(f"❌ Erro ao inserir no Supabase: {e}")
        
        print(f"💾 Total de registros salvos: {total_inseridos}")
