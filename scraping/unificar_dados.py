# Conteúdo do arquivo: unificar_dados.py
import pandas as pd
import numpy as np
from datetime import datetime
import os
import re
from typing import Optional, List, Dict, Any

# Importa as funções dos scrapers
from scraping.serpapi_amazon_func import buscar_produtos_amazon
from scraping.web_scrap_mercado_livre import get_mercado_livre_data
from scraping.web_scrap_mercado_livre_improved import get_mercado_livre_data_improved


def limpar_preco_numerico(preco_str: str) -> float:
    """
    Limpa e converte string de preço para valor numérico.
    
    Args:
        preco_str (str): String do preço
        
    Returns:
        float: Valor numérico ou 0.0 se inválido
    """
    if not preco_str or pd.isna(preco_str):
        return 0.0
    
    preco_str = str(preco_str)
    
    # Remove símbolos de moeda e espaços
    preco_limpo = (preco_str
                   .replace("R$", "")
                   .replace("$", "")
                   .replace(" ", "")
                   .strip())
    
    # Trata diferentes formatos de número
    # Ex: "1.234,56" -> "1234.56" ou "1,234.56" -> "1234.56"
    if ',' in preco_limpo and '.' in preco_limpo:
        # Formato "1.234,56" (brasileiro) ou "1,234.56" (americano)
        if preco_limpo.rfind(',') > preco_limpo.rfind('.'):
            # Formato brasileiro: "1.234,56"
            preco_limpo = preco_limpo.replace('.', '').replace(',', '.')
        else:
            # Formato americano: "1,234.56"
            preco_limpo = preco_limpo.replace(',', '')
    elif ',' in preco_limpo:
        # Se só tem vírgula, pode ser decimal ou separador de milhares
        partes = preco_limpo.split(',')
        if len(partes) == 2 and len(partes[1]) <= 2:
            # Provavelmente decimal: "123,45"
            preco_limpo = preco_limpo.replace(',', '.')
        else:
            # Provavelmente separador de milhares: "1,234"
            preco_limpo = preco_limpo.replace(',', '')
    
    # Extrai apenas números e ponto decimal
    match = re.search(r'(\d+\.?\d*)', preco_limpo)
    
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    
    return 0.0


