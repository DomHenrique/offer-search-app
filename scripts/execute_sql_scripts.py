#!/usr/bin/env python3
"""
Script para executar todos os scripts de criação de tabelas diretamente no Supabase
"""

import os
import sys
import psycopg2
import re
from dotenv import load_dotenv
from urllib.parse import urlparse

# Adiciona o diretório raiz ao path para importar módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_postgres_connection_info():
    """Extrai as informações de conexão PostgreSQL da URL do Supabase"""
    try:
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY')
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL e SUPABASE_KEY são necessários")
        
        # Parse da URL do Supabase
        parsed = urlparse(supabase_url)
        host = parsed.hostname
        port = parsed.port or 5432
        
        # Extrai o nome do banco de dados do host (última parte antes de .supabase.co)
        # Exemplo: zekvwvhdjbqeokmspmmy.supabase.co -> zekvwvhdjbqeokmspmmy
        db_name = host.split('.')[0]
        
        return {
            'host': host,
            'port': port,
            'database': db_name,
            'user': 'postgres',
            'password': supabase_key
        }
    except Exception as e:
        print(f"❌ Erro ao extrair informações de conexão: {e}")
        return None

def execute_sql_scripts():
    """Executa todos os scripts SQL diretamente no Supabase usando psycopg2"""
    try:
        # Carrega variáveis de ambiente
        load_dotenv()
        
        # Obtém as informações de conexão
        conn_info = get_postgres_connection_info()
        if not conn_info:
            print("❌ Não foi possível obter informações de conexão!")
            return False
        
        # Conecta ao banco de dados PostgreSQL
        conn = psycopg2.connect(**conn_info)
        cursor = conn.cursor()
        
        print("✅ Conectado ao Supabase com sucesso!")
        print(f"   Host: {conn_info['host']}")
        print(f"   Database: {conn_info['database']}")
        print()
        
        # Diretório dos scripts
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        
        # Lista todos os arquivos .sql e ordena por nome
        sql_files = [f for f in os.listdir(scripts_dir) if f.endswith('.sql')]
        sql_files.sort()
        
        print("🚀 Executando scripts de criação de tabelas...")
        print()
        
        for sql_file in sql_files:
            print(f"📄 Executando {sql_file}...")
            try:
                # Lê o conteúdo do script
                with open(os.path.join(scripts_dir, sql_file), 'r') as f:
                    content = f.read()
                
                # Divide o conteúdo em comandos separados por ;
                commands = content.split(';')
                
                # Executa cada comando
                for command in commands:
                    command = command.strip()
                    if command:
                        try:
                            cursor.execute(command)
                        except Exception as cmd_error:
                            # Se for um erro de "already exists", ignoramos
                            if "already exists" in str(cmd_error).lower():
                                print(f"⚠️  Tabela/índice já existe, continuando...")
                            else:
                                raise cmd_error
                
                # Confirma as alterações
                conn.commit()
                
                print(f"✅ {sql_file} executado com sucesso!")
                print()
                
            except Exception as e:
                print(f"❌ Erro ao executar {sql_file}: {e}")
                conn.rollback()
                conn.close()
                return False
        
        # Fecha a conexão
        cursor.close()
        conn.close()
        
        print("🎉 Todos os scripts foram executados com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco de dados: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Inicializando execução dos scripts SQL...")
    print()
    
    if execute_sql_scripts():
        print("✅ Todos os scripts foram executados com sucesso!")
    else:
        print("❌ Ocorreu um erro ao executar os scripts.")