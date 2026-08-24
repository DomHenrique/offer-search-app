document.addEventListener('DOMContentLoaded', async () => {
  const apiUrlInput = document.getElementById('apiUrl');
  const btnSync = document.getElementById('btnSync');
  const btnText = document.getElementById('btnText');
  
  // Elementos Mercado Livre
  const mlStatusDot = document.getElementById('mlStatusDot');
  const mlStatusText = document.getElementById('mlStatusText');
  const mlStatusBadge = document.getElementById('mlStatusBadge');
  const mlCookiesCount = document.getElementById('mlCookiesCount');

  // Elementos Amazon
  const amazonStatusDot = document.getElementById('amazonStatusDot');
  const amazonStatusText = document.getElementById('amazonStatusText');
  const amazonStatusBadge = document.getElementById('amazonStatusBadge');
  const amazonCookiesCount = document.getElementById('amazonCookiesCount');

  const feedback = document.getElementById('feedback');
  const lastSyncText = document.getElementById('lastSyncText');

  // 1. Carrega configurações salvas do storage
  const storage = await chrome.storage.local.get(['apiUrl', 'lastSync']);
  if (storage.apiUrl) {
    apiUrlInput.value = storage.apiUrl;
  }
  if (storage.lastSync) {
    lastSyncText.textContent = `Último sync: ${new Date(storage.lastSync).toLocaleTimeString('pt-BR')} (${new Date(storage.lastSync).toLocaleDateString('pt-BR')})`;
  }

  // Salva alteração de URL
  apiUrlInput.addEventListener('change', () => {
    let url = apiUrlInput.value.trim().replace(/\/+$/, '');
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://' + url;
    }
    apiUrlInput.value = url;
    chrome.storage.local.set({ apiUrl: url });
  });

  // 2. Busca cookies do Mercado Livre
  let mlCookies = [];
  try {
    const cookiesBr = await chrome.cookies.getAll({ domain: 'mercadolivre.com.br' });
    const cookiesCom = await chrome.cookies.getAll({ domain: 'mercadolivre.com' });
    const cookiesLibre = await chrome.cookies.getAll({ domain: 'mercadolibre.com' });

    const mapML = new Map();
    [...cookiesBr, ...cookiesCom, ...cookiesLibre].forEach(c => {
      mapML.set(`${c.domain}:${c.name}`, c);
    });
    mlCookies = Array.from(mapML.values());

    const hasMLAuth = mlCookies.some(c => ['ssid', 'org_client_id', '_d2id', 'c_d2id'].includes(c.name));

    if (mlCookies.length > 0 && hasMLAuth) {
      mlStatusDot.className = 'status-dot online';
      mlStatusText.textContent = 'Conta ML Conectada';
      mlStatusBadge.className = 'badge active';
      mlStatusBadge.textContent = 'Autenticado';
      mlCookiesCount.textContent = `${mlCookies.length} cookies de sessão detectados`;
    } else if (mlCookies.length > 0) {
      mlStatusDot.className = 'status-dot online';
      mlStatusText.textContent = 'Cookies ML Detectados (Visitante)';
      mlStatusBadge.className = 'badge';
      mlStatusBadge.textContent = 'Parcial';
      mlCookiesCount.textContent = `${mlCookies.length} cookies encontrados`;
    } else {
      mlStatusDot.className = 'status-dot offline';
      mlStatusText.textContent = 'Nenhum cookie ML encontrado';
      mlStatusBadge.className = 'badge inactive';
      mlStatusBadge.textContent = 'Desconectado';
      mlCookiesCount.textContent = 'Abra mercadolivre.com.br e faça login';
    }
  } catch (err) {
    console.error('Erro ao ler cookies ML:', err);
    mlStatusText.textContent = 'Erro ao ler cookies ML';
    mlCookiesCount.textContent = err.message;
  }

  // 3. Busca cookies da Amazon
  let amazonCookies = [];
  try {
    const cookiesAmazonBr = await chrome.cookies.getAll({ domain: 'amazon.com.br' });
    const cookiesAmazonCom = await chrome.cookies.getAll({ domain: 'amazon.com' });

    const mapAmz = new Map();
    [...cookiesAmazonBr, ...cookiesAmazonCom].forEach(c => {
      mapAmz.set(`${c.domain}:${c.name}`, c);
    });
    amazonCookies = Array.from(mapAmz.values());

    const hasAmazonAuth = amazonCookies.some(c => ['at-acbbr', 'sess-at-acbbr', 'ubid-acbbr', 'session-id'].includes(c.name));

    if (amazonCookies.length > 0 && hasAmazonAuth) {
      amazonStatusDot.className = 'status-dot online';
      amazonStatusText.textContent = 'Conta Amazon Conectada';
      amazonStatusBadge.className = 'badge active';
      amazonStatusBadge.textContent = 'Autenticado';
      amazonCookiesCount.textContent = `${amazonCookies.length} cookies de sessão detectados`;
    } else if (amazonCookies.length > 0) {
      amazonStatusDot.className = 'status-dot online';
      amazonStatusText.textContent = 'Cookies Amazon Detectados (Visitante)';
      amazonStatusBadge.className = 'badge';
      amazonStatusBadge.textContent = 'Parcial';
      amazonCookiesCount.textContent = `${amazonCookies.length} cookies encontrados`;
    } else {
      amazonStatusDot.className = 'status-dot offline';
      amazonStatusText.textContent = 'Nenhum cookie Amazon encontrado';
      amazonStatusBadge.className = 'badge inactive';
      amazonStatusBadge.textContent = 'Desconectado';
      amazonCookiesCount.textContent = 'Abra amazon.com.br e faça login';
    }
  } catch (err) {
    console.error('Erro ao ler cookies Amazon:', err);
    amazonStatusText.textContent = 'Erro ao ler cookies Amazon';
    amazonCookiesCount.textContent = err.message;
  }

  // 4. Ação do Botão de Sincronização Unificada
  btnSync.addEventListener('click', async () => {
    const targetUrl = apiUrlInput.value.trim().replace(/\/+$/, '');
    if (!targetUrl) {
      showFeedback('Por favor, informe a URL da API.', 'error');
      return;
    }

    if (mlCookies.length === 0 && amazonCookies.length === 0) {
      showFeedback('Nenhum cookie de marketplace encontrado para sincronizar.', 'error');
      return;
    }

    btnSync.disabled = true;
    btnText.textContent = 'Sincronizando...';
    hideFeedback();

    let successMessages = [];
    let errorMessages = [];

    const formatCookies = (cookies) => cookies.map(c => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path || '/',
      secure: c.secure || false,
      httpOnly: c.httpOnly || false,
      sameSite: c.sameSite || 'lax'
    }));

    // Sincroniza Mercado Livre
    if (mlCookies.length > 0) {
      try {
        const payloadML = formatCookies(mlCookies);
        const resML = await fetch(`${targetUrl}/api/auth/sync-ml-session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({
            cookies: payloadML,
            total_cookies: payloadML.length,
            synced_from: 'chrome-extension',
            timestamp: new Date().toISOString()
          })
        });
        const dataML = await resML.json();
        if (resML.ok && dataML.success) {
          successMessages.push(`Mercado Livre (${payloadML.length} cookies)`);
        } else {
          errorMessages.push(`ML: ${dataML.error || 'Falha'}`);
        }
      } catch (err) {
        errorMessages.push(`ML: ${err.message}`);
      }
    }

    // Sincroniza Amazon
    if (amazonCookies.length > 0) {
      try {
        const payloadAmazon = formatCookies(amazonCookies);
        const resAmz = await fetch(`${targetUrl}/api/auth/sync-amazon-session`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({
            cookies: payloadAmazon,
            total_cookies: payloadAmazon.length,
            synced_from: 'chrome-extension',
            timestamp: new Date().toISOString()
          })
        });
        const dataAmz = await resAmz.json();
        if (resAmz.ok && dataAmz.success) {
          successMessages.push(`Amazon (${payloadAmazon.length} cookies)`);
        } else {
          errorMessages.push(`Amazon: ${dataAmz.error || 'Falha'}`);
        }
      } catch (err) {
        errorMessages.push(`Amazon: ${err.message}`);
      }
    }

    if (successMessages.length > 0) {
      const now = new Date().toISOString();
      await chrome.storage.local.set({ lastSync: now, apiUrl: targetUrl });
      lastSyncText.textContent = `Último sync: ${new Date(now).toLocaleTimeString('pt-BR')}`;
      showFeedback(`✅ Sincronizado: ${successMessages.join(' e ')}!` + (errorMessages.length ? ` (Avisos: ${errorMessages.join(', ')})` : ''), 'success');
    } else {
      showFeedback(`❌ Falha ao sincronizar: ${errorMessages.join(', ')}`, 'error');
    }

    btnSync.disabled = false;
    btnText.textContent = 'Sincronizar Sessões';
  });

  // Handler para conectar API Oficial OAuth
  const btnMeliOAuth = document.getElementById('btnMeliOAuth');
  if (btnMeliOAuth) {
    btnMeliOAuth.addEventListener('click', () => {
      let targetUrl = (apiUrlInput.value.trim() || 'https://offer-search.hnperformancedigital.com.br').replace(/\/+$/, '');
      if (!targetUrl.startsWith('http://') && !targetUrl.startsWith('https://')) {
        targetUrl = 'https://' + targetUrl;
      }
      chrome.tabs.create({ url: `${targetUrl}/settings/meli/connect` });
    });
  }

  function showFeedback(msg, type) {
    feedback.textContent = msg;
    feedback.className = `feedback ${type}`;
  }

  function hideFeedback() {
    feedback.style.display = 'none';
    feedback.className = 'feedback';
  }
});
