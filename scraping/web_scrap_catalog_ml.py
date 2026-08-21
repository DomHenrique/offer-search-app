# scraping/web_scrap_catalog_ml.py
# Scraper de Catálogos do Mercado Livre
# Extrai lista de catálogos por termo e vendedores por catalog_id

import re
import time
import random
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional

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


# ─── Regex para extrair catalog_id de URLs do ML ─────────────────────────────

def extract_catalog_id_from_url(url: str) -> Optional[str]:
    """
    Extrai o catalog_id (ex: MLB45231994) de uma URL do Mercado Livre.
    Retorna None se a URL não for de catálogo.
    
    Padrões aceitos:
      - /p/MLB45231994/
      - /p/MLB45231994?...
      - /p/MLB45231994/s?...
    """
    if not url:
        return None
    match = re.search(r'/p/(MLB\d+)', url)
    return match.group(1) if match else None


# ─── Classe Principal ─────────────────────────────────────────────────────────

class CatalogScraper:
    """
    Scraper de catálogos do Mercado Livre.
    Responsabilidades:
      - scrape_catalog_list(): busca catálogos por termo, retorna lista deduplicada
      - scrape_catalog_sellers(): scraping de sellers de um catálogo específico
    """

    def __init__(self):
        self.driver = None
        self.search_base_url = 'https://lista.mercadolivre.com.br/'
        self.catalog_base_url = 'https://www.mercadolivre.com.br/p/{catalog_id}/s?'
        self.ignored_selectors = [
            '.ui-search-sponsored-disclaimer',
            '.ui-search-advertising',
            '.ui-search-banner',
            '.andes-carousel',
        ]

    def setup_driver(self) -> Optional[object]:
        """Configura o driver Firefox headless (mesmo padrão do MercadoLivreScraper)."""
        if not SELENIUM_AVAILABLE:
            print("❌ Selenium não disponível")
            return None
        try:
            firefox_options = Options()
            firefox_options.add_argument("--headless")
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.add_argument("--disable-gpu")
            firefox_options.add_argument("--window-size=1920,1080")
            firefox_options.add_argument(
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            )

            self.driver = webdriver.Firefox(options=firefox_options)
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
            return self.driver

        except Exception as e:
            print(f"❌ Erro ao configurar Firefox driver: {e}")
            return None

    def close_driver(self):
        """Fecha o driver se estiver aberto."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            finally:
                self.driver = None

    def _load_page(self, url: str, wait_time: int = 10) -> bool:
        """Carrega uma URL e aguarda o body estar presente. Retorna True se OK."""
        if not self.driver:
            return False
        try:
            self.driver.get(url)
            time.sleep(random.uniform(1.5, 3))
            WebDriverWait(self.driver, wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Scroll suave para carregar lazy content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(0.8)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"⚠️ Erro ao carregar página {url}: {e}")
            return False

    def _is_login_page(self) -> bool:
        """Detecta se o Selenium foi redirecionado para página de login do ML."""
        try:
            current_url = self.driver.current_url
            page_source = self.driver.page_source
            login_indicators = [
                'login.mercadolivre.com.br',
                'mercadolivre.com.br/jms/mlb/lgz',
                'id="user_id"',
                'id="password"',
                'Entrar no Mercado Livre',
                'Faça login no Mercado Livre',
            ]
            for indicator in login_indicators:
                if indicator in current_url or indicator in page_source:
                    return True
            return False
        except Exception:
            return False

    def inject_ml_cookies(self, user_id: Optional[str] = None) -> bool:
        """
        Carrega os cookies salvos no Supabase e injeta no WebDriver
        para navegar autenticado no Mercado Livre.
        """
        if not self.driver:
            return False
        try:
            from database.db_manager import DatabaseManager
            db = DatabaseManager()
            session_data = db.get_ml_session(user_id=user_id)
            if not session_data or not session_data.get('cookies'):
                print("ℹ️ Nenhum cookie de sessão do ML encontrado no banco.")
                return False

            cookies = session_data.get('cookies', [])
            print(f"🍪 Injetando {len(cookies)} cookies de sessão no Selenium...")

            # Para injetar cookies no Selenium, é obrigatório primeiro estar no domínio
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
                        # Remove leading dot if any issue
                        cookie_dict['domain'] = domain.lstrip('.')
                    if c.get('secure'):
                        cookie_dict['secure'] = True
                    if c.get('httpOnly'):
                        cookie_dict['httpOnly'] = True

                    self.driver.add_cookie(cookie_dict)
                    injected += 1
                except Exception:
                    pass

            print(f"✅ {injected} cookies do Mercado Livre injetados com sucesso!")
            return True
        except Exception as e:
            print(f"⚠️ Erro ao injetar cookies no Selenium: {e}")
            return False

    # ─── Scraping de lista de catálogos ──────────────────────────────────────

    def scrape_catalog_list(self, search_term: str, n_pages: int = 1) -> Dict:
        """
        Busca catálogos por termo de pesquisa.
        
        Fluxo:
        1. Abre a lista de resultados do ML para o termo
        2. Extrai URLs de todos os produtos
        3. Filtra apenas os que têm catalog_id (/p/MLBxxxxxx)
        4. Deduplica por catalog_id
        5. Retorna lista de catálogos com nome, imagem e catalog_id
        
        Returns:
            {
                'success': bool,
                'catalogs': [{'catalog_id', 'nome', 'imagem', 'produto_url'}],
                'error': str | None
            }
        """
        print(f"🔍 Buscando catálogos para: '{search_term}' ({n_pages} página(s))")

        if not self.setup_driver():
            return {'success': False, 'catalogs': [], 'error': 'Falha ao inicializar o driver'}

        try:
            all_products = []
            formatted_term = search_term.replace(' ', '-').lower()

            for page in range(1, n_pages + 1):
                if page == 1:
                    url = f"{self.search_base_url}{formatted_term}"
                else:
                    url = f"{self.search_base_url}{formatted_term}_Desde_{((page - 1) * 50) + 1}"

                print(f"📄 Página {page}: {url}")
                if not self._load_page(url):
                    print(f"⚠️ Falha ao carregar página {page}")
                    continue

                containers = self.driver.find_elements(By.CSS_SELECTOR, "li.ui-search-layout__item")
                print(f"   Encontrados {len(containers)} produtos")

                for container in containers:
                    try:
                        # Título
                        title = ''
                        for sel in ["h3.poly-component__title", "h2.poly-component__title",
                                    "a.poly-component__title", ".ui-search-item__title", "h3", "h2"]:
                            try:
                                el = container.find_element(By.CSS_SELECTOR, sel)
                                t = el.text.strip()
                                if len(t) > 5:
                                    title = t
                                    break
                            except Exception:
                                continue

                        # URL do produto
                        product_url = ''
                        try:
                            link = container.find_element(
                                By.CSS_SELECTOR,
                                "a[href*='mercadolivre'], a[href*='mercadolibre']"
                            )
                            product_url = link.get_attribute('href') or ''
                        except Exception:
                            pass

                        # Imagem
                        image_url = ''
                        for img_sel in [
                            "img.poly-component__picture",
                            "div.poly-card__portada img",
                            "img[src*='mlstatic']",
                            "img"
                        ]:
                            try:
                                img = container.find_element(By.CSS_SELECTOR, img_sel)
                                src = (img.get_attribute('src') or
                                       img.get_attribute('data-src') or
                                       img.get_attribute('data-lazy-src') or '')
                                if src and 'mlstatic' in src and not src.startswith('data:'):
                                    image_url = src
                                    break
                            except Exception:
                                continue

                        if title and product_url:
                            all_products.append({
                                'titulo': title,
                                'produto_url': product_url,
                                'imagem': image_url,
                            })
                    except Exception as e:
                        print(f"   ⚠️ Erro ao processar produto: {e}")
                        continue

                # Delay entre páginas
                if page < n_pages:
                    time.sleep(random.uniform(1.5, 3))

            # Filtra e deduplica por catalog_id
            seen_ids = set()
            catalogs = []

            for product in all_products:
                catalog_id = extract_catalog_id_from_url(product['produto_url'])
                if catalog_id and catalog_id not in seen_ids:
                    seen_ids.add(catalog_id)
                    catalogs.append({
                        'catalog_id': catalog_id,
                        'nome': product['titulo'],
                        'imagem': product['imagem'],
                        'produto_url': product['produto_url'],
                    })

            print(f"✅ {len(catalogs)} catálogos únicos encontrados de {len(all_products)} produtos")
            return {'success': True, 'catalogs': catalogs, 'error': None}

        except Exception as e:
            print(f"❌ Erro no scraping de lista: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'catalogs': [], 'error': str(e)}

        finally:
            self.close_driver()

    # ─── Scraping de sellers de um catálogo ──────────────────────────────────

    def scrape_catalog_sellers(self, catalog_id: str) -> Dict:
        """
        Faz scraping dos vendedores de um catálogo específico.
        
        Acessa: https://www.mercadolivre.com.br/p/<catalog_id>/s?
        
        Returns:
            {
                'success': bool,
                'sellers': [{
                    'seller_name', 'preco', 'preco_str', 'frete_gratis',
                    'frete_full', 'reputacao', 'condicao', 'is_best_offer', 'posicao'
                }],
                'error': str | None,
                'login_required': bool
            }
        """
        print(f"🏪 Buscando sellers do catálogo: {catalog_id}")

        if not self.setup_driver():
            return {
                'success': False, 'sellers': [],
                'error': 'Falha ao inicializar o driver', 'login_required': False
            }

        # Injeta cookies de sessão ativa do Mercado Livre se existirem
        self.inject_ml_cookies()

        url = f"https://www.mercadolivre.com.br/p/{catalog_id}/s?"

        try:
            if not self._load_page(url, wait_time=15):
                return {
                    'success': False, 'sellers': [],
                    'error': f'Falha ao carregar página do catálogo {catalog_id}',
                    'login_required': False
                }

            # Verifica redirecionamento de login
            if self._is_login_page():
                print("⚠️ Sessão do ML não autenticada ou expirada — redirecionado para login")
                return {
                    'success': False, 'sellers': [],
                    'error': 'Sessão do Mercado Livre expirada ou não sincronizada. Abra a extensão ML Session Sync no Chrome e clique em "Sincronizar Sessão".',
                    'login_required': True
                }

            # Aguarda sellers carregarem (lazy loading possível)
            time.sleep(2)

            # Tenta múltiplos seletores para a tabela de sellers
            seller_rows = []
            seller_selectors = [
                "div.ui-pdp-buybox__offers__item",
                ".andes-table__row--body",
                "tr.andes-table__row",
                "[class*='seller-list'] [class*='row']",
                "[class*='offers'] [class*='item']",
                "li[class*='seller']",
                ".ui-pdp-media",
            ]

            for sel in seller_selectors:
                try:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    if rows:
                        seller_rows = rows
                        print(f"   Seletor de sellers: '{sel}' → {len(rows)} itens")
                        break
                except Exception:
                    continue

            if not seller_rows:
                # Fallback: tenta extrair dados do page source com BeautifulSoup
                print("   Tentando fallback com BeautifulSoup...")
                sellers = self._extract_sellers_from_source()
            else:
                sellers = self._extract_sellers_from_elements(seller_rows)

            print(f"✅ {len(sellers)} sellers encontrados")
            return {'success': True, 'sellers': sellers, 'error': None, 'login_required': False}

        except Exception as e:
            print(f"❌ Erro no scraping de sellers: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False, 'sellers': [],
                'error': str(e), 'login_required': False
            }

        finally:
            self.close_driver()

    def _extract_sellers_from_elements(self, seller_rows: list) -> List[Dict]:
        """Extrai dados de sellers a partir dos elementos Selenium."""
        sellers = []

        for i, row in enumerate(seller_rows):
            try:
                seller = {
                    'seller_name': '',
                    'seller_id_ml': '',
                    'preco': 0.0,
                    'preco_str': '',
                    'frete_gratis': False,
                    'frete_full': False,
                    'reputacao': '',
                    'condicao': 'novo',
                    'is_best_offer': False,
                    'posicao': i + 1,
                }

                row_text = row.text.lower()

                # Nome do vendedor
                for sel in [
                    ".ui-pdp-seller__header__title",
                    "[class*='seller-name']",
                    "[class*='seller__name']",
                    "strong", "b"
                ]:
                    try:
                        el = row.find_element(By.CSS_SELECTOR, sel)
                        name = el.text.strip()
                        if name and len(name) > 1:
                            seller['seller_name'] = name
                            break
                    except Exception:
                        continue

                # Preço
                for sel in [
                    ".andes-money-amount__fraction",
                    "[class*='price-fraction']",
                    "[class*='money-amount']",
                    "span[class*='price']"
                ]:
                    try:
                        el = row.find_element(By.CSS_SELECTOR, sel)
                        price_text = el.text.strip()
                        if price_text and re.search(r'\d', price_text):
                            cleaned = re.sub(r'[^\d,.]', '', price_text)
                            cleaned = cleaned.replace('.', '').replace(',', '.')
                            seller['preco'] = float(cleaned) if cleaned else 0.0
                            seller['preco_str'] = f"R$ {price_text}"
                            break
                    except Exception:
                        continue

                # Frete
                if 'grátis' in row_text or 'gratis' in row_text or 'frete grátis' in row_text:
                    seller['frete_gratis'] = True
                if 'full' in row_text or 'mercado envios full' in row_text:
                    seller['frete_full'] = True

                # Reputação
                try:
                    rep_el = row.find_element(
                        By.CSS_SELECTOR,
                        "[class*='reputation'], [class*='thermometer'], [class*='seller-info']"
                    )
                    rep_class = rep_el.get_attribute('class') or ''
                    rep_text = rep_el.text.lower()
                    if 'green' in rep_class or 'verde' in rep_class or 'excelente' in rep_text:
                        seller['reputacao'] = 'verde'
                    elif 'yellow' in rep_class or 'amarelo' in rep_class or 'bom' in rep_text:
                        seller['reputacao'] = 'amarelo'
                    elif 'red' in rep_class or 'vermelho' in rep_class or 'regular' in rep_text:
                        seller['reputacao'] = 'vermelho'
                    else:
                        seller['reputacao'] = rep_text[:20] if rep_text else ''
                except Exception:
                    pass

                # Condição
                if 'usado' in row_text or 'recondicionado' in row_text:
                    seller['condicao'] = 'usado'
                else:
                    seller['condicao'] = 'novo'

                # Melhor oferta / destaque
                try:
                    best_el = row.find_element(
                        By.CSS_SELECTOR,
                        "[class*='best'], [class*='highlight'], [class*='winner'], [class*='destaque']"
                    )
                    if best_el:
                        seller['is_best_offer'] = True
                except Exception:
                    pass

                # Só adiciona se tem seller_name ou preço
                if seller['seller_name'] or seller['preco'] > 0:
                    sellers.append(seller)

            except Exception as e:
                print(f"   ⚠️ Erro ao processar seller {i + 1}: {e}")
                continue

        return sellers

    def _extract_sellers_from_source(self) -> List[Dict]:
        """Fallback: extrai sellers do page source usando BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            sellers = []
            # Tenta encontrar qualquer estrutura de tabela de preços/sellers
            rows = (
                soup.select('.andes-table__row--body') or
                soup.select('[class*="offers"] [class*="item"]') or
                soup.select('[class*="seller-list"] li') or
                soup.select('tr')
            )

            for i, row in enumerate(rows[:20]):  # Limita a 20 resultados
                text = row.get_text(separator=' ', strip=True)
                price_match = re.search(r'R?\$?\s*([\d.]+,\d{2})', text)
                if price_match:
                    price_str = price_match.group(1)
                    price_num = float(price_str.replace('.', '').replace(',', '.'))

                    # Tenta extrair nome do vendedor
                    seller_name = ''
                    strong_tags = row.find_all(['strong', 'b', 'span'])
                    for tag in strong_tags:
                        t = tag.get_text(strip=True)
                        if t and len(t) > 2 and not re.search(r'[\d,.]', t):
                            seller_name = t
                            break

                    sellers.append({
                        'seller_name': seller_name,
                        'seller_id_ml': '',
                        'preco': price_num,
                        'preco_str': f"R$ {price_str}",
                        'frete_gratis': 'grátis' in text.lower() or 'gratis' in text.lower(),
                        'frete_full': 'full' in text.lower(),
                        'reputacao': '',
                        'condicao': 'usado' if 'usado' in text.lower() else 'novo',
                        'is_best_offer': False,
                        'posicao': i + 1,
                    })

            return sellers

        except Exception as e:
            print(f"   ❌ Fallback BeautifulSoup falhou: {e}")
            return []


