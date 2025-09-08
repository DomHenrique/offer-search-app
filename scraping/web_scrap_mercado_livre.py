#!/usr/bin/env python3
"""
Mercado Livre scraper that handles both search terms and a default offers page.
"""
import requests
from bs4 import BeautifulSoup
import json
import re
import pandas as pd
from datetime import datetime
import os
from urllib.parse import quote_plus
from scraping.url_imagem import MercadoLivreThumbnailExtractor

class MercadoLivreScraper:
    def __init__(self):
        """Initialize the scraper"""
        self.session = requests.Session()
        self.thumbnail_extractor = MercadoLivreThumbnailExtractor()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Referer': 'https://www.mercadolivre.com.br/',
        })

    def _get_preloaded_state(self, url):
        """Fetches the page and extracts the __PRELOADED_STATE__ JSON data."""
        try:
            response = self.session.get(url, timeout=30)
            print(f"✅ Status: {response.status_code} for URL: {url}")
            
            if response.status_code != 200:
                print(f"❌ Failed to load page: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            scripts = soup.find_all('script')
            preloaded_state_script = None
            for script in scripts:
                if script.string and '__PRELOADED_STATE__' in script.string:
                    preloaded_state_script = script.string
                    break
            
            if not preloaded_state_script:
                print("❌ Could not find __PRELOADED_STATE__ script")
                return None
            
            match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*({.*?});', preloaded_state_script, re.DOTALL)
            if not match:
                print("❌ Could not extract JSON from script")
                return None
            
            json_text = match.group(1)
            return json.loads(json_text)
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            return None
        except Exception as e:
            print(f"❌ Error fetching or parsing page: {e}")
            import traceback
            traceback.print_exc()
            return None

    def scrape_offers_page(self, category="MLB1051", limit=50):
        """Scrapes the default offers page."""
        url = f"https://www.mercadolivre.com.br/ofertas?category={category}"
        print(f"🔄 Loading default offers page: {url}")
        data = self._get_preloaded_state(url)
        if not data:
            return []
        products = self._extract_products_from_offers_data(data)
        return products[:limit]

    def scrape_search_page(self, search_term, limit=50):
        """Scrapes a search results page."""
        search_url_encoded = quote_plus(search_term)
        url = f"https://lista.mercadolivre.com.br/{search_url_encoded}"
        print(f"🔄 Loading search page: {url}")
        data = self._get_preloaded_state(url)
        if not data:
            return []
        products = self._extract_products_from_search_data(data)
        return products[:limit]

    def _extract_products_from_offers_data(self, data):
        """Extracts products from the __PRELOADED_STATE__ of an offers page."""
        products = []
        try:
            items = data.get('data', {}).get('items', [])
            print(f"🎯 Found {len(items)} items in offers data")
            for item in items:
                try:
                    card = item.get('card', {})
                    metadata = card.get('metadata', {})
                    components = card.get('components', [])
                    
                    product = {
                        'title': '', 'price': 0, 'original_price': 0, 'discount': 0,
                        'brand': '', 'store_name': '', 'image_url': '',
                        'product_url': metadata.get('url', ''),
                        'product_id': metadata.get('id', ''),
                        'position': item.get('position', 0)
                    }
                    
                    for component in components:
                        component_type = component.get('type', '')
                        if component_type == 'title':
                            product['title'] = component.get('title', {}).get('text', '')
                        elif component_type == 'brand':
                            product['brand'] = component.get('brand', {}).get('text', '')
                        elif component_type == 'price':
                            price_data = component.get('price', {})
                            product['price'] = price_data.get('current_price', {}).get('value', 0)
                            product['original_price'] = price_data.get('previous_price', {}).get('value', product['price'])
                            if product['original_price'] > 0 and product['price'] > 0:
                                product['discount'] = round(((product['original_price'] - product['price']) / product['original_price']) * 100, 2)
                        elif component_type == 'seller':
                            product['store_name'] = component.get('seller', {}).get('text', '')
                        elif component_type == 'pictures':
                            pictures = component.get('pictures', {}).get('pictures', [])
                            if pictures and pictures[0].get('id'):
                                product['image_url'] = f"https://http2.mlstatic.com/D_NQ_NP_{pictures[0]['id']}-O.webp"
                    
                    if not product.get('image_url') and product.get('product_url'):
                        print(f"🖼️ No image found for {product['title']}. Trying to extract from product page...")
                        thumbnail = self.thumbnail_extractor.extract_thumbnail(f"https://{product['product_url']}", download=False)
                        if thumbnail:
                            product['image_url'] = thumbnail
                            print(f"✅ Found image: {thumbnail}")

                    if product['title']:
                        products.append(product)
                except Exception as e:
                    print(f"❌ Error processing offer item: {e}")
            print(f"✅ Successfully extracted {len(products)} products from offers page")
            return products
        except Exception as e:
            print(f"❌ Error extracting products from offers data: {e}")
            return []

    def _extract_products_from_search_data(self, data):
        """Extracts products from the __PRELOADED_STATE__ of a search results page."""
        products = []
        try:
            results = data.get('initialState', {}).get('results', [])
            print(f"🎯 Found {len(results)} items in search data")
            for item in results:
                try:
                    price_info = item.get('price', {}) or {}
                    original_price_info = item.get('original_price', {}) or {}
                    
                    product = {
                        'title': item.get('title', ''),
                        'price': price_info.get('amount', 0),
                        'original_price': original_price_info.get('amount', price_info.get('amount', 0)),
                        'discount': (item.get('discount') or {}).get('value'),
                        'brand': item.get('brand', ''),
                        'store_name': (item.get('seller') or {}).get('nickname', ''),
                        'image_url': f"https://http2.mlstatic.com/D_NQ_NP_{item.get('thumbnail_id')}-O.webp" if item.get('thumbnail_id') else '',
                        'product_url': item.get('permalink', ''),
                        'product_id': item.get('id', ''),
                        'position': item.get('position', 0)
                    }
                    if not product.get('image_url') and product.get('product_url'):
                        print(f"🖼️ No image found for {product['title']}. Trying to extract from product page...")
                        thumbnail = self.thumbnail_extractor.extract_thumbnail(f"https://{product['product_url']}", download=False)
                        if thumbnail:
                            product['image_url'] = thumbnail
                            print(f"✅ Found image: {thumbnail}")

                    if product['title']:
                        products.append(product)
                except Exception as e:
                    print(f"❌ Error processing search item: {e}")
            print(f"✅ Successfully extracted {len(products)} products from search page")
            return products
        except Exception as e:
            print(f"❌ Error extracting products from search data: {e}")
            return []

    def to_dataframe(self, products, search_term=""):
        """Converts a list of product dictionaries to a pandas DataFrame."""
        if not products:
            return pd.DataFrame()
        df_data = [{
            'TITLE': p.get('title', ''),
            'PRICE': f"R$ {p.get('price', 0):.2f}",
            'PRICE_NUMERIC': p.get('price', 0),
            'ORIGINAL_PRICE': f"R$ {p.get('original_price', 0):.2f}",
            'ORIGINAL_PRICE_NUMERIC': p.get('original_price', 0),
            'DISCOUNT_PERCENT': p.get('discount', 0),
            'BRAND': p.get('brand', ''),
            'STORE_NAME': p.get('store_name', ''),
            'IMAGE_URL': p.get('image_url', ''),
            'PRODUCT_URL': p.get('product_url', ''),
            'PRODUCT_ID': p.get('product_id', ''),
            'POSITION': p.get('position', 0),
            'SEARCH_TERM': search_term,
            'SCRAPY_DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'MARKETPLACE': 'MercadoLivre'
        } for p in products]
        return pd.DataFrame(df_data)

    def save_to_csv(self, df, search_term="mercado_livre"):
        """Saves a DataFrame to a CSV file."""
        if df.empty:
            return ""
        os.makedirs('scraped_data', exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        search_clean = re.sub(r'[^\w\-_]', '_', search_term)[:30]
        filename = f"ml_{search_clean}_{timestamp}.csv"
        filepath = os.path.join('scraped_data', filename)
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"💾 Saved {len(df)} products to {filepath}")
        return filepath

def scrape_mercado_livre(search_term="", limit=50, save_csv=False):
    """
    Main function to scrape Mercado Livre.
    If search_term is empty, scrapes the default offers page.
    Otherwise, scrapes the search results for the given term.
    """
    scraper = MercadoLivreScraper()
    
    if search_term:
        products = scraper.scrape_search_page(search_term, limit=limit)
    else:
        products = scraper.scrape_offers_page(limit=limit)
    
    df = scraper.to_dataframe(products, search_term)
    
    if save_csv and not df.empty:
        scraper.save_to_csv(df, search_term or "ofertas")
    
    return df

def get_mercado_livre_data(search_term="", pages=1):
    """
    Backward compatibility function. Converts pages to a limit and calls the main scraper.
    """
    limit = pages * 48
    return scrape_mercado_livre(search_term, limit=limit, save_csv=False)

if __name__ == "__main__":
    print("--- 🔍 Scraping Mercado Livre (Default Offers) ---")
    df_offers = scrape_mercado_livre(limit=5, save_csv=True)
    if not df_offers.empty:
        print(f"✅ Successfully scraped {len(df_offers)} products from offers page.")
        print(df_offers[['TITLE', 'PRICE']].head())
    else:
        print("❌ Failed to scrape products from offers page.")

    print("\n--- 🔍 Scraping Mercado Livre (Search: 'celular') ---")
    df_search = scrape_mercado_livre("celular", limit=5, save_csv=True)
    if not df_search.empty:
        print(f"✅ Successfully scraped {len(df_search)} products from search.")
        print(df_search[['TITLE', 'PRICE']].head())
    else:
        print("❌ Failed to scrape products from search.")
