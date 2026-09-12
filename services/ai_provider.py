"""
services/ai_provider.py
Gerenciador agnóstico de provedores e modelos de IA para o Offer Search App.
Suporta Google Gemini, OpenAI, Anthropic Claude e Groq, com busca dinâmica
de modelos suportados via API e instanciação de modelos de chat para LangChain/LangGraph.
"""

import os
import requests
from typing import List, Dict, Any, Optional

SUPPORTED_PROVIDERS = [
    {
        "id": "google",
        "name": "Google Gemini",
        "description": "Excelente velocidade, custo ultrabaixo e suporte nativo a Structured Output.",
        "default_model": "gemini-2.0-flash",
        "key_env_name": "GEMINI_API_KEY",
        "curated_models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Recomendado - Mais Rápido)"},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro (Maior Raciocínio)"},
        ]
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "description": "Modelos GPT-4o e GPT-4o mini consagrados para precisão e aderência a schemas.",
        "default_model": "gpt-4o-mini",
        "key_env_name": "OPENAI_API_KEY",
        "curated_models": [
            {"id": "gpt-4o-mini", "name": "GPT-4o mini (Econômico e Rápido)"},
            {"id": "gpt-4o", "name": "GPT-4o (Alta Precisão)"},
            {"id": "o3-mini", "name": "o3-mini (Raciocínio Rápido)"},
        ]
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "description": "Modelos Claude 3.5 com excelente capacidade analítica e de comparação textual.",
        "default_model": "claude-3-5-haiku-latest",
        "key_env_name": "ANTHROPIC_API_KEY",
        "curated_models": [
            {"id": "claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku (Rápido e Preciso)"},
            {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet (Máxima Precisão)"},
            {"id": "claude-3-7-sonnet-latest", "name": "Claude 3.7 Sonnet (Última Geração)"},
        ]
    },
    {
        "id": "groq",
        "name": "Groq",
        "description": "Latência quase instantânea para inferência de modelos open source como Llama 3.3.",
        "default_model": "llama-3.3-70b-versatile",
        "key_env_name": "GROQ_API_KEY",
        "curated_models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile (Recomendado)"},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant (Ultrarrápido)"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B"},
        ]
    }
]


def list_supported_providers() -> List[Dict[str, Any]]:
    """Retorna os metadados dos provedores suportados pelo sistema."""
    return SUPPORTED_PROVIDERS


def fetch_available_models(provider: str, api_key: str) -> Dict[str, Any]:
    """
    Testa a chave da API e busca dinamicamente os modelos suportados junto ao provedor.
    Retorna {'success': bool, 'models': List[Dict], 'error': Optional[str]}.
    """
    provider = str(provider or "").strip().lower()
    api_key = str(api_key or "").strip()

    if not api_key:
        return {"success": False, "models": [], "error": "A chave da API não foi informada."}

    matched_provider = next((p for p in SUPPORTED_PROVIDERS if p["id"] == provider), None)
    if not matched_provider:
        return {"success": False, "models": [], "error": f"Provedor '{provider}' não suportado."}

    try:
        # 1. Google Gemini
        if provider == "google":
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                err_msg = resp.json().get("error", {}).get("message", resp.text)
                return {"success": False, "models": [], "error": f"Google API Error ({resp.status_code}): {err_msg}"}
            
            data = resp.json()
            models = []
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                display = m.get("displayName") or name
                methods = m.get("supportedGenerationMethods", [])
                # Filtra modelos que suportam geração de conteúdo
                if "generateContent" in methods and not any(x in name.lower() for x in ["embedding", "imagen", "aqa"]):
                    models.append({
                        "id": name,
                        "name": f"{display} ({name})",
                        "description": m.get("description", "")
                    })
            if not models:
                models = matched_provider["curated_models"]
            return {"success": True, "models": models}

        # 2. OpenAI
        elif provider == "openai":
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=10)
            if resp.status_code != 200:
                err_msg = resp.json().get("error", {}).get("message", resp.text)
                return {"success": False, "models": [], "error": f"OpenAI Error ({resp.status_code}): {err_msg}"}

            data = resp.json()
            allowed_prefixes = ["gpt-4o", "gpt-4-turbo", "o1", "o3", "chatgpt"]
            models = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                if any(mid.startswith(p) for p in allowed_prefixes) and not any(x in mid for x in ["audio", "realtime", "transcription"]):
                    models.append({
                        "id": mid,
                        "name": mid,
                        "description": "Modelo oficial OpenAI"
                    })
            # Ordena com gpt-4o e mini primeiro
            models.sort(key=lambda x: (not x["id"].startswith("gpt-4o-mini"), not x["id"].startswith("gpt-4o"), x["id"]))
            if not models:
                models = matched_provider["curated_models"]
            return {"success": True, "models": models}

        # 3. Groq
        elif provider == "groq":
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            if resp.status_code != 200:
                err_msg = resp.json().get("error", {}).get("message", resp.text)
                return {"success": False, "models": [], "error": f"Groq Error ({resp.status_code}): {err_msg}"}

            data = resp.json()
            models = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                if m.get("active", True) and not "whisper" in mid:
                    models.append({
                        "id": mid,
                        "name": mid,
                        "description": f"Desenvolvido por {m.get('owned_by', 'Groq')}"
                    })
            if not models:
                models = matched_provider["curated_models"]
            return {"success": True, "models": models}

        # 4. Anthropic Claude
        elif provider == "anthropic":
            # Testa chave fazendo chamada com cabeçalho Anthropic
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            # Tenta listar modelos da Anthropic
            resp = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                models = [{"id": m.get("id"), "name": m.get("display_name") or m.get("id"), "description": ""} for m in data.get("data", [])]
                if models:
                    return {"success": True, "models": models}
            elif resp.status_code in [401, 403]:
                return {"success": False, "models": [], "error": "Chave Anthropic inválida ou sem permissão."}

            # Retorna modelos padrão curados caso endpoint de lista não esteja ativo na chave
            return {"success": True, "models": matched_provider["curated_models"]}

    except Exception as e:
        return {"success": False, "models": [], "error": f"Erro de comunicação: {str(e)}"}

    return {"success": False, "models": [], "error": "Provedor não processado."}


