import os
import pandas as pd
from datetime import datetime
from serpapi.google_search import GoogleSearch
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

# Pega a API key do SerpApi do .env
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def buscar_produtos_amazon(
    query: str,
    api_key: str = SERPAPI_KEY,
    ordenar: str = "price-desc-rank",
    device: str = "desktop"
) -> pd.DataFrame:
    """
    Busca produtos na Amazon via SerpApi e retorna DataFrame padronizado com avaliações.
    
    Args:
        query: Termo de busca
        api_key: Chave da API do SerpApi
        ordenar: Critério de ordenação
        device: Tipo de device (desktop/mobile)
    
    Returns:
        DataFrame com informações dos produtos incluindo avaliações
    """
    if not api_key:
        raise ValueError("❌ SERPAPI_KEY não encontrada no .env")

    is_default_search = False
    if not query or not query.strip():
        query = "ofertas do dia"
        is_default_search = True
    
    # Configura os parâmetros da busca
    params = {
        "engine": "amazon",
        "k": query,  # Corrigido: SerpApi Amazon espera 'k' para a query
        "api_key": api_key,
        "sort_by": ordenar,
        "device": device,
        "amazon_domain": "amazon.com.br"
    }
    
    print(f"[DEBUG Amazon] Iniciando busca para: '{query}' com parâmetros: {params}")
    # Realiza a busca
    try:
        search_result = GoogleSearch(params)
        results = search_result.get_dict()
    except Exception as e:
        print(f"[DEBUG Amazon] Erro ao buscar na SerpApi: {e}")
        return pd.DataFrame()

    print(f"[DEBUG Amazon] Resultado bruto da API: {str(results)[:1000]}...")

    # Busca produtos em diferentes seções
    product_ads = results.get("product_ads", {}).get("products", [])
    organic_results = results.get("organic_results", [])
    print(f"[DEBUG Amazon] Produtos em product_ads: {len(product_ads)} | organic_results: {len(organic_results)}")

    # Busca também em featured_products se disponível
    featured_products = []
    if "featured_products" in results:
        for section in results["featured_products"]:
            featured_products.extend(section.get("products", []))
    print(f"[DEBUG Amazon] Produtos em featured_products: {len(featured_products)}")

    produtos = product_ads + organic_results + featured_products

    if not produtos:
        print(f"⚠️ Nenhum produto encontrado para '{query}'")
        print(f"[DEBUG Amazon] Estrutura completa retornada: {results}")
        return pd.DataFrame()
    
    # Extrai dados dos produtos
    data_list = []
    
    for idx, produto in enumerate(produtos):
        print(f"[DEBUG Amazon Produto bruto {idx+1}] {produto}")
        # Dados básicos
        title = produto.get("title", "")
        price = produto.get("price", "")
        image = produto.get("thumbnail", "")
        print(f"[DEBUG Amazon Imagem] URL da imagem extraída: {image}")
        link = produto.get("link_clean", produto.get("link", ""))
        asin = produto.get("asin", "")

        # Dados de avaliação
        rating = produto.get("rating", None)
        reviews_count = produto.get("reviews", None)
        bought_last_month = produto.get("bought_last_month", "")

        # Informações adicionais
        sponsored = produto.get("sponsored", False)
        prime = produto.get("prime", False)
        badges = produto.get("badges", [])
        offers = produto.get("offers", [])
        snap_ebt = produto.get("snap_ebt_eligible", False)

        # Extração de Marca e Vendedor
        brand = produto.get("brand", "")
        if not brand:
            # Tenta extrair a marca do início do título
            if title.upper().startswith("EF ECOFLOW"):
                brand = "EF ECOFLOW"
            elif title.upper().startswith("ECOFLOW"):
                brand = "Ecoflow"
            elif title.upper().startswith("ZOUPW"):
                brand = "ZOUPW"
            elif title:
                first_word = title.split()[0]
                if len(first_word) >= 2 and not first_word.isdigit():
                    brand = first_word

        seller_name = produto.get("seller") or brand or "Amazon Brasil"

        # Detecção de Catálogo / Concorrência de Múltiplas Ofertas
        sellers_count = 1
        is_catalog = False
        offers_text = ""
        if isinstance(offers, list):
            offers_text = ", ".join([str(o) for o in offers])
            if len(offers) > 1:
                sellers_count = len(offers)
                is_catalog = True
            elif len(offers) == 1:
                m_cnt = re.search(r'(\d+)\s*(?:outras?\s*ofertas?|opções\s*de\s*compra|vendedores|ofertas?\s*a\s*partir)', str(offers[0]), re.IGNORECASE)
                if m_cnt:
                    sellers_count = int(m_cnt.group(1)) + 1
                    is_catalog = True
        elif isinstance(offers, str):
            offers_text = offers
            m_cnt = re.search(r'(\d+)\s*(?:outras?\s*ofertas?|opções\s*de\s*compra|vendedores|ofertas?\s*a\s*partir)', offers, re.IGNORECASE)
            if m_cnt:
                sellers_count = int(m_cnt.group(1)) + 1
                is_catalog = True

        # Preços
        old_price = produto.get("old_price", "")
        extracted_price = produto.get("extracted_price", None)
        price_unit = produto.get("price_unit", "")

        product_data = {
            "TITLE": title,
            "ASIN": asin,
            "PRICE": price,
            "OLD_PRICE": old_price,
            "EXTRACTED_PRICE": extracted_price,
            "PRICE_UNIT": price_unit,
            "RATING": rating,
            "REVIEWS_COUNT": reviews_count,
            "BOUGHT_LAST_MONTH": bought_last_month,
            "IMAGE_URL": image,
            "PRODUCT_URL": link,
            "STORE_NAME": seller_name,
            "BRAND": brand,
            "MARCA": brand,
            "IS_CATALOG": is_catalog,
            "SELLERS_COUNT": sellers_count,
            "SPONSORED": sponsored,
            "PRIME": prime,
            "BADGES": ", ".join(badges) if badges else "",
            "OFFERS": offers_text,
            "SNAP_EBT_ELIGIBLE": snap_ebt,
            "SEARCH_TERM": query,
            "SCRAPY_DATETIME": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "MARKETPLACE": "Amazon"
        }

        print(f"[DEBUG Amazon Produto] Dados do produto extraído: {product_data}")
        data_list.append(product_data)
    
    df = pd.DataFrame(data_list)
    
    if df.empty:
        return df
    
    # Filtro pós-scrap para a busca padrão
    if query == "ofertas do dia":
        print("[DEBUG Amazon] Aplicando filtro 'smartphone' para a busca 'ofertas do dia'.")
        df = df[df['TITLE'].str.contains('smartphone', case=False, na=False)].copy()
        print(f"[DEBUG Amazon] {len(df)} produtos restantes após o filtro.")

    # Processa preço numérico
    df["PRICE_NUMERIC"] = df.apply(_extract_price_numeric, axis=1)
    
    # Processa preço antigo numérico
    df["OLD_PRICE_NUMERIC"] = df["OLD_PRICE"].apply(_clean_price_string)
    
    # Calcula desconto percentual
    df["DISCOUNT_PERCENT"] = df.apply(_calculate_discount, axis=1)
    
    # Processa número de reviews
    df["REVIEWS_COUNT_NUMERIC"] = df["REVIEWS_COUNT"].fillna(0)
    
    # Cria categoria de rating
    df["RATING_CATEGORY"] = df["RATING"].apply(_categorize_rating)
    
    # Remove duplicatas baseado no ASIN
    df = df.drop_duplicates(subset=["ASIN"], keep="first")
    
    print(f"✅ Encontrados {len(df)} produtos únicos para '{query}'")
    
    return df

