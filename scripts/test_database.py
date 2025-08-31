#!/usr/bin/env python3
"""
Script de teste para verificar conexão com o banco de dados e tabelas.
"""

import os
import sys
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variáveis de ambiente
load_dotenv()

from database.db_manager import DatabaseManager
from database.supabase_client import SupabaseDB

def test_database_connection():
    """Testa a conexão com o banco de dados"""
    print("🔍 Testando conexão com o banco de dados...")
    
    try:
        # Testa conexão com DatabaseManager
        db_manager = DatabaseManager()
        connection_ok = db_manager.test_connection()
        print(f"✅ DatabaseManager: {'Conectado' if connection_ok else 'Falha na conexão'}")
        
        # Testa conexão com SupabaseDB
        try:
            supabase_db = SupabaseDB()
            # Tenta fazer uma consulta simples
            response = supabase_db.supabase.table("users").select("id").limit(1).execute()
            print("✅ SupabaseDB: Conectado")
        except Exception as e:
            print(f"❌ SupabaseDB: Erro na conexão - {e}")
            
    except Exception as e:
        print(f"❌ DatabaseManager: Erro na conexão - {e}")

def test_table_existence():
    """Testa a existência das tabelas necessárias"""
    print("\n🔍 Verificando existência das tabelas...")
    
    required_tables = [
        "users",
        "ofertas", 
        "produtos_aprovados",
        "agendamentos",
        "historico_buscas",
        "alertas",
        "configuracoes"
    ]
    
    try:
        db_manager = DatabaseManager()
        
        for table_name in required_tables:
            try:
                # Tenta fazer uma consulta simples para verificar se a tabela existe
                response = db_manager.supabase.table(table_name).select("id").limit(1).execute()
                print(f"✅ Tabela '{table_name}': Existe")
            except Exception as e:
                error_msg = str(e).lower()
                if "could not find the table" in error_msg or "does not exist" in error_msg:
                    print(f"❌ Tabela '{table_name}': Não encontrada")
                else:
                    print(f"⚠️ Tabela '{table_name}': Erro ao verificar - {e}")
                    
    except Exception as e:
        print(f"❌ Erro ao verificar tabelas: {e}")

def test_env_variables():
    """Verifica as variáveis de ambiente necessárias"""
    print("\n🔍 Verificando variáveis de ambiente...")
    
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_KEY", 
        "SERPAPI_KEY",
        "SECRET_KEY"
    ]
    
    # Print the actual environment variables being used
    print("📝 Variáveis de ambiente atuais:")
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            # Mostra apenas o início e o fim da chave para segurança
            if var in ["SUPABASE_KEY", "SERPAPI_KEY", "SECRET_KEY"]:
                masked_value = f"{value[:10]}...{value[-5:]}" if len(value) > 15 else "***"
                print(f"   {var}: {masked_value}")
            else:
                print(f"   {var}: {value}")
        else:
            print(f"   {var}: Não definida")

if __name__ == "__main__":
    print("🧪 Teste de Conexão com Banco de Dados")
    print("=" * 40)
    
    test_env_variables()
    test_database_connection()
    test_table_existence()
    
    print("\n✅ Teste concluído!")
