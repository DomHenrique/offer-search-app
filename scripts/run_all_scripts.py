import os
import sys
from dotenv import load_dotenv

# Garante que o diretório raiz do projeto esteja no sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv(os.path.join(project_root, '.env'))

def run_database_setup():
    """
    Executa o processo de configuração do banco de dados.
    """
    print("="*80)
    print("🚀 INICIANDO CONFIGURAÇÃO DO BANCO DE DADOS 🚀")
    print("="*80)
    
    # Verifica se pelo menos uma das variáveis de conexão existe
    connection_string = os.getenv("SUPABASE_DB_CONNECTION_STRING") or os.getenv("SUPABASE_URL")
    
    if not connection_string:
        print("\033[91mErro: Nenhuma variável de conexão com o banco de dados foi encontrada.\033[0m")
        print("Para o script de migração funcionar, seu arquivo .env precisa conter uma das seguintes variáveis:")
        print("1. \033[93mSUPABASE_URL\033[0m (que você provavelmente já tem)")
        print("2. \033[93mSUPABASE_DB_CONNECTION_STRING\033[0m (para configurações manuais)")
        print("\nPor favor, verifique seu arquivo .env.")
        sys.exit(1)
        
    print("\n✅ Variável de conexão com o banco de dados encontrada.")
    print("▶️  Executando o script de inicialização do banco de dados (init_db.py)...")
    
    try:
        # Importa e chama a função principal do init_db somente após as verificações
        from scripts.init_db import init_db as init_db_main
        init_db_main()
        print("\n\033[92m🎉 Banco de dados configurado com sucesso! 🎉\033[0m")
        print("Todas as tabelas, funções e triggers foram criados.")
        
    except ImportError:
        print("\n\033[91mErro: Não foi possível importar o script 'init_db.py'.\033[0m")
        sys.exit(1)
    except Exception as e:
        print(f"\n\033[91m❌ Ocorreu um erro durante a execução do script init_db.py: {e}\033[0m")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_database_setup()