def _extract_price_numeric(row):
    """Extrai valor numérico do preço."""
    price = str(row["PRICE"])
    
    # Se já temos extracted_price, usa ele
    if pd.notna(row["EXTRACTED_PRICE"]) and row["EXTRACTED_PRICE"] > 0:
        return float(row["EXTRACTED_PRICE"])
    
    # Senão, processa o preço manualmente
    return _clean_price_string(price)

def _clean_price_string(price_str):
    """Limpa string de preço e retorna valor numérico."""
    if not price_str or price_str == "":
        return 0.0
    
    price_str = str(price_str)
    
    # Remove símbolos de moeda e espaços
    cleaned = (
        price_str
        .replace("R$", "")
        .replace("$", "")
        .replace(",", "")
        .replace(" ", "")
        .strip()
    )
    
    # Extrai apenas números e ponto decimal
    import re
    match = re.search(r'(\d+\.?\d*)', cleaned)
    
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    
    return 0.0

def _calculate_discount(row):
    """Calcula percentual de desconto."""
    if (pd.notna(row["OLD_PRICE_NUMERIC"]) and 
        row["OLD_PRICE_NUMERIC"] > 0 and 
        row["PRICE_NUMERIC"] > 0):
        
        discount = ((row["OLD_PRICE_NUMERIC"] - row["PRICE_NUMERIC"]) /
                   row["OLD_PRICE_NUMERIC"] * 100)
        return round(discount, 2)
    
    return 0.0

