#!/usr/bin/env python3
"""
Instruções para configurar o banco de dados do Offer Search App

Para configurar corretamente o banco de dados, siga estas etapas:

1. Acesse o dashboard do seu projeto Supabase
2. Vá para o SQL Editor
3. Execute os scripts na ordem numérica (01, 02, 03, etc.)

Abaixo estão os scripts que devem ser executados em ordem:
"""

import os

def print_setup_instructions():
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    
    # Lista todos os arquivos .sql e ordena por nome
    sql_files = [f for f in os.listdir(scripts_dir) if f.endswith('.sql')]
    sql_files.sort()
    
    print("=" * 60)
    print("INSTRUÇÕES PARA CONFIGURAÇÃO DO BANCO DE DADOS")
    print("=" * 60)
    print()
    print("Siga estas etapas para configurar corretamente o banco de dados:")
    print("1. Acesse o dashboard do seu projeto Supabase")
    print("2. Vá para o SQL Editor")
    print("3. Execute os scripts na ordem numérica (01, 02, 03, etc.)")
    print()
    print("ORDEM CORRETA DE EXECUÇÃO:")
    print("-" * 30)
    
    for i, sql_file in enumerate(sql_files, 1):
        print(f"{i:2d}. {sql_file}")
    
    print()
    print("=" * 60)
    print("CONTEÚDO DOS SCRIPTS (para referência)")
    print("=" * 60)
    print()
    
    for sql_file in sql_files:
        print(f"--- {sql_file} ---")
        with open(os.path.join(scripts_dir, sql_file), 'r') as f:
            print(f.read())
        print("-" * 50)
        print()

if __name__ == "__main__":
    print_setup_instructions()