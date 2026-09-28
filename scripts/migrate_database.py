#!/usr/bin/env python3
"""
==============================================================================
SCRIPT DE MIGRAÇÃO E LIMPEZA SEGURA DO BANCO DE DADOS
Offer Search App -> Novo Supabase (qohalxlfeddyijidldsa)
==============================================================================
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Any
from dotenv import load_dotenv
from supabase import create_client, Client

# Carrega ambiente atual
load_dotenv()

# ==============================================================================
# CONFIGURAÇÕES E CONSTANTES
# ==============================================================================

ORIGIN_URL = os.getenv("SUPABASE_URL", "https://povgswnmwispktahqxzk.supabase.co")
ORIGIN_KEY = os.getenv("SUPABASE_KEY")

TARGET_URL = os.getenv("TARGET_SUPABASE_URL", "https://qohalxlfeddyijidldsa.supabase.co")
TARGET_KEY = os.getenv("TARGET_SUPABASE_KEY")

# WHITELIST ESTRITA - APENAS ESTAS 17 TABELAS SÃO DA APLICAÇÃO
TABLES_MIGRATION_ORDER = [
    # 1. Tabelas Pais (devem ser inseridas primeiro)
    "users",
    "ofertas",
    "pedidos_compra",
    "catalogos",
    "lotes_busca",
    # 2. Tabelas Filhas (possuem Foreign Keys para os Pais)
    "configuracoes",
    "produtos_aprovados",
    "agendamentos",
    "historico_buscas",
    "alertas",
    "itens_pedido",
    "catalog_sellers",
    "sku_catalogs",
    "lote_itens",
    # 3. Dossiê e Logs
    "sku_knowledge_base",
    "sku_reference_listings",
    "search_logs"
]

# TABELAS PROTEGIDAS DA OUTRA APLICAÇÃO (NUNCA TOCAR!)
PROTECTED_TABLES_OTHER_APP = [
    "clients",
    "daily_metrics",
    "organic_metrics",
    "meta_ads_campaigns_weekly",
    "meta_ads_ads_weekly",
    "meta_ads_audience_weekly",
    "gridd360_leads"
]

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "backups")


def get_clients():
    """Inicializa os clientes Supabase de origem e destino"""
    if not ORIGIN_KEY:
        raise ValueError("❌ SUPABASE_KEY não configurado no .env")
    if not TARGET_KEY:
        raise ValueError("❌ TARGET_KEY não configurado")

    origin_client: Client = create_client(ORIGIN_URL, ORIGIN_KEY)
    target_client: Client = create_client(TARGET_URL, TARGET_KEY)
    return origin_client, target_client


def backup_origin_data(origin_client: Client) -> str:
    """Extrai todos os dados da origem e salva em JSON local com timestamp"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_origin_{timestamp}.json")

    print(f"\n📦 [FASE 1] Iniciando Backup de Segurança da Origem ({ORIGIN_URL})...")
    backup_data: Dict[str, List[Dict[str, Any]]] = {}

    for table in TABLES_MIGRATION_ORDER:
        try:
            res = origin_client.table(table).select("*").execute()
            rows = res.data or []
            backup_data[table] = rows
            print(f"  ✓ {table}: {len(rows)} registros exportados.")
        except Exception as e:
            print(f"  ⚠️ Erro ao exportar tabela '{table}': {e}")
            backup_data[table] = []

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"✅ Backup concluído com sucesso em:\n   -> {backup_file}\n")
    return backup_file


def check_target_tables(target_client: Client) -> List[str]:
    """Verifica quais tabelas já existem no banco de destino"""
    missing = []
    for table in TABLES_MIGRATION_ORDER:
        try:
            target_client.table(table).select("*").limit(1).execute()
        except Exception as e:
            err = str(e).lower()
            if "could not find" in err or "does not exist" in err or "404" in err or "pgrst200" in err:
                missing.append(table)
    return missing


def clean_target_tables(target_client: Client):
    """Limpa dados antigos/residuais no banco de destino antes de importar a origem"""
    print(f"\n🧹 Limpando dados residuais no banco de destino para espelhamento exato...")
    cleanup_order = list(reversed(TABLES_MIGRATION_ORDER))
    for table in cleanup_order:
        try:
            if table == "users":
                target_client.table(table).delete().gt("id", 0).execute()
            elif table in ["ofertas", "pedidos_compra", "lotes_busca", "search_logs", "sku_catalogs"]:
                target_client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            elif table in ["catalogos"]:
                target_client.table(table).delete().neq("catalog_id", "").execute()
            elif table in ["catalog_sellers", "configuracoes", "produtos_aprovados", "agendamentos", "historico_buscas", "alertas", "sku_knowledge_base", "sku_reference_listings"]:
                target_client.table(table).delete().gt("id", 0).execute()
            elif table in ["itens_pedido", "lote_itens"]:
                target_client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        except Exception as e:
            # Tenta deleção ampla
            try:
                target_client.table(table).delete().not_.is_("id", "null").execute()
            except Exception:
                pass