def get_chat_model(provider: str, model_name: str, api_key: str, temperature: float = 0.1):
    """
    Retorna uma instância de ChatModel do LangChain compatível com o provedor selecionado.
    """
    provider = str(provider or "").strip().lower()
    model_name = str(model_name or "").strip()
    api_key = str(api_key or "").strip()

    if not api_key:
        raise ValueError("Chave de API não configurada.")

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name or "gemini-2.0-flash",
            google_api_key=api_key,
            temperature=temperature
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name or "gpt-4o-mini",
            api_key=api_key,
            temperature=temperature
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_name or "claude-3-5-haiku-latest",
            api_key=api_key,
            temperature=temperature
        )

    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_name or "llama-3.3-70b-versatile",
            api_key=api_key,
            temperature=temperature
        )

    else:
        raise ValueError(f"Provedor de IA '{provider}' desconhecido.")


def get_active_user_ai_model(user_id: str, db_manager):
    """
    Carrega a configuração ativa de IA do usuário (ou variáveis de ambiente como fallback)
    e retorna o ChatModel pronto para uso nos grafos de agentes.
    """
    try:
        user_uuid = db_manager._get_user_uuid(user_id) if hasattr(db_manager, "_get_user_uuid") else user_id
        # Busca configurações do usuário na tabela configuracoes
        raw_configs = db_manager.get_user_configs(user_id) if hasattr(db_manager, "get_user_configs") else []
        if isinstance(raw_configs, list):
            configs = {c.get("chave"): c.get("valor") for c in raw_configs if isinstance(c, dict)}
        elif isinstance(raw_configs, dict):
            configs = raw_configs
        else:
            configs = {}
    except Exception:
        configs = {}

    provider = configs.get("AI_PROVIDER") or os.environ.get("AI_PROVIDER", "google")
    api_key = configs.get("AI_API_KEY") or os.environ.get("AI_API_KEY") or os.environ.get(f"{provider.upper()}_API_KEY", "")
    model_name = configs.get("AI_MODEL") or os.environ.get("AI_MODEL", "")
    
    # Se ainda não tiver model_name definido, usa o default do provedor
    if not model_name:
        p_meta = next((p for p in SUPPORTED_PROVIDERS if p["id"] == provider), None)
        model_name = p_meta["default_model"] if p_meta else "gemini-2.0-flash"

    if not api_key:
        return None, None, None

    try:
        model = get_chat_model(provider=provider, model_name=model_name, api_key=api_key)
        return model, provider, model_name
    except Exception as e:
        print(f"⚠️ Erro ao inicializar modelo de IA ativo ({provider}/{model_name}): {e}")
        return None, provider, model_name
