#!/usr/bin/env python3
"""
Script para atualizar as configurações do usuário no banco de dados.
"""

import os
import sys
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variáveis de ambiente
load_dotenv()

from database.db_manager import DatabaseManager

def update_user_configs():
    """Atualiza as configurações do usuário ID 2"""
    print("🔄 Atualizando configurações do usuário ID 2...")

    try:
        db_manager = DatabaseManager()

        # Pega as variáveis de ambiente
        serpapi_key = os.environ.get('SERPAPI_KEY', '')
        supabase_url = os.environ.get('SUPABASE_URL', '')
        supabase_key = os.environ.get('SUPABASE_KEY', '')

        print(f"🔑 SERPAPI_KEY do .env: {serpapi_key[:10]}...{serpapi_key[-5:] if len(serpapi_key) > 15 else '***'}")
        print(f"🔗 SUPABASE_URL do .env: {supabase_url}")
        print(f"🔐 SUPABASE_KEY do .env: {supabase_key[:10]}...{supabase_key[-5:] if len(supabase_key) > 15 else '***'}")

        # Atualiza as configurações do usuário
        updates = [
            ('SERPAPI_KEY', serpapi_key),
            ('SUPABASE_URL', supabase_url),
            ('SUPABASE_KEY', supabase_key)
        ]

        for chave, valor in updates:
            if valor:  # Só atualiza se o valor não estiver vazio
                success = db_manager.update_config("2", chave, valor)
                if success:
                    print(f"✅ {chave} atualizado com sucesso")
                else:
                    print(f"❌ Falha ao atualizar {chave}")
            else:
                print(f"⚠️ {chave} está vazio no .env, pulando...")

        # Verifica as configurações atualizadas
        configs = db_manager.get_user_configs("2")
        config_dict = {config['chave']: config['valor'] for config in configs}
        print(f"\n⚙️ Configurações atualizadas:")
        print(f"SERPAPI_KEY: '{config_dict.get('SERPAPI_KEY', 'NÃO ENCONTRADA')}'")
        print(f"SUPABASE_URL: '{config_dict.get('SUPABASE_URL', 'NÃO ENCONTRADA')}'")
        print(f"SUPABASE_KEY: '{config_dict.get('SUPABASE_KEY', 'NÃO ENCONTRADA')}'")

    except Exception as e:
        print(f"❌ Erro ao atualizar configurações: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_user_configs()
