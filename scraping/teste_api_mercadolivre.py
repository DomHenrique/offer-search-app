import requests
import pandas as pd
from datetime import datetime

class MercadoLivreAPI:
    BASE_URL = "https://api.mercadolibre.com"

    def __init__(self):
        pass

    def search_products(self, search_term: str, limit: int = 50) -> list:
        """
        Busca produtos na API do Mercado Livre.
        
        Args:
            search_term (str): Termo de pesquisa
            limit (int): Número de produtos a serem retornados (máximo 50)

        Returns:
            list: Lista de produtos encontrados
        """
        url = f"{self.BASE_URL}/sites/MLB/search"
        params = {
            'q': search_term,
            'limit': limit
        }
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('results', [])
        else:
            print(f"❌ Erro ao buscar produtos: {response.status_code} - {response.text}")
            return []

    def extract_product_data(self, products: list) -> list:
        """
        Extrai dados relevantes dos produtos.

        Args:
            products (list): Lista de produtos

        Returns:
            list: Lista com dados de produtos extraídos
        """
        product_data_list = []

        for product in products:
            product_data = {
                'title': product.get('title', ''),
                'price': product.get('price', 0.0),
                'image_url': product.get('thumbnail', ''),
                'product_url': product.get('permalink', ''),
                'store_name': product.get('seller', {}).get('nickname', ''),
                'rating': product.get('rating_average', 0),
                'review_count': product.get('total_reviews', 0),
            }
            product_data_list.append(product_data)

        return product_data_list
    
    def save_to_csv(self, product_data: list, search_term: str) -> str:
        """Salva os dados em um arquivo CSV."""
        df = pd.DataFrame(product_data)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ml_products_{search_term.replace(' ', '_')}_{timestamp}.csv"
        df.to_csv(filename, index=False, encoding='utf-8')
        print(f"💾 Dados salvos em: {filename}")
        return filename

def main():
    search_term = "cadernos"  # Termo de pesquisa
    api = MercadoLivreAPI()

    # Busca produtos
    products = api.search_products(search_term)

    # Extrai dados dos produtos
    product_data = api.extract_product_data(products)

    # Salva em CSV
    if product_data:
        api.save_to_csv(product_data, search_term)

if __name__ == "__main__":
    main()