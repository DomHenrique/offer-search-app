#!/usr/bin/env python3
"""
Script para criar tabelas manualmente no Supabase.

Este script fornece instruções para criar as tabelas necessárias no Supabase
quando a conexão direta ao banco de dados não está disponível.
"""

import sys
import os

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
from database.table_manager import TableManager
from database.db_manager import DatabaseManager

def print_manual_instructions():
    """Imprime instruções manuais para criar as tabelas"""
    print("=" * 60)
    print("INSTRUÇÕES PARA CRIAÇÃO MANUAL DAS TABELAS")
    print("=" * 60)
    
    table_scripts = [
        '01_create_users_table.sql',
        '02_create_ofertas_table.sql',
        '03_create_produtos_aprovados_table.sql',
        '04_create_agendamentos_table.sql',
        '05_create_historico_buscas_table.sql',
        '06_create_alertas_table.sql',
        '07_create_configuracoes_table.sql',
        '08_create_triggers_and_functions.sql'
    ]
    
    script_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts')
    
    print("\nPara criar as tabelas manualmente, siga estes passos:")
    print("\n1. Acesse o painel do Supabase (https://supabase.com/dashboard)")
    print("2. Selecione seu projeto")
    print("3. Vá para a seção 'SQL Editor'")
    print("4. Execute os seguintes scripts na ordem abaixo:")
    print()
    
    for i, script_name in enumerate(table_scripts, 1):
        script_path = os.path.join(script_dir, script_name)
        if os.path.exists(script_path):
            print(f"   {i}. {script_name}")
        else:
            print(f"   {i}. {script_name} (ARQUIVO NÃO ENCONTRADO)")
    
    print("\n5. Após executar todos os scripts, as tabelas estarão criadas!")
    print("\n" + "=" * 60)

def main():
    """Função principal"""
    print("Verificando tabelas existentes...")
    
    try:
        # Inicializa os gerenciadores
        db_manager = DatabaseManager()
        table_manager = TableManager(db_manager)
        
        # Verifica quais tabelas existem
        print("\nVerificando existência das tabelas...")
        table_status = table_manager.verify_all_tables()
        
        # Mostra resultados
        print("\nStatus das tabelas:")
        for table_name, exists in table_status.items():
            status = "✅ EXISTE" if exists else "❌ NÃO EXISTE"
            print(f"   {table_name}: {status}")
        
        # Verifica se todas existem
        missing_tables = [table for table, exists in table_status.items() if not exists]
        if missing_tables:
            print(f"\n⚠️  {len(missing_tables)} tabela(s) estão faltando:")
            for table in missing_tables:
                print(f"   - {table}")
            print_manual_instructions()
        else:
            print("\n✅ Todas as tabelas necessárias já existem!")
            
        # Fecha conexão
        table_manager.close_connection()
        
    except Exception as e:
        print(f"\n❌ Erro ao verificar tabelas: {e}")
        print_manual_instructions()

if __name__ == "__main__":
    main()