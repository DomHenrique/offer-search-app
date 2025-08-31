#!/usr/bin/env python3
"""
Este script fornece instruções para configurar e inicializar o banco de dados.
"""

import os
import sys

def print_instructions():
    """Exibe as instruções de configuração do banco de dados."""
    
    print("="*80)
    print("🚀 INSTRUÇÕES PARA CONFIGURAÇÃO DO BANCO DE DADOS SUPABASE 🚀")
    print("="*80)
    print()
    print("Este assistente irá guiá-lo para criar todas as tabelas necessárias para a aplicação.")
    print()
    
    print("PASSO 1: Instale as dependências")
    print("-" * 40)
    print("Certifique-se de que todas as bibliotecas Python necessárias estão instaladas.")
    print("No terminal, na raiz do projeto, execute:")
    print("\033[93m" + "pip install -r requirements.txt" + "\033[0m")
    print()
    
    print("PASSO 2: Configure suas credenciais do Supabase")
    print("-" * 40)
    print("Você precisará de uma string de conexão direta com o banco de dados.")
    print("1. Vá para o seu projeto no Supabase.")
    print("2. Navegue até 'Project Settings' -> 'Database'.")
    print("3. Em 'Connection string', copie a URI.")
    print("4. Crie um arquivo chamado \033[93m.env\033[0m na raiz do projeto, se ainda não existir.")
    print("5. Adicione a seguinte linha ao arquivo .env, substituindo pelo seu valor:")
    print("\033[93m" + 'SUPABASE_DB_CONNECTION_STRING="postgresql://postgres:[SUA-SENHA]@db.[ID-PROJETO].supabase.co:5432/postgres"' + "\033[0m")
    print()
    
    print("PASSO 3: Execute o script de inicialização")
    print("-" * 40)
    print("O script 'init_db.py' irá se conectar ao seu banco de dados e criar todas as tabelas.")
    print("Para executá-lo, use o seguinte comando no terminal:")
    print("\033[93m" + "python3 scripts/init_db.py" + "\033[0m")
    print()
    
    print("Após a execução, seu banco de dados estará pronto para ser usado com a aplicação.")
    print("="*80)

if __name__ == "__main__":
    # Verifica se o script init_db.py existe
    init_script_path = os.path.join(os.path.dirname(__file__), 'init_db.py')
    if not os.path.exists(init_script_path):
        print("\033[91m" + "Erro: O script 'init_db.py' não foi encontrado. Certifique-se de que ele existe no diretório 'scripts'." + "\033[0m")
        sys.exit(1)
        
    print_instructions()