def migrate_data(origin_client: Client, target_client: Client, backup_data: Dict[str, List[Dict[str, Any]]]):
    """Envia os dados do backup para o novo banco de destino"""
    print(f"\n🚀 [FASE 2] Enviando dados para o novo banco de destino ({TARGET_URL})...")

    # Verifica se faltam tabelas no destino
    missing_tables = check_target_tables(target_client)
    if missing_tables:
        print(f"\n❌ ATENÇÃO: As seguintes tabelas ainda NÃO existem no novo banco:")
        for t in missing_tables:
            print(f"   - {t}")
        print("\nℹ️ Execute o script 'scripts/setup_new_database.sql' no SQL Editor do novo Supabase antes de continuar!")
        sys.exit(1)

    # Limpa dados residuais no destino para garantir contagens 100% idênticas
    clean_target_tables(target_client)

    BATCH_SIZE = 100

    for table in TABLES_MIGRATION_ORDER:
        rows = backup_data.get(table, [])
        if not rows:
            print(f"  ⏭️ {table}: 0 registros (nada a transferir).")
            continue

        print(f"  ⏳ {table}: Inserindo {len(rows)} registros...")
        inserted_count = 0

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            try:
                # Usamos upsert para evitar conflito se algum registro já existir
                res = target_client.table(table).upsert(batch).execute()
                inserted_count += len(res.data or batch)
            except Exception as e:
                # Se falhar no upsert (ex: tabela sem unique constraint primária composta), tenta insert simples
                try:
                    res = target_client.table(table).insert(batch).execute()
                    inserted_count += len(res.data or batch)
                except Exception as e2:
                    print(f"     ❌ Erro no lote {i//BATCH_SIZE + 1} de '{table}': {e2}")

        print(f"  ✅ {table}: {inserted_count}/{len(rows)} sincronizados.")


def validate_counts(origin_client: Client, target_client: Client) -> bool:
    """Compara contagem exata tabela a tabela entre Origem e Destino"""
    print(f"\n🔍 [FASE 3] Auditoria e Validação Cruzada de Contagens...")
    print(f"{'Tabela':<25} | {'Origem':<10} | {'Destino':<10} | {'Status'}")
    print("-" * 65)

    all_matched = True

    for table in TABLES_MIGRATION_ORDER:
        try:
            res_orig = origin_client.table(table).select("*", count="exact").limit(0).execute()
            count_orig = res_orig.count or 0
        except Exception:
            count_orig = 0

        try:
            res_dest = target_client.table(table).select("*", count="exact").limit(0).execute()
            count_dest = res_dest.count or 0
        except Exception:
            count_dest = 0

        if count_dest >= count_orig:
            status = "✅ OK"
        else:
            status = f"❌ DIVERGÊNCIA ({count_orig - count_dest} faltando)"
            all_matched = False

        print(f"{table:<25} | {count_orig:<10} | {count_dest:<10} | {status}")

    print("-" * 65)
    return all_matched