def padronizar_colunas_amazon(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza colunas do DataFrame do Amazon para formato unificado.
    
    Args:
        df (pd.DataFrame): DataFrame original do Amazon
        
    Returns:
        pd.DataFrame: DataFrame padronizado
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Cria cópia para não alterar original
    df_padronizado = df.copy()
    
    # **CORREÇÃO IMPORTANTE**: Converte colunas categóricas para string para evitar erros
    for col in df_padronizado.columns:
        if hasattr(df_padronizado[col], 'dtype') and str(df_padronizado[col].dtype) == 'category':
            df_padronizado[col] = df_padronizado[col].astype(str)
    
    # Mapeia colunas para padrão unificado (compatível com Supabase)
    column_mapping = {
        'TITLE': 'TITULO',
        'PRICE': 'PRECO_STR',
        'PRICE_NUMERIC': 'PRECO_NUM',
        'RATING': 'AVALIACAO',
        'REVIEWS_COUNT': 'NUM_AVALIACOES',
        'IMAGE_URL': 'IMAGEM_URL',
        'PRODUCT_URL': 'PRODUTO_URL',
        'SEARCH_TERM': 'TERMO_BUSCA',
        'SCRAPY_DATETIME': 'DATA_SCRAPING',
        'MARKETPLACE': 'MARKETPLACE',
        'ASIN': 'CODIGO_PRODUTO',
        'OLD_PRICE': 'PRECO_ANTIGO',
        'DISCOUNT_PERCENT': 'DESCONTO_PERCENT',
        'PRIME': 'PRIME',
        'SPONSORED': 'PATROCINADO',
        'BADGES': 'ETIQUETAS',
        'BOUGHT_LAST_MONTH': 'VENDIDOS_MES',
        'OFFERS': 'OFERTAS_ESPECIAIS',
        'SNAP_EBT_ELIGIBLE': 'SNAP_EBT'
    }
    
    # Renomeia colunas existentes
    df_padronizado = df_padronizado.rename(columns=column_mapping)
    
    # Adiciona colunas obrigatórias que podem não existir
    colunas_obrigatorias = {
        'TITULO': '',
        'PRECO_STR': '',
        'PRECO_NUM': 0.0,
        'AVALIACAO': 0.0,
        'NUM_AVALIACOES': 0,
        'IMAGEM_URL': '',
        'PRODUTO_URL': '',
        'TERMO_BUSCA': '',
        'DATA_SCRAPING': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'MARKETPLACE': 'Amazon'
    }
    
    for coluna, valor_padrao in colunas_obrigatorias.items():
        if coluna not in df_padronizado.columns:
            df_padronizado[coluna] = valor_padrao
    
    # Garante que PRECO_NUM seja numérico
    if 'PRECO_NUM' in df_padronizado.columns:
        df_padronizado['PRECO_NUM'] = pd.to_numeric(df_padronizado['PRECO_NUM'], errors='coerce').fillna(0)
    else:
        df_padronizado['PRECO_NUM'] = df_padronizado['PRECO_STR'].apply(limpar_preco_numerico)
    
    # Converte avaliações para float
    if 'AVALIACAO' in df_padronizado.columns:
        df_padronizado['AVALIACAO'] = pd.to_numeric(df_padronizado['AVALIACAO'], errors='coerce').fillna(0)
    
    # Converte número de avaliações para int
    if 'NUM_AVALIACOES' in df_padronizado.columns:
        df_padronizado['NUM_AVALIACOES'] = pd.to_numeric(df_padronizado['NUM_AVALIACOES'], errors='coerce').fillna(0).astype(int)
    
    return df_padronizado


def padronizar_colunas_ml(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza colunas do DataFrame do Mercado Livre para formato unificado.
    
    Args:
        df (pd.DataFrame): DataFrame original do Mercado Livre
        
    Returns:
        pd.DataFrame: DataFrame padronizado
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Cria cópia para não alterar original
    df_padronizado = df.copy()
    
    # **CORREÇÃO IMPORTANTE**: Converte colunas categóricas para string para evitar erros
    for col in df_padronizado.columns:
        if hasattr(df_padronizado[col], 'dtype') and str(df_padronizado[col].dtype) == 'category':
            df_padronizado[col] = df_padronizado[col].astype(str)
    
    # Mapeia colunas para padrão unificado (compatível com Supabase)
    column_mapping = {
        'TITLE': 'TITULO',
        'PRICE': 'PRECO_STR',
        'PRICE_NUMERIC': 'PRECO_NUM',
        'RATING': 'AVALIACAO',
        'REVIEWS': 'NUM_AVALIACOES',
        'IMAGE_URL': 'IMAGEM_URL',
        'PRODUCT_URL': 'PRODUTO_URL',
        'SEARCH_TERM': 'TERMO_BUSCA',
        'SCRAPY_DATETIME': 'DATA_SCRAPING',
        'MARKETPLACE': 'MARKETPLACE'
    }
    
    # Renomeia colunas existentes
    df_padronizado = df_padronizado.rename(columns=column_mapping)
    
    # Adiciona colunas obrigatórias que podem não existir
    colunas_obrigatorias = {
        'TITULO': '',
        'PRECO_STR': '',
        'PRECO_NUM': 0.0,
        'AVALIACAO': 0.0,
        'NUM_AVALIACOES': 0,
        'IMAGEM_URL': '',
        'PRODUTO_URL': '',
        'TERMO_BUSCA': '',
        'DATA_SCRAPING': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'MARKETPLACE': 'MercadoLivre'
    }
    
    for coluna, valor_padrao in colunas_obrigatorias.items():
        if coluna not in df_padronizado.columns:
            df_padronizado[coluna] = valor_padrao
    
    # Garante que PRECO_NUM seja numérico e limpo
    if 'PRECO_NUM' in df_padronizado.columns:
        df_padronizado['PRECO_NUM'] = pd.to_numeric(df_padronizado['PRECO_NUM'], errors='coerce').fillna(0)
    
    # Se PRECO_NUM está zerado mas temos PRECO_STR, tenta extrair
    mask_preco_zero = (df_padronizado['PRECO_NUM'] == 0) & (df_padronizado['PRECO_STR'] != '')
    if mask_preco_zero.any():
        df_padronizado.loc[mask_preco_zero, 'PRECO_NUM'] = df_padronizado.loc[mask_preco_zero, 'PRECO_STR'].apply(limpar_preco_numerico)
    
    # Converte avaliações para float
    if 'AVALIACAO' in df_padronizado.columns:
        df_padronizado['AVALIACAO'] = pd.to_numeric(df_padronizado['AVALIACAO'], errors='coerce').fillna(0)
    
    # Converte número de avaliações para int
    if 'NUM_AVALIACOES' in df_padronizado.columns:
        df_padronizado['NUM_AVALIACOES'] = pd.to_numeric(df_padronizado['NUM_AVALIACOES'], errors='coerce').fillna(0).astype(int)
    
    return df_padronizado


def filtrar_produtos_validos(df: pd.DataFrame, min_price: float = 0.0) -> pd.DataFrame:
    """
    Filtra produtos removendo aqueles sem preço válido.
    
    Args:
        df (pd.DataFrame): DataFrame com produtos
        min_price (float): Preço mínimo para filtrar
        
    Returns:
        pd.DataFrame: DataFrame filtrado
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    df_filtrado = df.copy()
    
    # **CORREÇÃO IMPORTANTE**: Converte colunas categóricas para string para evitar erros
    for col in df_filtrado.columns:
        if hasattr(df_filtrado[col], 'dtype') and str(df_filtrado[col].dtype) == 'category':
            df_filtrado[col] = df_filtrado[col].astype(str)
    
    # Remove apenas produtos sem preço ou com preço zero/inválido
    df_filtrado = df_filtrado[
        (df_filtrado['PRECO_NUM'] > min_price) &
        (df_filtrado['PRECO_NUM'].notna()) &
        (df_filtrado['TITULO'] != '') &
        (df_filtrado['TITULO'].notna())
    ].copy()
    
    # REMOVIDO: Filtro de títulos semelhantes - mantém todos os produtos
    
    return df_filtrado


def adicionar_metricas_comparacao(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adiciona métricas para facilitar comparação de produtos.
    
    Args:
        df (pd.DataFrame): DataFrame com produtos
        
    Returns:
        pd.DataFrame: DataFrame com métricas adicionadas
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    df_com_metricas = df.copy()
    
    # Categoria de preço
    if df_com_metricas['PRECO_NUM'].max() > 0:
        # Converte para string para evitar problemas com categorias
        categorias = pd.cut(
            df_com_metricas['PRECO_NUM'],
            bins=5,
            labels=['Muito Barato', 'Barato', 'Médio', 'Caro', 'Muito Caro']
        )
        df_com_metricas['CATEGORIA_PRECO'] = categorias.astype(str)
    else:
        df_com_metricas['CATEGORIA_PRECO'] = 'Indefinido'
    
    # Score de produto (combinando preço e avaliação)
    # Normaliza preço (menor preço = maior score) e avaliação (maior avaliação = maior score)
    if df_com_metricas['PRECO_NUM'].max() > df_com_metricas['PRECO_NUM'].min():
        preco_normalizado = (df_com_metricas['PRECO_NUM'].max() - df_com_metricas['PRECO_NUM']) / \
                           (df_com_metricas['PRECO_NUM'].max() - df_com_metricas['PRECO_NUM'].min())
    else:
        preco_normalizado = 1
    
    if df_com_metricas['AVALIACAO'].max() > 0:
        avaliacao_normalizada = df_com_metricas['AVALIACAO'] / df_com_metricas['AVALIACAO'].max()
    else:
        avaliacao_normalizada = 0
    
    # Score: 40% preço + 60% avaliação (favorece qualidade)
    df_com_metricas['SCORE_PRODUTO'] = (preco_normalizado * 0.4 + avaliacao_normalizada * 0.6) * 100
    df_com_metricas['SCORE_PRODUTO'] = df_com_metricas['SCORE_PRODUTO'].round(2)
    
    return df_com_metricas


def converter_para_supabase(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte DataFrame unificado para formato compatível com Supabase.
    
    Args:
        df (pd.DataFrame): DataFrame unificado
        
    Returns:
        pd.DataFrame: DataFrame no formato Supabase
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Mapeia colunas para o schema do Supabase (atualizado com novos campos)
    df_supabase = pd.DataFrame({
        "termo_pesquisa": df["TERMO_BUSCA"].fillna(""),
        "titulo": df["TITULO"].fillna(""),
        "preco": df["PRECO_STR"].fillna(""),
        "preco_numerico": df["PRECO_NUM"].fillna(0),
        "loja": df.get("CODIGO_PRODUTO", pd.Series([""] * len(df))).fillna(""), # ASIN ou código ML
        "avaliacao": df["AVALIACAO"].fillna(0),
        "avaliacoes": df["NUM_AVALIACOES"].fillna(0),
        "imagem": df["IMAGEM_URL"].fillna(""),
        "url_produto": df["PRODUTO_URL"].fillna(""),
        "marketplace": df["MARKETPLACE"].fillna(""),
        
        # Novos campos de avaliação e métricas
        "categoria_preco": df.get("CATEGORIA_PRECO", pd.Series([""] * len(df))).fillna(""),
        "score_produto": df.get("SCORE_PRODUTO", pd.Series([0] * len(df))).fillna(0),
        "prime": df.get("PRIME", pd.Series([False] * len(df))).fillna(False),
        "patrocinado": df.get("PATROCINADO", pd.Series([False] * len(df))).fillna(False),
        "desconto_percent": df.get("DESCONTO_PERCENT", pd.Series([0] * len(df))).fillna(0),
        "preco_antigo": df.get("PRECO_ANTIGO", pd.Series([""] * len(df))).fillna(""),
        "etiquetas": df.get("ETIQUETAS", pd.Series([""] * len(df))).fillna(""),
        "ofertas_especiais": df.get("OFERTAS_ESPECIAIS", pd.Series([""] * len(df))).fillna(""),
        "vendidos_mes": df.get("VENDIDOS_MES", pd.Series([""] * len(df))).fillna(""),
        
        # Campos de controle
        "criado_em": [datetime.now().isoformat()] * len(df),
        "atualizado_em": [datetime.now().isoformat()] * len(df)
    })
    
    return df_supabase


def gerar_relatorio_unificado(df: pd.DataFrame, termo_busca: str):
    """
    Gera relatório detalhado dos produtos unificados.
    
    Args:
        df (pd.DataFrame): DataFrame com produtos
        termo_busca (str): Termo de busca utilizado
    """
    if df is None or df.empty:
        print("❌ Nenhum produto encontrado para gerar relatório")
        return
    
    print("\n" + "="*60)
    print(f"📊 RELATÓRIO UNIFICADO - BUSCA: '{termo_busca.upper()}'")
    print("="*60)
    
    # Estatísticas gerais
    total_produtos = len(df)
    amazon_produtos = len(df[df['MARKETPLACE'] == 'Amazon'])
    ml_produtos = len(df[df['MARKETPLACE'] == 'MercadoLivre'])
    
    print(f"🔢 Total de produtos encontrados: {total_produtos}")
    print(f"🛒 Amazon: {amazon_produtos} produtos ({amazon_produtos/total_produtos*100:.1f}%)")
    print(f"🛒 Mercado Livre: {ml_produtos} produtos ({ml_produtos/total_produtos*100:.1f}%)")
    
    # Estatísticas de preço
    precos_validos = df[df['PRECO_NUM'] > 0]['PRECO_NUM']
    if not precos_validos.empty:
        print(f"\n💰 ANÁLISE DE PREÇOS:")
        print(f"   Preço médio: R$ {precos_validos.mean():.2f}")
        print(f"   Preço mínimo: R$ {precos_validos.min():.2f}")
        print(f"   Preço máximo: R$ {precos_validos.max():.2f}")
        print(f"   Mediana: R$ {precos_validos.median():.2f}")
    
    # Estatísticas de avaliação
    avaliacoes_validas = df[df['AVALIACAO'] > 0]['AVALIACAO']
    if not avaliacoes_validas.empty:
        print(f"\n⭐ ANÁLISE DE AVALIAÇÕES:")
        print(f"   Avaliação média: {avaliacoes_validas.mean():.2f}")
        print(f"   Produtos avaliados: {len(avaliacoes_validas)}")
        print(f"   % com avaliação: {len(avaliacoes_validas)/total_produtos*100:.1f}%")
        
        # Distribuição de avaliações
        if 'CATEGORIA_PRECO' in df.columns:
            print(f"   Produtos bem avaliados (4+): {len(df[df['AVALIACAO'] >= 4])}")
    
    # Top 5 produtos por marketplace
    print(f"\n🏆 TOP 5 POR MARKETPLACE:")
    
    for marketplace in ['Amazon', 'MercadoLivre']:
        df_mp = df[df['MARKETPLACE'] == marketplace]
        if not df_mp.empty:
            print(f"\n📱 {marketplace.upper()}:")
            if 'SCORE_PRODUTO' in df_mp.columns:
                top_5 = df_mp.nlargest(5, 'SCORE_PRODUTO')[['TITULO', 'PRECO_NUM', 'AVALIACAO', 'SCORE_PRODUTO']]
            else:
                top_5 = df_mp.nsmallest(5, 'PRECO_NUM')[['TITULO', 'PRECO_NUM', 'AVALIACAO']]
            
            for idx, row in top_5.iterrows():
                titulo_resumo = row['TITULO'][:50] + "..." if len(row['TITULO']) > 50 else row['TITULO']
                print(f"   • {titulo_resumo}")
                score_info = f" | Score: {row['SCORE_PRODUTO']:.1f}" if 'SCORE_PRODUTO' in row else ""
                print(f"     R$ {row['PRECO_NUM']:.2f} | ⭐{row['AVALIACAO']:.1f}{score_info}")
    
    # Comparação de preços entre marketplaces
    print(f"\n💲 COMPARAÇÃO DE PREÇOS:")
    preco_medio_amazon = df[df['MARKETPLACE'] == 'Amazon']['PRECO_NUM'].mean()
    preco_medio_ml = df[df['MARKETPLACE'] == 'MercadoLivre']['PRECO_NUM'].mean()
    
    if not pd.isna(preco_medio_amazon) and not pd.isna(preco_medio_ml):
        if preco_medio_amazon < preco_medio_ml:
            diferenca = ((preco_medio_ml - preco_medio_amazon) / preco_medio_amazon) * 100
            print(f"   Amazon em média {diferenca:.1f}% mais barata")
        else:
            diferenca = ((preco_medio_amazon - preco_medio_ml) / preco_medio_ml) * 100
            print(f"   Mercado Livre em média {diferenca:.1f}% mais barato")
    
    print("="*60)


def salvar_no_supabase(df: pd.DataFrame, termo_busca: str) -> bool:
    """
    Salva dados unificados no Supabase.
    
    Args:
        df (pd.DataFrame): DataFrame para salvar
        termo_busca (str): Termo de busca
        
    Returns:
        bool: True se salvou com sucesso
    """
    if df is None or df.empty:
        print("❌ Nenhum dado para salvar no Supabase")
        return False
    
    try:
        # Importa a classe DatabaseManager
        from database.db_manager import DatabaseManager
        
        # Converte para formato Supabase
        df_supabase = converter_para_supabase(df)
        
        # Salva no Supabase usando DatabaseManager
        db = DatabaseManager()
        success = db.salvar_ofertas(df_supabase)
        
        if success:
            print(f"💾 {len(df_supabase)} produtos salvos no Supabase com sucesso!")
        else:
            print("❌ Falha ao salvar produtos no Supabase")
        return success
        
    except ImportError:
        print("❌ Módulo database.db_manager não encontrado")
        return False
    except Exception as e:
        print(f"❌ Erro ao salvar no Supabase: {e}")
        import traceback
        traceback.print_exc()
        return False


def buscar_ofertas_do_dia(
    paginas_ml: int = 1,
    salvar_supabase: bool = True
) -> pd.DataFrame:
    """
    Busca ofertas do dia do Mercado Livre (sem termo específico)
    
    Args:
        paginas_ml (int): Número de páginas do ML para buscar
        salvar_supabase (bool): Se deve salvar no Supabase
        
    Returns:
        pd.DataFrame: DataFrame com produtos das ofertas do dia
    """
    print(f"🛒 Buscando ofertas do dia do Mercado Livre...")
    print("="*50)
    
    min_price = float(os.getenv("MIN_PRICE_FILTER", 1.0))

    # Busca dados do Mercado Livre (ofertas do dia)
    print("🛒 Buscando ofertas do dia no Mercado Livre...")
    try:
        # Usa o scraper melhorado sem termo de busca (busca padrão)
        df_ml = get_mercado_livre_data_improved("", paginas_ml)
        if df_ml is not None and not df_ml.empty:
            print(f"✅ Mercado Livre: {len(df_ml)} ofertas do dia encontradas")
        else:
            print("⚠️ Mercado Livre: Nenhuma oferta do dia encontrada")
            df_ml = pd.DataFrame()
    except Exception as e:
        print(f"❌ Erro na busca de ofertas do dia: {e}")
        df_ml = pd.DataFrame()
    
    # Padroniza colunas
    print("🔧 Padronizando dados...")
    df_ml_padronizado = padronizar_colunas_ml(df_ml)
    
    # Combina DataFrames (só ML neste caso)
    dfs_validos = [df for df in [df_ml_padronizado] 
                   if df is not None and not df.empty]
    
    if not dfs_validos:
        print("❌ Nenhuma oferta do dia válida encontrada")
        return pd.DataFrame()
    
    # Combina todos os DataFrames válidos
    df_final = pd.concat(dfs_validos, ignore_index=True)
    
    # Remove duplicatas baseado no título e preço
    df_final = df_final.drop_duplicates(subset=['titulo', 'preco_numerico'], keep='first')
    
    # Filtra por preço mínimo
    df_final = df_final[df_final['preco_numerico'] >= min_price]
    
    # Ordena por preço (menor primeiro)
    df_final = df_final.sort_values('preco_numerico').reset_index(drop=True)
    
    print(f"🎯 Total de ofertas do dia processadas: {len(df_final)}")
    
    # Salva no Supabase se solicitado
    if salvar_supabase and not df_final.empty:
        print("💾 Salvando ofertas do dia no Supabase...")
        sucesso = salvar_no_supabase(df_final, "ofertas_do_dia")
        if sucesso:
            print("✅ Ofertas do dia salvas com sucesso!")
        else:
            print("❌ Erro ao salvar ofertas do dia")
    
    return df_final

def unificar_dados_amazon_mercadolivre(
    termo: str,
    paginas_ml: int = 1,
    salvar_supabase: bool = True
) -> pd.DataFrame:
    """
    Unifica dados de Amazon (via SerpApi) e Mercado Livre (via Selenium).
    
    Args:
        termo (str): Termo de busca
        paginas_ml (int): Número de páginas do ML para buscar
        salvar_supabase (bool): Se deve salvar no Supabase
        
    Returns:
        pd.DataFrame: DataFrame unificado com produtos filtrados
    """
    print(f"🔍 Iniciando busca unificada para: '{termo}'")
    print("="*50)
    
    min_price = float(os.getenv("MIN_PRICE_FILTER", 1.0))

    # Busca dados do Amazon
    print("🛒 Buscando produtos na Amazon...")
    try:
        df_amazon = buscar_produtos_amazon(termo)
        if df_amazon is not None and not df_amazon.empty:
            print(f"✅ Amazon: {len(df_amazon)} produtos encontrados")
        else:
            print("⚠️ Amazon: Nenhum produto encontrado")
            df_amazon = pd.DataFrame()
    except Exception as e:
        print(f"❌ Erro na busca Amazon: {e}")
        df_amazon = pd.DataFrame()
    
    # Busca dados do Mercado Livre (usando versão melhorada)
    print("🛒 Buscando produtos no Mercado Livre...")
    try:
        # Usa o scraper melhorado que suporta busca padrão e com termo
        df_ml = get_mercado_livre_data_improved(termo, paginas_ml)
        if df_ml is not None and not df_ml.empty:
            print(f"✅ Mercado Livre: {len(df_ml)} produtos encontrados")
        else:
            print("⚠️ Mercado Livre: Nenhum produto encontrado")
            df_ml = pd.DataFrame()
    except Exception as e:
        print(f"❌ Erro na busca Mercado Livre: {e}")
        # Fallback para o scraper original
        try:
            print("🔄 Tentando com scraper original...")
            df_ml = get_mercado_livre_data(termo, paginas_ml)
            if df_ml is not None and not df_ml.empty:
                print(f"✅ Mercado Livre (fallback): {len(df_ml)} produtos encontrados")
            else:
                df_ml = pd.DataFrame()
        except Exception as e2:
            print(f"❌ Erro no fallback Mercado Livre: {e2}")
            df_ml = pd.DataFrame()
    
    # Padroniza colunas
    print("🔧 Padronizando dados...")
    df_amazon_padronizado = padronizar_colunas_amazon(df_amazon)
    df_ml_padronizado = padronizar_colunas_ml(df_ml)
    
    # Combina DataFrames
    dfs_validos = [df for df in [df_amazon_padronizado, df_ml_padronizado] 
                   if df is not None and not df.empty]
    
    if not dfs_validos:
        print("❌ Nenhum dado válido encontrado")
        return pd.DataFrame()
    
    df_unificado = pd.concat(dfs_validos, ignore_index=True)
    
    # Filtra produtos válidos (apenas remove sem preço)
    print("🔍 Filtrando produtos válidos...")
    df_filtrado = filtrar_produtos_validos(df_unificado, min_price=min_price)
    
    if df_filtrado.empty:
        print("❌ Nenhum produto válido após filtros")
        return pd.DataFrame()
    
    # Adiciona métricas de comparação
    print("📊 Calculando métricas...")
    df_final = adicionar_metricas_comparacao(df_filtrado)
    
    # Ordena por score se disponível
    if 'SCORE_PRODUTO' in df_final.columns:
        df_final = df_final.sort_values('SCORE_PRODUTO', ascending=False).reset_index(drop=True)
    else:
        df_final = df_final.sort_values('PRECO_NUM', ascending=True).reset_index(drop=True)
    
    # Gera relatório
    gerar_relatorio_unificado(df_final, termo)
    
    # Salva no Supabase se solicitado
    if salvar_supabase:
        salvar_no_supabase(df_final, termo)
    
    print(f"\n✅ Busca concluída! {len(df_final)} produtos encontrados")
    
    return df_final


def comparar_produto_especifico(df: pd.DataFrame, termo_produto: str) -> pd.DataFrame:
    """
    Compara preços de um produto específico entre marketplaces.
    
    Args:
        df (pd.DataFrame): DataFrame com produtos
        termo_produto (str): Termo para filtrar produto específico
        
    Returns:
        pd.DataFrame: DataFrame com produtos similares
    """
    if df is None or df.empty:
        return pd.DataFrame()
    
    # Filtra produtos que contenham o termo no título
    mask = df['TITULO'].str.contains(termo_produto, case=False, na=False)
    df_produto = df[mask].copy()
    
    if df_produto.empty:
        print(f"❌ Nenhum produto encontrado com '{termo_produto}'")
        return pd.DataFrame()
    
    # Agrupa por marketplace e mostra estatísticas
    print(f"\n🔍 COMPARAÇÃO DE PREÇOS: '{termo_produto}'")
    print("="*50)
    
    for marketplace in df_produto['MARKETPLACE'].unique():
        df_mp = df_produto[df_produto['MARKETPLACE'] == marketplace]
        print(f"\n📱 {marketplace.upper()}:")
        print(f"   Produtos encontrados: {len(df_mp)}")
        print(f"   Preço médio: R$ {df_mp['PRECO_NUM'].mean():.2f}")
        print(f"   Menor preço: R$ {df_mp['PRECO_NUM'].min():.2f}")
        print(f"   Maior preço: R$ {df_mp['PRECO_NUM'].max():.2f}")
        if df_mp['AVALIACAO'].max() > 0:
            print(f"   Avaliação média: {df_mp['AVALIACAO'].mean():.2f}")
    
    return df_produto.sort_values('PRECO_NUM')
