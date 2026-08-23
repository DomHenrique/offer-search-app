# Web Scraping Mercado Livre - Versão Melhorada com Filtro
# Coleta dados estruturados com pareamento correto e ignora seletores específicos

from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import random
import re
import os
import urllib.parse
from typing import List, Dict, Optional, Tuple

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.firefox.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    SELENIUM_AVAILABLE = True
except ImportError:
    print("Selenium não está instalado. Por favor, instale com: pip install selenium")
    SELENIUM_AVAILABLE = False

class MercadoLivreScraper:
    def __init__(self, ignored_selectors: List[str] = None):
        """
        Inicializa o scraper do Mercado Livre
        
        Args:
            ignored_selectors (List[str]): Lista de seletores CSS para ignorar durante o scraping
        """
        self.driver = None
        self.base_url = 'https://lista.mercadolivre.com.br/'
        # Seletores que devem ser ignorados (exemplo: banners, propagandas, etc.)
        self.ignored_selectors = ignored_selectors or [
            '.brand-wrapper-desktop-new__container-right',  # Seletor fornecido pelo usuário
            '.ui-search-sponsored-disclaimer',  # Anúncios patrocinados
            '.ui-search-advertising',  # Publicidade
            '.ui-search-banner',  # Banners
            '.andes-carousel',  # Carrosséis de propaganda
        ]
        
    def setup_driver(self) -> Optional[webdriver.Firefox]:
        """Configura o driver do Firefox em modo headless"""
        try:
            firefox_options = Options()
            
            # Configurações para rodar em segundo plano
            firefox_options.add_argument("--headless")
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.add_argument("--disable-gpu")
            firefox_options.add_argument("--window-size=1920,1080")
            
            # User agent realista
            firefox_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0")
            
            self.driver = webdriver.Firefox(options=firefox_options)
            
            # Remove propriedades que identificam automação
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return self.driver
        except Exception as e:
            print(f"❌ Erro ao configurar Firefox driver: {e}")
            return None

    def inject_ml_cookies(self, user_id: Optional[str] = None) -> bool:
        """
        Carrega os cookies salvos no Supabase pela extensão Chrome e injeta no WebDriver
        para navegar autenticado no Mercado Livre sem bloqueios de WAF/CAPTCHA.
        """
        if not self.driver:
            return False
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            session_data = db.get_ml_session(user_id=user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ [ML] Nenhum cookie de sessão do ML encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 [ML] Injetando {len(cookies)} cookies de sessão no WebDriver Firefox...")

            # É necessário carregar o domínio antes de injetar os cookies
            self.driver.get("https://www.mercadolivre.com.br/robots.txt")
            time.sleep(1)

            injected = 0
            for c in cookies:
                try:
                    cookie_dict = {
                        'name': c['name'],
                        'value': c['value'],
                        'path': c.get('path', '/'),
                    }
                    domain = c.get('domain', '')
                    if domain:
                        cookie_dict['domain'] = domain.lstrip('.')
                    if c.get('secure'):
                        cookie_dict['secure'] = True
                    if c.get('httpOnly'):
                        cookie_dict['httpOnly'] = True

                    self.driver.add_cookie(cookie_dict)
                    injected += 1
                except Exception:
                    pass

            print(f"✅ [ML] {injected} cookies do Mercado Livre injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ [ML] Erro ao injetar cookies do Mercado Livre: {e}")
            return False
    
    def is_element_ignored(self, element) -> bool:
        """
        Verifica se um elemento deve ser ignorado baseado nos seletores configurados
        
        Args:
            element: Elemento Selenium a ser verificado
            
        Returns:
            bool: True se o elemento deve ser ignorado, False caso contrário
        """
        try:
            # Verifica se o próprio elemento corresponde a algum seletor ignorado
            for selector in self.ignored_selectors:
                try:
                    # Tenta encontrar o seletor dentro do elemento atual
                    if element.find_elements(By.CSS_SELECTOR, selector):
                        return True
                    
                    # Verifica se o elemento atual corresponde ao seletor
                    parent = element.find_element(By.XPATH, './..')
                    if parent.find_elements(By.CSS_SELECTOR, f"{selector}"):
                        # Verifica se o elemento atual está dentro do seletor ignorado
                        ignored_elements = parent.find_elements(By.CSS_SELECTOR, selector)
                        for ignored_elem in ignored_elements:
                            if element == ignored_elem or self._is_child_of(element, ignored_elem):
                                return True
                except:
                    continue
            
            # Verifica se está dentro de um elemento ignorado percorrendo os pais
            current = element
            for _ in range(10):  # Limita a busca a 10 níveis acima
                try:
                    current = current.find_element(By.XPATH, './..')
                    class_names = current.get_attribute('class') or ''
                    
                    for selector in self.ignored_selectors:
                        selector_clean = selector.replace('.', '').replace('#', '')
                        if selector_clean in class_names:
                            return True
                except:
                    break
                    
            return False
        except:
            return False
    
    def _is_child_of(self, child_element, parent_element) -> bool:
        """Verifica se um elemento é filho de outro"""
        try:
            return self.driver.execute_script(
                "return arguments[0].contains(arguments[1]);", 
                parent_element, child_element
            )
        except:
            return False
    
    def get_page_with_selenium(self, url: str, wait_time: int = 10) -> Optional[str]:
        """Carrega a página usando Selenium"""
        if not self.driver:
            return None
            
        try:
            self.driver.get(url)
            
            # Aguarda a página carregar
            time.sleep(random.uniform(1, 3))
            
            # Aguarda elementos específicos aparecerem
            try:
                WebDriverWait(self.driver, wait_time).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except TimeoutException:
                pass
            
            # Scroll para carregar mais conteúdo
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            
            return self.driver.page_source
            
        except Exception as e:
            print(f"❌ Erro ao carregar página {url}: {e}")
            return None
            
    def parse_html_products(self, html_content: str) -> List[Dict]:
        """
        Extrai dados completos de cada produto de forma estruturada em lote via BeautifulSoup,
        executando em milissegundos sem overhead de IPC/Selenium.
        
        Args:
            html_content (str): Código HTML completo da página
            
        Returns:
            List[Dict]: Lista de dicionários com dados estruturados dos produtos
        """
        products = []
        if not html_content:
            return products

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            containers = soup.select('li.ui-search-layout__item, div.ui-search-result, div.poly-card, .ui-search-layout .ui-search-layout__item, .ui-search-results__item')
            
            print(f"🔍 [ML Fast Parser] Encontrados {len(containers)} containers de produtos no HTML")
            
            for i, container in enumerate(containers):
                try:
                    # 1. TÍTULO
                    title_elem = container.select_one(
                        'h3.poly-component__title, h2.poly-component__title, a.poly-component__title, .ui-search-item__title, h3, h2'
                    )
                    title = title_elem.text.strip() if title_elem else ''
                    if len(title) < 5:
                        continue

                    # 2. PREÇO
                    price_elem = container.select_one(
                        '.poly-price__current .andes-money-amount__fraction, .andes-money-amount__fraction, .price-tag-fraction'
                    )
                    price_str = price_elem.text.strip() if price_elem else ''
                    price_cents_elem = container.select_one(
                        '.poly-price__current .andes-money-amount__cents, .andes-money-amount__cents'
                    )
                    cents_str = price_cents_elem.text.strip() if price_cents_elem else '00'

                    price_numeric = 0.0
                    if price_str:
                        clean_num = price_str.replace('.', '').replace(',', '.')
                        if '.' not in clean_num and cents_str != '00':
                            clean_num = f"{clean_num}.{cents_str}"
                        try:
                            price_numeric = float(clean_num)
                        except Exception:
                            price_numeric = 0.0

                    price_display = f"R$ {price_str}" if price_str else ""

                    # 3. IMAGEM
                    img_elem = container.select_one(
                        'img.poly-component__picture, img.ui-search-result__image__element, img[data-src], img[src]'
                    )
                    image_url = img_elem.get('data-src') or img_elem.get('src', '') if img_elem else ''

                    # 4. URL DO PRODUTO
                    link_elem = container.select_one(
                        'a.poly-component__title, a.ui-search-link, a[href*="/MLB-"], a[href*="/p/MLB"], a[href*="MLB"]'
                    )
                    product_url = link_elem.get('href', '') if link_elem else ''
                    if product_url.startswith('/'):
                        product_url = f"https://www.mercadolivre.com.br{product_url}"

                    # 5. NOME DA LOJA / VENDEDOR
                    seller_elem = container.select_one(
                        '.poly-component__seller, .ui-search-item__group__element--seller, .ui-search-official-store-label, a[href*="/loja/"], .ui-search-seller-link, span[class*="seller"]'
                    )
                    store_name = seller_elem.text.strip() if seller_elem else ''
                    
                    if not store_name and '/loja/' in product_url:
                        m_loja = re.search(r'/loja/([^/?&#]+)', product_url)
                        if m_loja:
                            store_name = m_loja.group(1).replace('-', ' ').title()

                    # Limpeza de prefixos
                    store_name = re.sub(r'^(por\s+|vendido\s+por\s+|loja\s+oficial\s+)', '', store_name, flags=re.IGNORECASE).strip()

                    # 6. AVALIAÇÕES E REPUTAÇÃO
                    rating = 0.0
                    rating_elem = container.select_one(
                        'span.poly-reviews__rating, .ui-search-reviews__rating-number, [aria-label*="estrelas"], [aria-label*="avaliações"]'
                    )
                    if rating_elem:
                        r_txt = rating_elem.get('aria-label') or rating_elem.text
                        m_r = re.search(r'(\d+[.,]\d+)', r_txt)
                        if m_r:
                            try:
                                rating = float(m_r.group(1).replace(',', '.'))
                            except Exception:
                                pass

                    review_count = 0
                    rev_elem = container.select_one('span.poly-reviews__total, span.poly-reviews__count, .ui-search-reviews__amount')
                    if rev_elem:
                        m_rev = re.search(r'(\d+)', rev_elem.text.replace('.', ''))
                        if m_rev:
                            review_count = int(m_rev.group(1))

                    # 7. DETECÇÃO DE CATÁLOGO / OPÇÕES DE COMPRA
                    # Coleta TODOS os hrefs das âncoras do card (não só o link do título)
                    # Isso resolve anúncios patrocinados que usam tracking URL no título
                    # mas ainda têm /p/MLB em links secundários (buybox, comparação, etc.)
                    all_hrefs_in_card = [
                        a.get('href', '')
                        for a in container.select('a')
                        if a.get('href')
                    ]
                    all_hrefs_str = ' '.join(all_hrefs_in_card)

                    # Busca /p/MLB em qualquer href do card
                    p_mlb_links = [h for h in all_hrefs_in_card if '/p/MLB' in h]
                    is_catalog = bool(p_mlb_links)

                    # Se encontrou URL de catálogo em link secundário, usa ela como product_url canônica
                    if p_mlb_links and '/p/MLB' not in product_url:
                        product_url = p_mlb_links[0]
                        if product_url.startswith('/'):
                            product_url = f"https://www.mercadolivre.com.br{product_url}"

                    # Para ads patrocinados (tracking URL sem /p/MLB em nenhum link),
                    # tenta extrair catalog_id do parâmetro wid=MLB\d+
                    catalog_id_from_wid = ''
                    if not is_catalog:
                        wid_match = re.search(r'wid=(MLB\d+)', all_hrefs_str)
                        if wid_match:
                            catalog_id_from_wid = wid_match.group(1)
                            is_catalog = True
                            # Constrói URL canônica do catálogo a partir do catalog_id
                            if 'click1.mercadolivre.com' in product_url or not product_url:
                                product_url = f"https://www.mercadolivre.com.br/p/{catalog_id_from_wid}"

                    sellers_count = 1
                    buybox_min_price = 0.0

                    buybox_elem = container.select_one(
                        '.poly-component__buybox, .poly-phrase-buybox, a[href*="/s#polycard_client"], a[href*="/s?"], a[href*="/s"]'
                    )
                    if buybox_elem:
                        is_catalog = True
                        b_text = buybox_elem.text.strip()
                        m_cnt = re.search(r'(\d+)\s+produtos?\s+novos?', b_text, re.IGNORECASE)
                        if m_cnt:
                            sellers_count = int(m_cnt.group(1))
                        m_p = re.search(r'a partir de\s*R\$\s*([\d\.,]+)', b_text, re.IGNORECASE)
                        if m_p:
                            try:
                                buybox_min_price = float(m_p.group(1).replace('.', '').replace(',', '.'))
                            except Exception:
                                pass

                    if not is_catalog:
                        c_text = container.text
                        if 'opções de compra' in c_text.lower() or 'produtos novos a partir de' in c_text.lower():
                            is_catalog = True
                            m_cnt = re.search(r'(\d+)\s+produtos?\s+novos?', c_text, re.IGNORECASE)
                            if m_cnt:
                                sellers_count = int(m_cnt.group(1))

                    # 8. FRETE E PARCELAMENTO
                    c_text_lower = container.text.lower()
                    shipping_type = "Frete Grátis"
                    if 'full' in c_text_lower or container.select_one("svg[class*='full'], .poly-component__shipping--full, .ui-search-item__fulfillment"):
                        shipping_type = "FULL"
                    elif 'chegará hoje' in c_text_lower or 'flex' in c_text_lower:
                        shipping_type = "Flex"

                    inst_elem = container.select_one(".poly-price__installments, span[class*='installments']")
                    installments = inst_elem.text.strip() if inst_elem else ""

                    old_p_elem = container.select_one("s.andes-money-amount--previous .andes-money-amount__fraction, s[class*='previous'] .andes-money-amount__fraction")
                    old_price = f"R$ {old_p_elem.text.strip()}" if old_p_elem else ""

                    product_data = {
                        'title': title,
                        'price': price_display,
                        'price_numeric': price_numeric,
                        'rating': rating,
                        'review_count': review_count,
                        'image_url': image_url,
                        'product_url': product_url,
                        'store_name': store_name,
                        'is_catalog': is_catalog,
                        'catalog_id': catalog_id_from_wid,
                        'sellers_count': sellers_count,
                        'buybox_min_price': buybox_min_price,
                        'shipping_type': shipping_type,
                        'installments': installments,
                        'old_price': old_price
                    }

                    if product_data['title'] and (product_data['price_numeric'] > 0 or product_data['price']):
                        products.append(product_data)

                except Exception as e_item:
                    continue

        except Exception as e:
            print(f"❌ [ML Fast Parser] Erro no parsing HTML: {e}")

        print(f"🎯 [ML Fast Parser] Total de {len(products)} produtos extraídos com sucesso em lote!")
        return products
    
    def scrape_page(self, url: str) -> Optional[List[Dict]]:
        """
        Faz scraping de uma única página via BeautifulSoup em lote sobre o page_source
        
        Args:
            url (str): URL da página
            
        Returns:
            Optional[List[Dict]]: Lista com dados dos produtos ou None
        """
        if not self.driver:
            return None
            
        page_source = self.get_page_with_selenium(url)
        if not page_source:
            return None
        
        return self.parse_html_products(page_source)
    
    def scrape_search(self, search_term: str, n_pages: int = 1, delay_range: Tuple[float, float] = (1, 3), user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
        """
        Faz scraping de múltiplas páginas para um termo de pesquisa com injeção de sessão
        
        Args:
            search_term (str): Termo de pesquisa
            n_pages (int): Número de páginas para processar
            delay_range (Tuple[float, float]): Intervalo de delay entre páginas
            user_id (str, optional): ID do usuário para injeção de sessão do Mercado Livre
            
        Returns:
            Optional[pd.DataFrame]: DataFrame com os dados ou None
        """
        if not search_term or not search_term.strip():
            print("❌ Termo de pesquisa inválido")
            return None
        
        if not self.setup_driver():
            print("❌ Falha ao inicializar o driver")
            return None
        
        try:
            # Injeta cookies de sessão autêntica para evitar bloqueios de WAF/CAPTCHA em VPS
            self.inject_ml_cookies(user_id=user_id)

            all_products = []
            
            # Formata o termo de pesquisa para URL
            formatted_term = search_term.replace(' ', '-').lower()
            search_url = f"{self.base_url}{formatted_term}"
            
            for page in range(1, n_pages + 1):
                try:
                    # Constrói URL da página
                    if page == 1:
                        page_url = search_url
                    else:
                        page_url = f"{search_url}_Desde_{((page-1)*50)+1}"
                    
                    print(f"📄 Processando página {page}/{n_pages}: {page_url}")
                    
                    # Faz scraping da página
                    page_products = self.scrape_page(page_url)
                    
                    # Fallback Inteligente (se página 1 estiver vazia por causa do formato do slug)
                    if page == 1 and not page_products:
                        print("🔄 [ML Fallback] Slug direto vazio. Tentando busca por query string livre...")
                        query_url = f"https://lista.mercadolivre.com.br/{urllib.parse.quote_plus(search_term)}"
                        page_products = self.scrape_page(query_url)

                        if not page_products:
                            # Tenta com limpeza de termos técnicos restritivos (voltagens/potências)
                            clean_sub = re.sub(r'\b\d+v[-_\s]?(eu|br|us|uk)?\b|\b\d+w\b|\b(painel\s+br|220v-eu|127v|220v|110v)\b', '', search_term, flags=re.IGNORECASE).strip()
                            clean_sub = re.sub(r'\s+', ' ', clean_sub).strip()
                            if clean_sub and clean_sub.lower() != search_term.lower() and len(clean_sub) >= 3:
                                clean_slug = clean_sub.replace(' ', '-').lower()
                                print(f"🔄 [ML Fallback Técnico] Tentando com termo sem ruído: '{clean_sub}'...")
                                page_products = self.scrape_page(f"{self.base_url}{clean_slug}")
                    
                    if page_products:
                        all_products.extend(page_products)
                        print(f"✅ Página {page}: {len(page_products)} produtos coletados")
                    else:
                        print(f"⚠️ Página {page}: Nenhum produto encontrado")
                    
                    # Delay entre páginas (exceto na última)
                    if page < n_pages:
                        delay = random.uniform(delay_range[0], delay_range[1])
                        print(f"⏳ Aguardando {delay:.1f}s...")
                        time.sleep(delay)
                        
                except Exception as e:
                    print(f"❌ Erro na página {page}: {e}")
                    continue
            
            if not all_products:
                print("❌ Nenhum produto foi encontrado")
                return None
            
            # Converte para DataFrame
            df_data = []
            for product in all_products:
                df_data.append({
                    'TITLE': product['title'],
                    'PRICE': product['price'],
                    'PRICE_NUMERIC': product['price_numeric'],
                    'RATING': product['rating'],
                    'REVIEWS': product['review_count'],
                    'IMAGE_URL': product['image_url'],
                    'PRODUCT_URL': product['product_url'],
                    'STORE_NAME': product['store_name'],
                    'SEARCH_TERM': search_term,
                    'IS_CATALOG': product.get('is_catalog', False),
                    'CATALOG_ID': product.get('catalog_id', ''),
                    'SELLERS_COUNT': product.get('sellers_count', 1),
                    'BUYBOX_MIN_PRICE': product.get('buybox_min_price', 0.0),
                    'SHIPPING_TYPE': product.get('shipping_type', 'Frete Grátis'),
                    'INSTALLMENTS': product.get('installments', ''),
                    'OLD_PRICE': product.get('old_price', ''),
                    'SCRAPY_DATETIME': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'MARKETPLACE': 'MercadoLivre'
                })
            
            df = pd.DataFrame(df_data)
            
            print(f"🎉 Scraping concluído! Total: {len(df)} produtos")
            return df
            
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_to_csv(self, df: pd.DataFrame, search_term: str = "mercado_livre", filename: Optional[str] = None) -> str:
        """Salva DataFrame em arquivo CSV"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            search_clean = re.sub(r'[^\w\-_]', '_', search_term)[:30]
            filename = f"ml_{search_clean}_{timestamp}.csv"
        
        os.makedirs('scraped_data', exist_ok=True)
        filepath = os.path.join('scraped_data', filename)
        
        df.to_csv(filepath, index=False, encoding='utf-8')
        print(f"💾 Dados salvos em: {filepath}")
        return filepath

def scrape_mercado_livre(search_term: str, n_pages: int = 1, save_csv: bool = False, ignored_selectors: List[str] = None, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """
    Função principal para scraping do Mercado Livre
    
    Args:
        search_term (str): Termo de pesquisa
        n_pages (int): Número de páginas para processar
        save_csv (bool): Se deve salvar em CSV
        ignored_selectors (List[str]): Seletores CSS adicionais para ignorar
        user_id (str, optional): ID do usuário para injeção de sessão
        
    Returns:
        Optional[pd.DataFrame]: DataFrame com os dados ou None
    """
    scraper = MercadoLivreScraper(ignored_selectors)
    
    df = scraper.scrape_search(search_term, n_pages, user_id=user_id)
    
    if df is not None and save_csv:
        scraper.save_to_csv(df, search_term)
        
    return df

def get_mercado_livre_data(search_term: str, pages: int = 1, ignored_selectors: List[str] = None, user_id: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Função simplificada para importação em outros arquivos com suporte a sessão"""
    return scrape_mercado_livre(search_term, pages, save_csv=False, ignored_selectors=ignored_selectors, user_id=user_id)

# Exemplo de uso:
if __name__ == "__main__":
    # Scraping com o seletor ignorado
    df = scrape_mercado_livre("smartphone", n_pages=2, save_csv=True)
    
    # Ou para adicionar mais seletores ignorados:
    custom_ignored = [
        '.brand-wrapper-desktop-new__container-right',
        '.custom-ad-banner',
        '.promotional-content'
    ]
    df = scrape_mercado_livre("notebook", n_pages=1, ignored_selectors=custom_ignored)