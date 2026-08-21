document.addEventListener('DOMContentLoaded', async () => {
  const apiUrlInput = document.getElementById('apiUrl');
  const btnSync = document.getElementById('btnSync');
  const btnText = document.getElementById('btnText');
  const mlStatusDot = document.getElementById('statusDot');
  const mlStatusText = document.getElementById('mlStatusText');
  const mlStatusBadge = document.getElementById('mlStatusBadge');
  const cookiesCount = document.getElementById('cookiesCount');
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

    // Deduplica por nome e domínio
    const map = new Map();
    [...cookiesBr, ...cookiesCom, ...cookiesLibre].forEach(c => {
      map.set(`${c.domain}:${c.name}`, c);
    });
    mlCookies = Array.from(map.values());

    const hasAuthCookie = mlCookies.some(c => ['ssid', 'org_client_id', '_d2id', 'c_d2id'].includes(c.name));

    if (mlCookies.length > 0 && hasAuthCookie) {
      mlStatusDot.className = 'status-dot online';
      mlStatusText.textContent = 'Conta ML Conectada';
      mlStatusBadge.className = 'badge active';
      mlStatusBadge.textContent = 'Autenticado';
      cookiesCount.textContent = `${mlCookies.length} cookies de sessão detectados`;
    } else if (mlCookies.length > 0) {
      mlStatusDot.className = 'status-dot online';
      mlStatusText.textContent = 'Cookies Detectados (Visitante)';
      mlStatusBadge.className = 'badge';
      mlStatusBadge.textContent = 'Parcial';
      cookiesCount.textContent = `${mlCookies.length} cookies encontrados (Faça login no ML se necessário)`;
    } else {
      mlStatusDot.className = 'status-dot offline';
      mlStatusText.textContent = 'Nenhum cookie encontrado';
      mlStatusBadge.className = 'badge inactive';
      mlStatusBadge.textContent = 'Desconectado';
      cookiesCount.textContent = 'Abra o mercadolivre.com.br e faça login';
    }
  } catch (err) {
    console.error('Erro ao ler cookies:', err);
    mlStatusText.textContent = 'Erro ao ler cookies';
    cookiesCount.textContent = err.message;
  }

  // 3. Ação do Botão de Sincronização
  btnSync.addEventListener('click', async () => {
    const targetUrl = apiUrlInput.value.trim().replace(/\/+$/, '');
    if (!targetUrl) {
      showFeedback('Por favor, informe a URL da API.', 'error');
      return;
    }

    if (mlCookies.length === 0) {
      showFeedback('Nenhum cookie do Mercado Livre encontrado para sincronizar.', 'error');
      return;
    }

    btnSync.disabled = true;
    btnText.textContent = 'Sincronizando...';
    hideFeedback();

    try {
      // Formata lista limpa de cookies para o backend
      const payloadCookies = mlCookies.map(c => ({
        name: c.name,
        value: c.value,
        domain: c.domain,
        path: c.path || '/',
        secure: c.secure || false,
        httpOnly: c.httpOnly || false,
        sameSite: c.sameSite || 'lax'
      }));

      const endpoint = `${targetUrl}/api/auth/sync-ml-session`;
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify({
          cookies: payloadCookies,
          total_cookies: payloadCookies.length,
          synced_from: 'chrome-extension',
          timestamp: new Date().toISOString()
        })
      });

      const data = await res.json();

      if (res.ok && data.success) {
        const now = new Date().toISOString();
        await chrome.storage.local.set({ lastSync: now, apiUrl: targetUrl });
        lastSyncText.textContent = `Último sync: ${new Date(now).toLocaleTimeString('pt-BR')}`;
        showFeedback(`✅ ${data.message || 'Sessão sincronizada com sucesso!'}`, 'success');
      } else {
        showFeedback(`❌ Erro da API: ${data.error || 'Falha ao sincronizar'}`, 'error');
      }
    } catch (err) {
      console.error('Erro ao enviar cookies:', err);
      showFeedback(`❌ Não foi possível conectar a ${targetUrl}. Verifique se o app está ativo.`, 'error');
    } finally {
      btnSync.disabled = false;
      btnText.textContent = 'Sincronizar Sessão';
    }
  });

  function showFeedback(msg, type) {
    feedback.textContent = msg;
    feedback.className = `feedback ${type}`;
  }

  function hideFeedback() {
    feedback.style.display = 'none';
    feedback.className = 'feedback';
  }
});
