# run_scraper.py (versão modificada)
import pandas as pd
import traceback
from database.supabase_client import SupabaseDB
from scraping.unificar_dados import unificar_dados_amazon_mercadolivre, buscar_ofertas_do_dia  

def buscar_e_salvar_ofertas(termo, paginas_ml=1, user_id=None):
    """Função que busca e salva ofertas para um termo específico"""
    
    print(f"🔎 Buscando ofertas para: {termo} (user_id: {user_id or 'default'})")

    # 1) Buscar dados unificados (Amazon + Mercado Livre) com injeção de sessão
    df = unificar_dados_amazon_mercadolivre(termo, paginas_ml=paginas_ml, user_id=user_id)

    if df.empty:
        print("⚠️ Nenhum dado encontrado.")
        return []
    
    print(f"✅ {len(df)} ofertas coletadas.")

    # 2) Adicionar coluna de termo de pesquisa
    df['termo_pesquisa'] = termo

    # 3) Salvar no Supabase
    try:
        db = SupabaseDB()
        db.salvar_ofertas(df)
        print(f"💾 {len(df)} ofertas salvas no Supabase.")
    except Exception as e:
        print(f"❌ Erro ao salvar no Supabase: {e}")
        print("Detalhes do erro:")
        traceback.print_exc()

    # Convert to records and return
    results = df.to_dict('records')
    print(f"📤 Retornando {len(results)} registros para a aplicação")
    return results

def buscar_ofertas_do_dia_ml(paginas_ml=1):
    """Função que busca ofertas do dia do Mercado Livre"""
    
    print(f"🛒 Buscando ofertas do dia do Mercado Livre...")

    # 1) Buscar ofertas do dia
    df = buscar_ofertas_do_dia(paginas_ml=paginas_ml)

    if df.empty:
        print("⚠️ Nenhuma oferta do dia encontrada.")
        return []
    
    print(f"✅ {len(df)} ofertas do dia coletadas.")

    # Convert to records and return
    results = df.to_dict('records')
    print(f"📤 Retornando {len(results)} registros para a aplicação")
    return results

def main(termo="celular"):
    """Função principal que pode receber um termo"""
    return buscar_e_salvar_ofertas(termo)

if __name__ == "__main__":
    # Pode ser chamado com argumentos ou usar padrão
    import sys
    termo = sys.argv[1] if len(sys.argv) > 1 else "celular"
    main(termo)
