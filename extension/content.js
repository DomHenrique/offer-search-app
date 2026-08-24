/**
 * Offer Search App - In-Page Stock & Catalog Intel (Content Script)
 * Assistente de Inteligência de Estoque e Margens direto no Mercado Livre e Amazon.
 */

(function () {
  'use strict';

  // Evita múltiplas inicializações
  if (window.__OFFER_SEARCH_INTEL_INITIALIZED__) return;
  window.__OFFER_SEARCH_INTEL_INITIALIZED__ = true;

  const DEFAULT_API_URL = 'https://offer-search.hnperformancedigital.com.br';
  let cachedApiUrl = null;
  let shadowRoot = null;
  let currentIntelData = null;
  let currentCatalogId = null;
  let isCardOpen = false;
  let selectedSkuForLinking = null;

  // ─── 1. Extrator de Identificadores e Metadados da Página ─────────
  function extractProductInfo() {
    const href = window.location.href;
    let catalogId = null;
    let itemId = null;

    // Detecta /p/MLB12345678 (Catálogo Oficial do Mercado Livre)
    const pMatch = href.match(/\/p\/(MLB\d+)/i);
    if (pMatch) {
      catalogId = pMatch[1].toUpperCase();
    }

    // Procura por canonical link caso seja página de variação ou anúncio de catálogo
    if (!catalogId) {
      const canonical = document.querySelector('link[rel="canonical"]');
      if (canonical && canonical.href) {
        const canMatch = canonical.href.match(/\/p\/(MLB\d+)/i);
        if (canMatch) catalogId = canMatch[1].toUpperCase();
      }
    }

    // Detecta item MLB / MLB-123456789
    const itemMatch = href.match(/(MLB-?\d+)/i);
    if (itemMatch && !catalogId) {
      itemId = itemMatch[1].replace('-', '').toUpperCase();
    }

    // Detecta Amazon ASIN (/dp/B0... ou /gp/product/B0...)
    const asinMatch = href.match(/\/(?:dp|product)\/([A-Z0-9]{10})/i);
    if (asinMatch) {
      itemId = asinMatch[1].toUpperCase();
    }

    // Extrai Preço visível na tela
    let price = 0.0;
    const priceEl = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__fraction') ||
                    document.querySelector('.price-tag-fraction') ||
                    document.querySelector('.a-price .a-price-whole');
    if (priceEl) {
      const priceCentsEl = document.querySelector('.ui-pdp-price__second-line .andes-money-amount__cents') ||
                           document.querySelector('.price-tag-cents') ||
                           document.querySelector('.a-price .a-price-fraction');
      const whole = priceEl.textContent.replace(/\./g, '').trim();
      const cents = priceCentsEl ? priceCentsEl.textContent.trim() : '00';
      price = parseFloat(`${whole}.${cents}`) || 0.0;
    }

    // Extrai Título
    const titleEl = document.querySelector('.ui-pdp-title') || document.querySelector('#productTitle') || document.querySelector('h1');
    const title = titleEl ? titleEl.textContent.trim() : document.title;

    // Extrai Imagem Principal
    const imgEl = document.querySelector('.ui-pdp-gallery__figure img') || document.querySelector('#landingImage') || document.querySelector('meta[property="og:image"]');
    const image = imgEl ? (imgEl.src || imgEl.getAttribute('content') || '') : '';

    return {
      catalogId: catalogId || itemId,
      itemId,
      title,
      price,
      image,
      url: href
    };
  }

  // ─── 2. Carrega URL da API e Comunicação com Backend ──────────────
  async function getApiUrl() {
    if (cachedApiUrl) return cachedApiUrl;
    return new Promise(resolve => {
      chrome.storage.local.get(['apiUrl'], res => {
        cachedApiUrl = (res.apiUrl || DEFAULT_API_URL).replace(/\/+$/, '');
        resolve(cachedApiUrl);
      });
    });
  }

  async function fetchProductIntel(info) {
    const apiUrl = await getApiUrl();
    const query = new URLSearchParams({
      catalog_id: info.catalogId || '',
      item_id: info.itemId || '',
      current_price: info.price || '',
      url: info.url
    });

    try {
      const res = await fetch(`${apiUrl}/api/extension/product-intel?${query.toString()}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'include'
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn('[Offer Search Intel] Erro ao consultar backend:', err);
      return null;
    }
  }

  async function fetchInventoryList(queryStr = '') {
    const apiUrl = await getApiUrl();
    try {
      const res = await fetch(`${apiUrl}/api/extension/inventory-list?q=${encodeURIComponent(queryStr)}`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        credentials: 'include'
      });
      if (!res.ok) return [];
      const data = await res.json();
      return data.items || [];
    } catch (err) {
      return [];
    }
  }

  async function sendLinkSku(catalogId, sku, productInfo) {
    const apiUrl = await getApiUrl();
    const payload = {
      catalog_id: catalogId,
      sku: sku,
      catalog_title: productInfo.title,
      catalog_url: productInfo.url,
      catalog_image: productInfo.image,
      buybox_min_price: productInfo.price
    };

    const res = await fetch(`${apiUrl}/api/extension/link-sku`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload)
    });
    return await res.json();
  }

  // ─── 3. Injeção e Construção do Shadow DOM ────────────────────────
  function setupShadowRoot() {
    let host = document.getElementById('offer-search-root');
    if (!host) {
      host = document.createElement('div');
      host.id = 'offer-search-root';
      document.body.appendChild(host);
    }

    if (!shadowRoot) {
      shadowRoot = host.attachShadow({ mode: 'open' });
      const cssUrl = chrome.runtime.getURL('content.css');
      shadowRoot.innerHTML = `
        <link rel="stylesheet" href="${cssUrl}">
        <div id="os-widget-wrapper"></div>
      `;
    }
    return shadowRoot.getElementById('os-widget-wrapper');
  }

  // ─── 4. Renderizadores de Interface (Estilo AvantPro) ─────────────
  function formatMoney(val) {
    return (parseFloat(val) || 0.0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function renderWidget(info, intel) {
    const container = setupShadowRoot();
    if (!container) return;

    currentIntelData = intel;
    currentCatalogId = info.catalogId;

    const isLinked = Boolean(intel && intel.is_linked);
    const sku = isLinked ? intel.sku : null;

    container.innerHTML = `
      <!-- Trigger Flutuante (FAB) -->
      ${!isCardOpen ? `
        <div class="os-fab-btn" id="osTriggerBtn">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
            <polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline>
            <line x1="12" y1="22.08" x2="12" y2="12"></line>
          </svg>
          <span>Offer Search Intel</span>
          <span class="os-fab-badge ${isLinked ? 'linked' : 'unlinked'}">
            ${isLinked ? `SKU: ${sku}` : 'Avulso'}
          </span>
        </div>
      ` : `
        <!-- Card Completo de Inteligência -->
        <div class="os-card" id="osCard">
          <div class="os-card-header">
            <div class="os-card-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fde047" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
              </svg>
              <span>Inteligência de Estoque</span>
            </div>
            <div class="os-card-actions">
              <button class="os-icon-btn" id="osBtnMinimize" title="Minimizar">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          </div>

          <div class="os-card-body">
            ${!intel ? `
              <div style="background:#fee2e2; border:1px solid #fca5a5; color:#991b1b; padding:12px; border-radius:10px; font-size:11px; margin-bottom:12px;">
                <strong>⚠️ Falha de comunicação com o Offer Search App</strong>
                <p style="margin-top:4px; opacity:0.9;">Não foi possível consultar os dados do servidor. Verifique se você está conectado à rede ou se o servidor está ativo.</p>
                <button class="os-btn-primary" id="osBtnRetry" style="margin-top:10px; background:#ef4444;">
                  <span>🔄 Tentar Novamente</span>
                </button>
              </div>
            ` : `
            <!-- Status de Vínculo -->
            <div class="os-status-banner ${isLinked ? 'linked' : 'unlinked'}">
              <div>
                <strong>${isLinked ? `🟢 Vinculado: ${intel.sku}` : '⚪ Catálogo Avulso (Sem SKU)'}</strong>
                <div style="font-size:10px; opacity:0.85; margin-top:2px;">ID: ${info.catalogId || 'N/A'}</div>
              </div>
              ${isLinked ? `<button class="os-icon-btn" id="osBtnChangeSku" title="Alterar SKU" style="background:#065f46; color:#fff;">✏️</button>` : ''}
            </div>`}

            ${isLinked ? `
              <!-- Métricas Principais de Estoque -->
              <div class="os-grid-metrics">
                <div class="os-metric-box">
                  <div class="os-metric-label">Estoque Próprio</div>
                  <div class="os-metric-value highlight">${intel.estoque_total} UN</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Custo Unitário</div>
                  <div class="os-metric-value">${formatMoney(intel.preco_custo)}</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Preço Loja / PIX</div>
                  <div class="os-metric-value">${formatMoney(intel.preco_venda)}</div>
                </div>
                <div class="os-metric-box">
                  <div class="os-metric-label">Menor Preço BuyBox</div>
                  <div class="os-metric-value warning">${formatMoney(intel.buybox_min_price || info.price)}</div>
                </div>
              </div>

              <!-- Tabela de Comparativo de Margem Estimada -->
              ${intel.margin ? `
                <div class="os-breakdown">
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">Preço de Venda BuyBox:</span>
                    <strong>${formatMoney(intel.buybox_min_price || info.price)}</strong>
                  </div>
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">(-) Custo do Produto:</span>
                    <span style="color:#ef4444;">- ${formatMoney(intel.preco_custo)}</span>
                  </div>
                  <div class="os-breakdown-row">
                    <span style="color:#64748b;">(-) Taxa ML Est. (16%):</span>
                    <span style="color:#ef4444;">- ${formatMoney(intel.margin.marketplace_fee)}</span>
                  </div>
                  <div class="os-breakdown-row total">
                    <span>Margem Líquida Estimada:</span>
                    <span style="color: ${intel.margin.status_color}; font-size:14px;">
                      ${formatMoney(intel.margin.net_profit)} (${intel.margin.margin_pct}%)
                    </span>
                  </div>
                  <div style="margin-top: 6px; font-size: 11px; font-weight: 700; color: ${intel.margin.status_color}; text-align: right;">
                    ${intel.margin.status_label}
                  </div>
                </div>
              ` : ''}
            ` : `
              <!-- Seção de Vinculação Rápida de SKU -->
              <div class="os-link-section">
                <div class="os-link-title">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
                  <span>Conectar a um Produto do Estoque</span>
                </div>
                <input type="text" class="os-input" id="osSkuSearchInput" placeholder="Buscar SKU ou descrição no estoque...">
                <div class="os-sku-dropdown" id="osSkuList">
                  ${(intel && intel.suggestions && intel.suggestions.length) ? intel.suggestions.map(s => `
                    <div class="os-sku-item" data-sku="${s.sku}">
                      <div>
                        <div class="os-sku-code">${s.sku}</div>
                        <div class="os-sku-desc">${s.descricao || ''}</div>
                      </div>
                      <div style="text-align:right;">
                        <strong>${s.estoque_total} UN</strong>
                        <div style="font-size:10px; color:#64748b;">${formatMoney(s.preco_custo)}</div>
                      </div>
                    </div>
                  `).join('') : '<div style="padding:10px; text-align:center; color:#64748b; font-size:11px;">Carregando SKUs...</div>'}
                </div>
                <button class="os-btn-primary" id="osBtnSubmitLink" disabled>
                  <span>🔗 Conectar ao SKU Selecionado</span>
                </button>
              </div>
            `}
          </div>

          <div class="os-card-footer">
            <a href="${cachedApiUrl}/catalog?sku=${sku || ''}" target="_blank" class="os-app-link">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
              <span>Abrir no Offer Search App</span>
            </a>
            <span style="color:#94a3b8; font-size:10px;">v1.2</span>
          </div>
        </div>
      `}
    `;

    bindEvents(info, intel);
  }

  // ─── 5. Event Listeners no Shadow DOM ─────────────────────────────
  function bindEvents(info, intel) {
    const triggerBtn = shadowRoot.getElementById('osTriggerBtn');
    if (triggerBtn) {
      triggerBtn.addEventListener('click', () => {
        isCardOpen = true;
        renderWidget(info, intel);
      });
    }

    const minBtn = shadowRoot.getElementById('osBtnMinimize');
    if (minBtn) {
      minBtn.addEventListener('click', () => {
        isCardOpen = false;
        renderWidget(info, intel);
      });
    }

    const retryBtn = shadowRoot.getElementById('osBtnRetry');
    if (retryBtn) {
      retryBtn.addEventListener('click', async () => {
        retryBtn.disabled = true;
        retryBtn.innerHTML = '<span class="os-spinner"></span> <span>Consultando...</span>';
        const newIntel = await fetchProductIntel(info);
        renderWidget(info, newIntel);
      });
    }

    const changeSkuBtn = shadowRoot.getElementById('osBtnChangeSku');
    if (changeSkuBtn) {
      changeSkuBtn.addEventListener('click', () => {
        intel.is_linked = false;
        renderWidget(info, intel);
      });
    }

    // Seção de busca de SKU no Dropdown
    const searchInput = shadowRoot.getElementById('osSkuSearchInput');
    const skuList = shadowRoot.getElementById('osSkuList');
    const submitBtn = shadowRoot.getElementById('osBtnSubmitLink');

    if (searchInput && skuList) {
      let debounceTimeout = null;
      searchInput.addEventListener('input', () => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(async () => {
          const q = searchInput.value.trim();
          skuList.innerHTML = '<div style="padding:10px; text-align:center; color:#64748b; font-size:11px;">Buscando...</div>';
          const items = await fetchInventoryList(q);
          if (!items.length) {
            skuList.innerHTML = '<div style="padding:10px; text-align:center; color:#94a3b8; font-size:11px;">Nenhum SKU encontrado</div>';
            return;
          }
          skuList.innerHTML = items.map(s => `
            <div class="os-sku-item ${selectedSkuForLinking === s.sku ? 'selected' : ''}" data-sku="${s.sku}">
              <div>
                <div class="os-sku-code">${s.sku}</div>
                <div class="os-sku-desc">${s.descricao || ''}</div>
              </div>
              <div style="text-align:right;">
                <strong>${s.estoque_total} UN</strong>
                <div style="font-size:10px; color:#64748b;">${formatMoney(s.preco_custo)}</div>
              </div>
            </div>
          `).join('');
          attachSkuItemClicks();
        }, 250);
      });

      function attachSkuItemClicks() {
        shadowRoot.querySelectorAll('.os-sku-item').forEach(item => {
          item.addEventListener('click', () => {
            shadowRoot.querySelectorAll('.os-sku-item').forEach(el => el.classList.remove('selected'));
            item.classList.add('selected');
            selectedSkuForLinking = item.getAttribute('data-sku');
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.innerHTML = `<span>🔗 Conectar a <strong>${selectedSkuForLinking}</strong></span>`;
            }
          });
        });
      }
      attachSkuItemClicks();

      if (submitBtn) {
        submitBtn.addEventListener('click', async () => {
          if (!selectedSkuForLinking) return;
          submitBtn.disabled = true;
          submitBtn.innerHTML = `<span class="os-spinner"></span> <span>Vinculando ao estoque...</span>`;

          try {
            const res = await sendLinkSku(info.catalogId, selectedSkuForLinking, info);
            if (res.success && res.product_intel) {
              currentIntelData = res.product_intel;
              renderWidget(info, res.product_intel);
            } else {
              alert('Erro ao vincular: ' + (res.error || 'Falha na requisição'));
              submitBtn.disabled = false;
              submitBtn.innerHTML = `<span>🔗 Tentar Novamente</span>`;
            }
          } catch (err) {
            alert('Erro de conexão com o Offer Search App.');
            submitBtn.disabled = false;
          }
        });
      }
    }
  }

  // ─── 6. Inicialização e Observador de SPA ─────────────────────────
  async function init() {
    const info = extractProductInfo();
    if (!info.catalogId && !info.itemId) {
      return;
    }

    const intel = await fetchProductIntel(info);
    renderWidget(info, intel);
  }

  // Executa na carga inicial
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Observa mudanças de rota em SPAs (Mercado Livre e Amazon)
  let lastUrl = location.href;
  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      setTimeout(init, 800);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });

})();