# ─── Funções de conveniência ──────────────────────────────────────────────────

def get_catalog_list(search_term: str, n_pages: int = 1) -> Dict:
    """Função simplificada para buscar lista de catálogos."""
    scraper = CatalogScraper()
    return scraper.scrape_catalog_list(search_term, n_pages)


def get_catalog_sellers(catalog_id: str) -> Dict:
    """Função simplificada para buscar sellers de um catálogo."""
    scraper = CatalogScraper()
    return scraper.scrape_catalog_sellers(catalog_id)


# ─── Teste standalone ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("TESTE 1: Busca de catálogos por termo")
    print("=" * 60)
    result = get_catalog_list("ecoflow river", n_pages=1)
    print(f"Sucesso: {result['success']}")
    if result['error']:
        print(f"Erro: {result['error']}")
    print(f"Catálogos encontrados: {len(result['catalogs'])}")
    for cat in result['catalogs'][:5]:
        print(f"  [{cat['catalog_id']}] {cat['nome'][:60]}")

    if result['catalogs']:
        print("\n" + "=" * 60)
        print(f"TESTE 2: Sellers do catálogo {result['catalogs'][0]['catalog_id']}")
        print("=" * 60)
        sellers_result = get_catalog_sellers(result['catalogs'][0]['catalog_id'])
        print(f"Sucesso: {sellers_result['success']}")
        if sellers_result['error']:
            print(f"Erro: {sellers_result['error']}")
        print(f"Sellers encontrados: {len(sellers_result['sellers'])}")
        for s in sellers_result['sellers']:
            print(f"  #{s['posicao']} {s['seller_name']} | R${s['preco']:.2f} | "
                  f"Frete: {'Grátis' if s['frete_gratis'] else 'Pago'} | "
                  f"Rep: {s['reputacao']}")