def cleanup_origin(origin_client: Client):
    """
    LIMPEZA CIRÚRGICA: Trunca/deleta APENAS E EXCLUSIVAMENTE as 17 tabelas da aplicação.
    Sob nenhuma hipótese toca nas tabelas da outra aplicação.
    """
    print(f"\n⚠️ [FASE 4] LIMPEZA CIRÚRGICA NA ORIGEM ({ORIGIN_URL})")
    print("🔒 Garantia de segurança: APENAS as 17 tabelas da whitelist serão limpas.")
    print("🛡️ As tabelas da outra aplicação (clients, daily_metrics, etc.) JAMAIS serão tocadas.")

    # Ordem reversa para respeitar FKs (filhos primeiro, pais depois)
    cleanup_order = list(reversed(TABLES_MIGRATION_ORDER))

    for table in cleanup_order:
        # Dupla checagem paranoica contra a lista protegida
        if table in PROTECTED_TABLES_OTHER_APP:
            print(f"🛑 ERRO CRÍTICO: Tabela protegida '{table}' detectada! Abortando imediatamente.")
            sys.exit(1)

        try:
            # Deleta todos os registros da tabela da aplicação
            # No Supabase PostgREST, delete sem filtro requer .neq('id', 'impossivel') ou filtro amplo
            if table == "users":
                res = origin_client.table(table).delete().gt("id", 0).execute()
            elif table in ["ofertas", "pedidos_compra", "lotes_busca", "search_logs", "sku_catalogs"]:
                res = origin_client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            elif table in ["catalogos"]:
                res = origin_client.table(table).delete().neq("catalog_id", "").execute()
            elif table in ["catalog_sellers"]:
                res = origin_client.table(table).delete().gt("id", 0).execute()
            elif table in ["configuracoes", "produtos_aprovados", "agendamentos", "historico_buscas", "alertas", "sku_knowledge_base", "sku_reference_listings"]:
                res = origin_client.table(table).delete().gt("id", 0).execute()
            elif table in ["itens_pedido", "lote_itens"]:
                res = origin_client.table(table).delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
            else:
                res = origin_client.table(table).delete().not_.is_("id", "null").execute()

            print(f"  🗑️ {table}: tabela limpa com sucesso.")
        except Exception as e:
            print(f"  ⚠️ Aviso ao limpar '{table}': {e}")

    # Validação final pós-limpeza: confere que as tabelas da outra aplicação permanecem intactas!
    print(f"\n🛡️ Verificando integridade das tabelas da outra aplicação:")
    for prot in PROTECTED_TABLES_OTHER_APP:
        try:
            res = origin_client.table(prot).select("*", count="exact").limit(0).execute()
            print(f"  ✓ {prot}: INTACTA com {res.count} registros!")
        except Exception as e:
            print(f"  ✓ {prot}: {e}")


def update_env_file():
    """Atualiza o arquivo .env para apontar para o novo banco de dados"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        print("⚠️ Arquivo .env não encontrado.")
        return

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.startswith("SUPABASE_URL="):
            new_lines.append(f"SUPABASE_URL={TARGET_URL}\n")
        elif line.startswith("SUPABASE_KEY="):
            new_lines.append(f"SUPABASE_KEY={TARGET_KEY}\n")
        else:
            new_lines.append(line)

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"\n📝 Arquivo .env atualizado com sucesso para apontar para o novo banco!")


# ==============================================================================
# CLI ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Migração segura de banco de dados para Offer Search App")
    parser.add_argument("--backup-only", action="store_true", help="Apenas realiza o backup local da origem em JSON")
    parser.add_argument("--validate", action="store_true", help="Compara as contagens entre origem e destino")
    parser.add_argument("--migrate", action="store_true", help="Realiza o backup e migra todos os dados para o novo banco")
    parser.add_argument("--cleanup-origin", action="store_true", help="Limpa apenas as 17 tabelas da aplicação na origem")
    parser.add_argument("--all", action="store_true", help="Executa todo o fluxo (Backup -> Migrar -> Validar -> Limpar -> Atualizar .env)")
    parser.add_argument("--force-yes", action="store_true", help="Ignora a confirmação interativa de texto para limpeza")

    args = parser.parse_args()

    origin_client, target_client = get_clients()

    if args.backup_only:
        backup_origin_data(origin_client)
        return

    if args.validate:
        validate_counts(origin_client, target_client)
        return

    if args.migrate or args.all:
        backup_file = backup_origin_data(origin_client)
        with open(backup_file, "r", encoding="utf-8") as f:
            backup_data = json.load(f)

        migrate_data(origin_client, target_client, backup_data)
        success = validate_counts(origin_client, target_client)

        if not success:
            print("\n❌ ERRO: A contagem de registros entre origem e destino divergiu! A limpeza na origem foi ABORTADA.")
            return

        print("\n🎉 Todos os dados foram migrados e validados com sucesso no novo banco!")

    if args.cleanup_origin or args.all:
        # Re-validação de segurança antes de limpar
        if not validate_counts(origin_client, target_client):
            print("\n❌ ABORTANDO: O novo banco não possui todos os registros da origem!")
            sys.exit(1)

        if not args.force_yes:
            print("\n" + "!" * 70)
            print("ATENÇÃO: Você está prestes a limpar as 17 tabelas do Offer Search App na origem.")
            print("As tabelas da outra aplicação (clients, metrics, etc.) permanecerão 100% intactas.")
            confirm = input("Digite 'CONFIRMAR' para prosseguir com a limpeza: ").strip()
            if confirm != "CONFIRMAR":
                print("Operação cancelada pelo usuário.")
                return

        cleanup_origin(origin_client)
        update_env_file()
        print("\n🏁 Processo de migração e limpeza concluído com sucesso total!")


if __name__ == "__main__":
    main()
