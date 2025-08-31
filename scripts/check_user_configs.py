#!/usr/bin/env python3
"""
Script para verificar as configurações do usuário no banco de dados.
"""

import os
import sys
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variáveis de ambiente
load_dotenv()

from database.db_manager import DatabaseManager

def check_user_configs():
    """Verifica as configurações do usuário ID 2"""
    print("🔍 Verificando configurações do usuário ID 2...")
    
    try:
        db_manager = DatabaseManager()
        
        # Busca configurações do usuário 2
        configs = db_manager.get_user_configs("2")
        print(f"⚙️ Configurações encontradas: {configs}")
        
        # Verifica se há configurações
        if not configs:
            print("⚠️ Nenhuma configuração encontrada para o usuário 2")
            return
            
        # Mostra valores específicos
        config_dict = {config['chave']: config['valor'] for config in configs}
        print(f"SERPAPI_KEY: '{config_dict.get('SERPAPI_KEY', 'NÃO ENCONTRADA')}'")
        print(f"SUPABASE_URL: '{config_dict.get('SUPABASE_URL', 'NÃO ENCONTRADA')}'")
        print(f"SUPABASE_KEY: '{config_dict.get('SUPABASE_KEY', 'NÃO ENCONTRADA')}'")
        
    except Exception as e:
        print(f"❌ Erro ao verificar configurações: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_user_configs()