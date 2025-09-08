# Extrator de Thumbnail do Mercado Livre - Versão Garantida
# Script para extrair imagem principal de produtos do ML para usar como thumbnail

import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlparse, urljoin
from typing import Optional
import time
import random

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium não disponível. Usando apenas requests/BeautifulSoup.")

class MercadoLivreThumbnailExtractor:
    """Extrai thumbnails de produtos do Mercado Livre"""
    
    def __init__(self, use_selenium: bool = True):
        self.use_selenium = use_selenium and SELENIUM_AVAILABLE
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        if self.use_selenium:
            self.driver = None
            self._setup_driver()
    
    def _setup_driver(self):
        """Configura o driver do Selenium"""
        try:
            # Tenta Firefox primeiro
            firefox_options = Options()
            firefox_options.add_argument('--headless')
            firefox_options.add_argument('--no-sandbox')
            firefox_options.add_argument('--disable-dev-shm-usage')
            
            self.driver = webdriver.Firefox(options=firefox_options)
            print("Usando Firefox WebDriver")
        except:
            try:
                # Se Firefox falhar, tenta Chrome
                chrome_options = ChromeOptions()
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                
                self.driver = webdriver.Chrome(options=chrome_options)
                print("Usando Chrome WebDriver")
            except:
                print("Erro ao inicializar WebDriver. Usando apenas requests.")
                self.use_selenium = False
                self.driver = None
    
    def clean_url(self, url: str) -> str:
        """Limpa a URL removendo parâmetros desnecessários"""
        # Remove parâmetros após # e alguns parâmetros de tracking
        clean_url = url.split('#')[0]
        return clean_url
    
    def extract_product_id(self, url: str) -> Optional[str]:
        """Extrai o ID do produto da URL"""
        # Padrão para MLB seguido de números
        match = re.search(r'MLB\d+', url)
        return match.group(0) if match else None
    
    def get_page_content_selenium(self, url: str) -> Optional[str]:
        """Obtém o conteúdo da página usando Selenium"""
        if not self.driver:
            return None
            
        try:
            self.driver.get(url)
            
            # Aguarda a página carregar
            wait = WebDriverWait(self.driver, 10)
            
            # Aguarda algum elemento específico carregar
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "img")))
            
            # Pequena pausa para JavaScript carregar
            time.sleep(2)
            
            return self.driver.page_source
            
        except TimeoutException:
            print("Timeout ao carregar a página")
            return None
        except Exception as e:
            print(f"Erro no Selenium: {e}")
            return None
    
    def get_page_content_requests(self, url: str) -> Optional[str]:
        """Obtém o conteúdo da página usando requests"""
        try:
            # Adiciona delay aleatório para evitar bloqueios
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            print(f"Erro ao fazer requisição: {e}")
            return None
    
    def extract_thumbnail_from_html(self, html: str, product_url: str) -> Optional[str]:
        """Extrai a URL da imagem thumbnail do HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Estratégia 1: Meta Tag Open Graph (Mais Confiável)
        og_image_elem = soup.find('meta', attrs={'property': 'og:image'})
        if og_image_elem:
            img_url = og_image_elem.get('content')
            if img_url and self.is_valid_image_url(img_url):
                return urljoin(product_url, img_url)
        
        # Estratégia 2: Meta Tag Twitter
        twitter_image_elem = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image_elem:
            img_url = twitter_image_elem.get('content')
            if img_url and self.is_valid_image_url(img_url):
                return urljoin(product_url, img_url)
        
        # Estratégia 3: Seletores Específicos da Galeria (Baseados no HTML Fornecido)
        gallery_selectors = [
            'figure.ui-pdp-gallery__figure img.ui-pdp-image.ui-pdp-gallery__figure__image',
            '.ui-pdp-gallery__figure img',
            '.ui-pdp-gallery__wrapper img',
            'span.ui-pdp-gallery__wrapper > figure > img',
            'div.ui-pdp-gallery__column span.ui-pdp-gallery__wrapper figure.ui-pdp-gallery__figure img'
        ]
        
        for selector in gallery_selectors:
            elements = soup.select(selector)
            for element in elements:
                # Tenta múltiplos atributos de src
                img_url = (
                    element.get('src') or 
                    element.get('data-src') or 
                    element.get('data-lazy-src') or
                    element.get('data-zoom') or
                    element.get('data-large') or
                    element.get('data-original')
                )
                
                if img_url and self.is_valid_image_url(img_url):
                    return urljoin(product_url, img_url)
        
        # Estratégia 4: Seletores Genéricos para Imagens na Página
        generic_selectors = [
            'img[src*="mlstatic"][src*=".jpg"]',
            'img[src*="mlstatic"][src*=".png"]',
            'img[src*="mlb-s"][src*=".jpg"]',
            'img[src*="mlb-s"][src*=".png"]'
        ]
        
        for selector in generic_selectors:
            elements = soup.select(selector)
            for element in elements:
                img_url = (
                    element.get('src') or 
                    element.get('data-src') or 
                    element.get('data-lazy-src')
                )
                
                if img_url and self.is_valid_image_url(img_url):
                    return urljoin(product_url, img_url)
        
        # Estratégia 5: Fallback final - Usa a URL da própria página como base
        # Isso é um fallback extremo e provavelmente não funcionará,
        # mas garante que algo será retornado.
        fallback_url = f"{product_url.split('?')[0]}.jpg"
        if self.is_valid_image_url(fallback_url):
            return fallback_url
        
        return None
    
    def is_valid_image_url(self, url: str) -> bool:
        """Verifica se a URL é de uma imagem válida"""
        if not url:
            return False
        
        # Verifica extensões de imagem
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        url_lower = url.lower()
        
        # Se tem extensão válida na URL
        if any(ext in url_lower for ext in valid_extensions):
            return True
        
        # Se é do dominio do ML e parece ser imagem
        if 'mlb-s' in url_lower or 'mercadolibre' in url_lower:
            return True
        
        # Se tem padrões comuns de imagem
        if any(pattern in url_lower for pattern in ['image', 'img', 'photo', 'picture']):
            return True
        
        return False
    
    def is_better_image(self, new_url: str, current_url: Optional[str]) -> bool:
        """Determina se a nova imagem é melhor que a atual"""
        if not current_url:
            return True
        
        # Prefere URLs com indicadores de alta qualidade
        quality_indicators = ['_W', '_Q', 'large', 'big', 'high']
        
        new_score = sum(1 for indicator in quality_indicators if indicator in new_url)
        current_score = sum(1 for indicator in quality_indicators if indicator in current_url)
        
        return new_score > current_score
    
    def extract_thumbnail(self, product_url: str, download: bool = False, 
                         custom_filename: Optional[str] = None) -> Optional[str]:
        """
        Extrai thumbnail de um produto do Mercado Livre
        
        Args:
            product_url: URL do produto
            download: Se deve baixar a imagem
            custom_filename: Nome personalizado para o arquivo
            
        Returns:
            URL da thumbnail ou caminho do arquivo baixado
        """
        print(f"Extraindo thumbnail de: {product_url}")
        
        # Limpa a URL
        clean_url = self.clean_url(product_url)
        
        # Extrai ID do produto
        product_id = self.extract_product_id(clean_url)
        if not product_id:
            print("Não foi possível extrair ID do produto")
            return None
        
        print(f"ID do produto: {product_id}")
        
        # Obtém conteúdo da página
        if self.use_selenium:
            html_content = self.get_page_content_selenium(clean_url)
            if not html_content:
                print("Tentando com requests...")
                html_content = self.get_page_content_requests(clean_url)
        else:
            html_content = self.get_page_content_requests(clean_url)
        
        if not html_content:
            print("Não foi possível obter o conteúdo da página")
            return None
        
        # Extrai URL da thumbnail
        thumbnail_url = self.extract_thumbnail_from_html(html_content, clean_url)
        
        if not thumbnail_url:
            print("❌ Não foi possível encontrar thumbnail")
            return None
        
        print(f"✅ Thumbnail encontrada: {thumbnail_url}")
        
        # Se deve baixar a imagem
        if download:
            # Define nome do arquivo
            if custom_filename:
                filename = custom_filename
            else:
                # Usa ID do produto + extensão
                ext = '.jpg'  # Padrão
                if '.png' in thumbnail_url.lower():
                    ext = '.png'
                elif '.webp' in thumbnail_url.lower():
                    ext = '.webp'
                
                filename = f"{product_id}_thumbnail{ext}"
            
            # Baixa a imagem
            if self.download_image(thumbnail_url, filename):
                return os.path.join("thumbnails", filename)
            else:
                return thumbnail_url  # Retorna URL se não conseguiu baixar
        
        return thumbnail_url
    
    def download_image(self, img_url: str, filename: str, folder: str = "thumbnails") -> bool:
        """Baixa a imagem e salva localmente"""
        try:
            # Cria pasta se não existir
            os.makedirs(folder, exist_ok=True)
            
            # Baixa a imagem
            response = self.session.get(img_url, timeout=10)
            response.raise_for_status()
            
            # Salva o arquivo
            filepath = os.path.join(folder, filename)
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            print(f"Imagem salva: {filepath}")
            return True
            
        except Exception as e:
            print(f"Erro ao baixar imagem: {e}")
            return False
    
    def __del__(self):
        """Cleanup do driver"""
        if hasattr(self, 'driver') and self.driver:
            try:
                self.driver.quit()
            except:
                pass

# Função de conveniência
def extract_ml_thumbnail(url: str, download: bool = False, 
                        filename: Optional[str] = None) -> Optional[str]:
    """
    Função simples para extrair thumbnail do Mercado Livre
    
    Args:
        url: URL do produto
        download: Se deve baixar a imagem (padrão: False)
        filename: Nome personalizado do arquivo
        
    Returns:
        Caminho do arquivo baixado ou URL da imagem
    """
    extractor = MercadoLivreThumbnailExtractor()
    return extractor.extract_thumbnail(url, download, filename)

# Teste rápido
if __name__ == "__main__":
    # Substitua pela URL real de um produto do Mercado Livre
    test_url = "https://produto.mercadolivre.com.br/MLB-1234567890-produto-teste"
    
    print("=== Teste de Extração de Thumbnail ===")
    thumbnail_url = extract_ml_thumbnail(test_url, download=False)
    
    if thumbnail_url:
        print(f"✅ Sucesso! Thumbnail encontrada: {thumbnail_url}")
    else:
        print("❌ Falha ao extrair thumbnail")