"""
tests/test_meli_integration.py
Teste de integração ao vivo com os endpoints da API do Mercado Livre.
"""

import time
from services.meli.search import MeliSearchService
from services.meli.catalog import MeliCatalogService
from scraping.unificar_dados import _meli_results_to_df


def test_live_search():
    print("\n🔍 --- TESTE 1: BUSCA DE OFERTAS VIA API OFICIAL ML (/sites/MLB/search) ---")
    service = MeliSearchService()
    
    start = time.time()
    res = service.search_offers("mochila notebook", limit=10)
    duration = time.time() - start
    
    print(f"⏱️ Tempo de resposta da API: {duration:.3f}s")
    print(f"📊 Sucesso: {res.get('success')} | Total retornado: {len(res.get('results', []))}")
    
    if res.get("results"):
        sample = res["results"][0]
        print(f"📦 Exemplo Item 1:")
        print(f"   - Título: {sample.get('title')}")
        print(f"   - Preço: R$ {sample.get('price')}")
        print(f"   - Vendedor: {sample.get('seller_name')}")
        print(f"   - É Catálogo: {sample.get('is_catalog')} (ID: {sample.get('catalog_id')})")
        print(f"   - Frete FULL: {sample.get('is_full')}")
        print(f"   - Parcelamento: {sample.get('installments_quantity')}x (Sem juros: {sample.get('is_interest_free')})")

        # Testa conversão para DataFrame
        df = _meli_results_to_df(res["results"], "mochila notebook")
        print(f"✅ DataFrame unificado gerado com {len(df)} linhas e {len(df.columns)} colunas.")
        assert not df.empty, "DataFrame não deve estar vazio"
        assert "TITULO" in df.columns, "Coluna TITULO deve estar presente"
        assert "PRECO_NUM" in df.columns, "Coluna PRECO_NUM deve estar presente"

    assert duration < 3.0, f"Tempo de resposta muito alto: {duration}s"
    print("✅ Teste 1 concluído com sucesso!")


def test_catalog_service():
    print("\n📦 --- TESTE 2: BUSCA DE CATÁLOGO OFICIAL ML (/products/search) ---")
    catalog_service = MeliCatalogService()
    
    start = time.time()
    res = catalog_service.search_catalog_products("samsung s23", limit=5)
    duration = time.time() - start
    
    print(f"⏱️ Tempo de resposta da API de Catálogo: {duration:.3f}s")
    print(f"📊 Sucesso: {res.get('success')} | Total de catálogos: {len(res.get('results', []))}")
    
    if res.get("results"):
        sample = res["results"][0]
        print(f"🏷️ Exemplo Catálogo 1:")
        print(f"   - ID Catálogo: {sample.get('catalog_id')}")
        print(f"   - Nome: {sample.get('name')}")
        print(f"   - Preço BuyBox: R$ {sample.get('price')}")
        print(f"   - Marca: {sample.get('brand')}")
        print(f"   - Imagem: {sample.get('image_url')}")

    assert duration < 4.0, f"Tempo de resposta muito alto: {duration}s"
    print("✅ Teste 2 concluído com sucesso!")


if __name__ == "__main__":
    test_live_search()
    test_catalog_service()
