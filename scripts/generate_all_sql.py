#!/usr/bin/env python3
"""
Script para gerar todos os comandos SQL em ordem para execução manual no Supabase
"""

import os
import sys

def generate_all_sql():
    """Gera todos os comandos SQL em ordem"""
    # Diretório dos scripts
    scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    
    # Lista todos os arquivos .sql e ordena por nome
    sql_files = [f for f in os.listdir(scripts_dir) if f.endswith('.sql')]
    sql_files.sort()
    
    print("-- COMANDOS SQL PARA EXECUTAR NO SUPABASE (em ordem)")
    print("-- Copie e cole cada bloco de comando no SQL Editor do Supabase")
    print("-- Execute um comando de cada vez e aguarde a conclusão antes de executar o próximo")
    print()
    
    for sql_file in sql_files:
        print(f"-- {'='*50}")
        print(f"-- {sql_file}")
        print(f"-- {'='*50}")
        print()
        
        # Lê o conteúdo do script
        with open(os.path.join(scripts_dir, sql_file), 'r') as f:
            content = f.read()
        
        print(content)
        print()
        print("-- Próximo comando")
        print()

if __name__ == "__main__":
    print("-- GERADOR DE COMANDOS SQL PARA SUPABASE")
    print()
    generate_all_sql()