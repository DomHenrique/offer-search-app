import os
import requests

def send_message(phone_number, message):
    """Envia mensagem usando a API da Evolution"""
    try:
        instance_name = os.environ.get('EVOLUTION_API_INSTANCE')
        api_key = os.environ.get('EVOLUTION_API_KEY')
        
        if not instance_name or not api_key:
            print("Variáveis de ambiente da Evolution API não configuradas")
            return False
        
        url = f"https://api.evolution-api.com/v1/instances/{instance_name}/messages/send"
        
        headers = {
            "Content-Type": "application/json",
            "apikey": api_key
        }
        
        payload = {
            "phone": phone_number,
            "message": message
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code == 201:
            print(f"Mensagem enviada para {phone_number} com sucesso")
            return True
        else:
            print(f"Erro ao enviar mensagem para {phone_number}: {response.text}")
            return False
            
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")
        return False
