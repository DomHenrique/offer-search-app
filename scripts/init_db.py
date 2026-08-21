import os
import psycopg2
from dotenv import load_dotenv
import time

def init_db():
    """
    Inicializa o banco de dados executando os scripts SQL em ordem.
    Usa psycopg2 para se conectar diretamente ao banco de dados PostgreSQL do Supabase.
    """
    load_dotenv()

    db_connection_string = os.environ.get("SUPABASE_DB_CONNECTION_STRING")

    if not db_connection_string:
        print("❌ A variável de ambiente SUPABASE_DB_CONNECTION_STRING não está definida.")
        print("👉 Adicione-a ao seu arquivo .env com a string de conexão do seu banco de dados Supabase.")
        return

    print("🚀 Conectando ao banco de dados Supabase...")
    
    conn = None
    try:
        conn = psycopg2.connect(db_connection_string)
        print("✅ Conexão com o banco de dados bem-sucedida!")
    except psycopg2.OperationalError as e:
        print(f"❌ Erro ao conectar ao banco de dados: {e}")
        print("👉 Verifique se a string de conexão em SUPABASE_DB_CONNECTION_STRING está correta.")
        return
    except Exception as e:
        print(f"❌ Ocorreu um erro inesperado na conexão: {e}")
        return

    # Lista de tabelas na ordem inversa de dependência para exclusão
    tables_to_drop = [
        "lote_itens",
        "lotes_busca",
        "configuracoes",
        "alertas",
        "historico_buscas",
        "agendamentos",
        "produtos_aprovados",
        "ofertas",
        "users"
    ]

    with conn.cursor() as cur:
        print("🗑️  Limpando tabelas existentes...")
        for table in tables_to_drop:
            try:
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                print(f"✅ Tabela {table} removida (se existia).")
            except psycopg2.Error as e:
                print(f"⚠️  Não foi possível remover a tabela {table}: {e}")
                conn.rollback()

    conn.commit()
    print("✅ Limpeza concluída.")
    print("-" * 40)


    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sql_files = sorted([f for f in os.listdir(scripts_dir) if f.endswith('.sql') and f.startswith(('0', '1'))])

    with conn.cursor() as cur:
        for sql_file in sql_files:
            file_path = os.path.join(scripts_dir, sql_file)
            try:
                print(f"📄 Executando script: {sql_file}...")
                with open(file_path, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                    
                sql_content = "\n".join(line for line in sql_content.split('\n') if not line.strip().startswith('--'))
                
                if sql_content.strip():
                    cur.execute(sql_content)
                    print(f"✅ Script {sql_file} executado com sucesso.")
                else:
                    print(f"⚠️ Script {sql_file} está vazio ou contém apenas comentários. Pulando.")
                
                time.sleep(0.5)

            except psycopg2.Error as e:
                print(f"❌ Erro ao executar {sql_file}: {e}")
                print("👉 A transação será revertida. Verifique o script para erros de sintaxe.")
                conn.rollback()
                conn.close()
                return
            except Exception as e:
                print(f"❌ Ocorreu um erro inesperado com {sql_file}: {e}")
                conn.rollback()
                conn.close()
                return

    conn.commit()
    print("\n🎉 Todos os scripts foram executados e as tabelas foram criadas com sucesso!")
    conn.close()

if __name__ == "__main__":
    init_db()