def _categorize_rating(rating):
    """Categoriza rating em faixas."""
    if pd.isna(rating):
        return "Sem avaliação"
    
    rating = float(rating)
    if rating >= 4.5:
        return "Excelente (4.5+)"
    elif rating >= 4.0:
        return "Muito bom (4.0-4.4)"
    elif rating >= 3.5:
        return "Bom (3.5-3.9)"
    elif rating >= 3.0:
        return "Regular (3.0-3.4)"
    else:
        return "Ruim (<3.0)"

def salvar_resultados(df: pd.DataFrame, query: str, formato: str = "csv"):
    """Salva resultados em arquivo."""
    if df.empty:
        print("❌ Nenhum dado para salvar")
        return
    
    # Cria pasta de resultados se não existir
    os.makedirs("resultados", exist_ok=True)
    
    # Nome do arquivo com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    query_clean = query.replace(" ", "_").replace("/", "_")
    filename = f"resultados/amazon_{query_clean}_{timestamp}"
    
    if formato.lower() == "csv":
        filepath = f"{filename}.csv"
        df.to_csv(filepath, index=False, encoding="utf-8")
        print(f"💾 Arquivo salvo: {filepath}")
    
    elif formato.lower() == "excel":
        filepath = f"{filename}.xlsx"
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Aba principal com todos os dados
            df.to_excel(writer, sheet_name='Todos_Produtos', index=False)
            
            # Aba com produtos bem avaliados
            df_top_rated = df[df["RATING"] >= 4.0].copy()
            if not df_top_rated.empty:
                df_top_rated.to_excel(writer, sheet_name='Bem_Avaliados', index=False)
            
            # Aba com produtos em promoção
            df_discount = df[df["DISCOUNT_PERCENT"] > 0].copy()
            if not df_discount.empty:
                df_discount.to_excel(writer, sheet_name='Em_Promocao', index=False)
        
        print(f"💾 Arquivo Excel salvo: {filepath}")

def gerar_relatorio(df: pd.DataFrame):
    """Gera relatório resumo dos produtos encontrados."""
    if df.empty:
        print("❌ Nenhum dado para relatório")
        return
    
    print("\n" + "="*50)
    print("📊 RELATÓRIO DE PRODUTOS ENCONTRADOS")
    print("="*50)
    
    print(f"🔢 Total de produtos únicos: {len(df)}")
    
    # Estatísticas de preço
    prices = df[df["PRICE_NUMERIC"] > 0]["PRICE_NUMERIC"]
    if not prices.empty:
        print(f"💰 Preço médio: ${prices.mean():.2f}")
        print(f"💰 Preço mínimo: ${prices.min():.2f}")
        print(f"💰 Preço máximo: ${prices.max():.2f}")
    
    # Estatísticas de avaliação
    ratings = df[df["RATING"].notna()]["RATING"]
    if not ratings.empty:
        print(f"⭐ Rating médio: {ratings.mean():.2f}")
        print(f"⭐ Produtos com avaliação: {len(ratings)}")
        
        # Distribuição por categoria de rating
        print("\n📈 Distribuição por qualidade:")
        rating_dist = df["RATING_CATEGORY"].value_counts()
        for categoria, count in rating_dist.items():
            percentage = (count / len(df) * 100)
            print(f"   {categoria}: {count} ({percentage:.1f}%)")
    
    # Produtos Prime
    prime_count = df["PRIME"].sum()
    print(f"🚚 Produtos Prime: {prime_count} ({prime_count/len(df)*100:.1f}%)")
    
    # Produtos patrocinados
    sponsored_count = df["SPONSORED"].sum()
    print(f"📢 Produtos patrocinados: {sponsored_count} ({sponsored_count/len(df)*100:.1f}%)")
    
    print("="*50)
