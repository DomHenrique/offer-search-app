/**
 * static/js/scanner.js
 * Lógica do Scanner Inteligente de Produtos (ML, Amazon, Fornecedores)
 * Suporta os papéis de Loja Própria, Fornecedor e Concorrente,
 * com auditoria de lacunas, análise de margem e matching com o estoque.
 */

let currentExtractedData = null;
let currentScanRole = 'supplier';
let selectedCandidateSku = null;
window.scannerTargetSku = null;

document.addEventListener('DOMContentLoaded', () => {
    initScannerRoleSelection();
    initScannerActions();
});

function setScannerRole(role) {
    currentScanRole = role || 'supplier';
    const roleCards = document.querySelectorAll('.scanner-role-card');
    roleCards.forEach(card => {
        const radio = card.querySelector('input[type="radio"]');
        if (radio && radio.value === currentScanRole) {
            card.classList.add('active-role');
            radio.checked = true;
        } else {
            card.classList.remove('active-role');
            if (radio) radio.checked = false;
        }
    });
}

window.openProductScannerModal = function(options = {}) {
    resetScannerToInput();

    // 1. Configura papel de anúncio
    if (options.role) {
        setScannerRole(options.role);
    } else {
        setScannerRole('supplier');
    }

    // 2. Configura SKU alvo pré-selecionado
    window.scannerTargetSku = options.sku ? options.sku.trim() : null;
    const banner = document.getElementById('scannerTargetSkuBanner');
    const badge = document.getElementById('scannerTargetSkuCode');
    if (banner && badge) {
        if (window.scannerTargetSku) {
            badge.textContent = window.scannerTargetSku;
            banner.classList.remove('d-none');
        } else {
            banner.classList.add('d-none');
        }
    }

    // 3. Preenche URL se fornecida
    const inputUrl = document.getElementById('scannerInputUrl');
    if (inputUrl) {
        inputUrl.value = options.url || '';
    }

    // 4. Abre o modal
    const modalEl = document.getElementById('globalProductScannerModal');
    if (modalEl) {
        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();
        if (!options.url && inputUrl) {
            setTimeout(() => inputUrl.focus(), 350);
        }
    }

    // 5. Se já foi fornecida uma URL, dispara extração automática
    if (options.url) {
        handleExtractAndMatch();
    }
};

function initScannerRoleSelection() {
    const roleCards = document.querySelectorAll('.scanner-role-card');
    roleCards.forEach(card => {
        card.addEventListener('click', () => {
            roleCards.forEach(c => c.classList.remove('active-role'));
            card.classList.add('active-role');
            const radio = card.querySelector('input[type="radio"]');
            if (radio) {
                radio.checked = true;
                currentScanRole = radio.value;
            }
        });
    });

    const btnPaste = document.getElementById('btnScannerPaste');
    if (btnPaste) {
        btnPaste.addEventListener('click', async () => {
            try {
                const text = await navigator.clipboard.readText();
                const input = document.getElementById('scannerInputUrl');
                if (input && text) {
                    input.value = text.trim();
                    input.focus();
                }
            } catch (err) {
                console.warn('Não foi possível acessar a área de transferência:', err);
            }
        });
    }
}

function initScannerActions() {
    const btnExtract = document.getElementById('btnScannerExtract');
    if (btnExtract) {
        btnExtract.addEventListener('click', handleExtractAndMatch);
    }

    const btnBack = document.getElementById('btnScannerBack');
    if (btnBack) {
        btnBack.addEventListener('click', resetScannerToInput);
    }

    const btnConfirm = document.getElementById('btnScannerConfirmLink');
    if (btnConfirm) {
        btnConfirm.addEventListener('click', handleConfirmLink);
    }

    const btnCreateSku = document.getElementById('btnCreateNewSkuAndLink');
    if (btnCreateSku) {
        btnCreateSku.addEventListener('click', handleCreateSkuFromListing);
    }

    const btnQuickFill = document.getElementById('btnScannerQuickFill');
    if (btnQuickFill) {
        btnQuickFill.addEventListener('click', handleQuickFillAttributes);
    }

    // Atalho: tecla Enter no input aciona a extração
    const inputUrl = document.getElementById('scannerInputUrl');
    if (inputUrl) {
        inputUrl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleExtractAndMatch();
            }
        });
    }

    // Recálculo dinâmico de margem quando o usuário edita o preço
    const editPriceInput = document.getElementById('scannerEditPrice');
    if (editPriceInput) {
        editPriceInput.addEventListener('input', recalculateCompetitorMargin);
    }
}

function recalculateCompetitorMargin() {
    if (currentScanRole !== 'competitor') return;
    const compPanel = document.getElementById('scannerCompetitorPanel');
    if (!compPanel || compPanel.classList.contains('d-none')) return;

    const editPrice = document.getElementById('scannerEditPrice');
    const compPrice = editPrice ? (parseFloat(editPrice.value) || 0.0) : 0.0;
    const cost = (window.currentSelectedCandidateCost !== undefined) ? window.currentSelectedCandidateCost : 0.0;

    const fee = Math.round(compPrice * 0.16 * 100) / 100;
    const netProfit = Math.round((compPrice - fee - cost) * 100) / 100;
    const marginPct = compPrice > 0 ? ((netProfit / compPrice) * 100) : 0.0;
    const isDangerous = (netProfit < 0 || marginPct < 8.0);

    const priceVal = document.getElementById('compPriceVal');
    const feeVal = document.getElementById('compFeeVal');
    const costVal = document.getElementById('compCostVal');
    const mVal = document.getElementById('compMarginVal');

    if (priceVal) priceVal.textContent = `R$ ${compPrice.toFixed(2)}`;
    if (feeVal) feeVal.textContent = `R$ ${fee.toFixed(2)}`;
    if (costVal) costVal.textContent = `R$ ${cost.toFixed(2)}`;
    if (mVal) {
        mVal.textContent = `${marginPct.toFixed(1)}% (R$ ${netProfit.toFixed(2)})`;
        mVal.className = isDangerous ? 'text-danger fw-bold' : 'text-success fw-bold';
    }
}

async function handleExtractAndMatch() {
    const inputUrl = document.getElementById('scannerInputUrl');
    const alertErr = document.getElementById('scannerAlertError');
    const loadingState = document.getElementById('scannerLoadingState');
    const inputSection = document.getElementById('scannerInputSection');
    const resultSection = document.getElementById('scannerResultSection');
    const btnBack = document.getElementById('btnScannerBack');
    const btnConfirm = document.getElementById('btnScannerConfirmLink');

    const urlOrId = inputUrl ? inputUrl.value.trim() : '';
    if (!urlOrId) {
        if (alertErr) {
            alertErr.textContent = 'Por favor, informe a URL ou identificador do produto.';
            alertErr.classList.remove('d-none');
        }
        return;
    }

    if (alertErr) alertErr.classList.add('d-none');
    if (inputSection) inputSection.classList.add('d-none');
    if (resultSection) resultSection.classList.add('d-none');
    if (loadingState) loadingState.classList.remove('d-none');

    try {
        const response = await fetch('/inventory/api/scanner/extract-and-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url_or_id: urlOrId,
                role: currentScanRole,
                sku_hint: window.scannerTargetSku || ''
            })
        });

        const data = await response.json();
        if (data.success) {
            currentExtractedData = data.extracted_data;
            renderScannerResults(data);
            if (loadingState) loadingState.classList.add('d-none');
            if (resultSection) resultSection.classList.remove('d-none');
            if (btnBack) btnBack.style.display = 'inline-block';
            if (btnConfirm) btnConfirm.style.display = 'inline-block';
        } else {
            throw new Error(data.error || 'Falha ao extrair produto.');
        }
    } catch (err) {
        if (loadingState) loadingState.classList.add('d-none');
        if (inputSection) inputSection.classList.remove('d-none');
        if (alertErr) {
            alertErr.textContent = err.message || 'Erro de comunicação ao extrair anúncio.';
            alertErr.classList.remove('d-none');
        }
    }
}

function renderScannerResults(data) {
    const ext = data.extracted_data || {};
    const role = data.role || currentScanRole;
    const candidates = data.candidates || [];
    const topCandidate = data.top_candidate;
    const audit = data.audit;
    const compAnalysis = data.competitor_analysis;

    // 1. Preenche Coluna Esquerda (Dados Extraídos)
    const imgEl = document.getElementById('scannerExtractedImg');
    if (imgEl) imgEl.src = ext.image_url || '/static/img/no-image.png';

    const editTitle = document.getElementById('scannerEditTitle');
    if (editTitle) editTitle.value = ext.title || '';

    const editPrice = document.getElementById('scannerEditPrice');
    if (editPrice) editPrice.value = (ext.price || 0.0).toFixed(2);

    const editGtin = document.getElementById('scannerEditGtin');
    if (editGtin) editGtin.value = ext.gtin || '';

    const listIdEl = document.getElementById('scannerExtractedListingId');
    if (listIdEl) listIdEl.textContent = ext.listing_id || 'ID N/D';

    const sellerEl = document.getElementById('scannerExtractedSeller');
    if (sellerEl) sellerEl.textContent = ext.seller || ext.marketplace || 'Vendedor';

    const urlLink = document.getElementById('scannerExtractedUrlLink');
    if (urlLink) urlLink.href = ext.listing_url || '#';

    const marketBadge = document.getElementById('scannerExtractedMarketplaceBadge');
    if (marketBadge) {
        marketBadge.textContent = ext.marketplace || 'Marketplace';
        marketBadge.className = 'badge ' + (ext.marketplace === 'MercadoLivre' ? 'bg-warning text-dark' : (ext.marketplace === 'Amazon' ? 'bg-dark' : 'bg-primary'));
    }

    // Atributos Chips
    const attrsContainer = document.getElementById('scannerExtractedAttributesContainer');
    if (attrsContainer) {
        attrsContainer.innerHTML = '';
        const rawAttrs = ext.raw_attributes || {};
        const entries = Object.entries(rawAttrs);
        if (entries.length === 0) {
            attrsContainer.innerHTML = '<span class="text-muted small">Nenhum atributo adicional detectado.</span>';
        } else {
            entries.slice(0, 15).forEach(([k, v]) => {
                const chip = document.createElement('span');
                chip.className = 'badge bg-light text-dark border';
                chip.style.fontSize = '0.75rem';
                chip.innerHTML = `<strong>${k}:</strong> ${v}`;
                attrsContainer.appendChild(chip);
            });
        }
    }

    // 2. Preenche Coluna Direita (Dinâmica por Papel)
    const auditPanel = document.getElementById('scannerAuditOwnStorePanel');
    const compPanel = document.getElementById('scannerCompetitorPanel');
    const rightColBadge = document.getElementById('scannerRightColumnBadge');

    if (auditPanel) auditPanel.classList.add('d-none');
    if (compPanel) compPanel.classList.add('d-none');

    // Configura painel de Loja Própria
    if (role === 'own_store') {
        if (rightColBadge) {
            rightColBadge.textContent = 'Auditoria do Anúncio';
            rightColBadge.className = 'badge bg-indigo text-white';
            rightColBadge.style.background = '#6d28d9';
        }
        if (auditPanel && audit) {
            auditPanel.classList.remove('d-none');
            const scoreBadge = document.getElementById('scannerAuditScoreBadge');
            const pBar = document.getElementById('scannerAuditProgressBar');
            const summaryText = document.getElementById('scannerAuditSummaryText');
            const issuesList = document.getElementById('scannerAuditIssuesList');

            const score = audit.completeness_score || 0;
            if (scoreBadge) {
                scoreBadge.textContent = `Saúde: ${score}% (${audit.status_label || ''})`;
                scoreBadge.style.backgroundColor = audit.status_color || '#3b82f6';
                scoreBadge.className = 'badge px-2 py-1 fs-6 text-white';
            }
            if (pBar) {
                pBar.style.width = `${score}%`;
                pBar.style.backgroundColor = audit.status_color || '#3b82f6';
            }
            if (summaryText) {
                summaryText.textContent = audit.issues.length === 0
                    ? 'Parabéns! O anúncio possui código EAN e todos os atributos essenciais preenchidos.'
                    : `Identificamos ${audit.issues.length} pontos de atenção para otimizar suas vendas.`;
            }

            if (issuesList) {
                issuesList.innerHTML = '';
                if (audit.issues.length === 0) {
                    issuesList.innerHTML = '<div class="p-2 text-success small fw-semibold"><i class="fas fa-check-circle me-1"></i> Ficha técnica e preço 100% alinhados!</div>';
                } else {
                    audit.issues.forEach(iss => {
                        const card = document.createElement('div');
                        card.className = 'p-2 rounded-2 border bg-white';
                        card.style.fontSize = '0.78rem';
                        card.innerHTML = `
                            <div class="d-flex justify-content-between align-items-center mb-1">
                                <strong class="text-dark">${iss.title}</strong>
                                <span class="badge ${iss.severity === 'CRITICAL' ? 'bg-danger' : (iss.severity === 'HIGH' ? 'bg-warning text-dark' : 'bg-secondary')}">${iss.badge}</span>
                            </div>
                            <div class="text-muted">${iss.impact}</div>
                        `;
                        issuesList.appendChild(card);
                    });
                }
            }

            // Quick Fill
            const qFillBox = document.getElementById('scannerQuickFillBox');
            if (qFillBox) {
                if (audit.can_quick_fill) {
                    qFillBox.classList.remove('d-none');
                } else {
                    qFillBox.classList.add('d-none');
                }
            }
        }
    } else if (role === 'competitor') {
        if (rightColBadge) {
            rightColBadge.textContent = 'Espionagem & Margem';
            rightColBadge.className = 'badge bg-amber text-dark';
            rightColBadge.style.background = '#f59e0b';
        }
        if (compPanel && compAnalysis) {
            compPanel.classList.remove('d-none');
            document.getElementById('compPriceVal').textContent = `R$ ${compAnalysis.competitor_price.toFixed(2)}`;
            document.getElementById('compCostVal').textContent = `R$ ${compAnalysis.inventory_cost.toFixed(2)}`;
            document.getElementById('compFeeVal').textContent = `R$ ${compAnalysis.marketplace_fee.toFixed(2)}`;
            const mVal = document.getElementById('compMarginVal');
            mVal.textContent = `${compAnalysis.margin_pct.toFixed(1)}% (R$ ${compAnalysis.net_profit.toFixed(2)})`;
            mVal.className = compAnalysis.is_dangerous ? 'text-danger fw-bold' : 'text-success fw-bold';
        }
    } else {
        if (rightColBadge) {
            rightColBadge.textContent = 'Base Canônica';
            rightColBadge.className = 'badge bg-success';
        }
    }

    // 3. Renderiza a Lista de Candidatos do Inventário
    renderCandidatesList(candidates, topCandidate);
}

function renderCandidatesList(candidates, topCandidate) {
    const container = document.getElementById('scannerCandidatesList');
    if (!container) return;

    container.innerHTML = '';
    selectedCandidateSku = null;

    if (!candidates || candidates.length === 0) {
        container.innerHTML = `
            <div class="p-3 text-center text-muted border rounded-2 bg-light small">
                Nenhum produto correspondente identificado automaticamente no estoque.
                Utilize o botão abaixo para criar um novo SKU.
            </div>
        `;
        return;
    }

    candidates.forEach((cand, idx) => {
        const isPreselected = (topCandidate && topCandidate.sku === cand.sku) || idx === 0;
        if (isPreselected && !selectedCandidateSku) {
            selectedCandidateSku = cand.sku;
            window.currentSelectedCandidateCost = cand.preco_custo || 0.0;
        }

        const itemDiv = document.createElement('div');
        itemDiv.className = `candidate-sku-item p-2 rounded-2 cursor-pointer ${isPreselected ? 'selected-sku' : ''}`;
        itemDiv.setAttribute('data-sku', cand.sku);

        const imgHtml = cand.image_url ? `<img src="${cand.image_url}" class="rounded border me-1" style="width: 32px; height: 32px; object-fit: contain;">` : '';

        itemDiv.innerHTML = `
            <div class="d-flex align-items-center justify-content-between">
                <div class="d-flex align-items-center gap-2">
                    <input type="radio" name="candidateSkuRadio" value="${cand.sku}" class="form-check-input mt-0" ${isPreselected ? 'checked' : ''}>
                    ${imgHtml}
                    <div>
                        <div class="d-flex align-items-center gap-1">
                            <strong class="text-dark" style="font-size: 0.88rem;">${cand.sku}</strong>
                            <span class="badge ${cand.match_score >= 90 ? 'bg-success' : (cand.match_score >= 60 ? 'bg-primary' : 'bg-secondary')}" style="font-size: 0.7rem;">
                                ${cand.match_score}% Match
                            </span>
                        </div>
                        <div class="text-muted text-truncate" style="font-size: 0.78rem; max-width: 320px;">
                            ${cand.descricao}
                        </div>
                    </div>
                </div>
                <div class="text-end" style="font-size: 0.78rem;">
                    <div class="text-dark fw-semibold">${cand.quantidade_total} em estoque</div>
                    <div class="text-muted">Custo: R$ ${cand.preco_custo.toFixed(2)}</div>
                </div>
            </div>
            ${cand.match_badge ? `<div class="mt-1 small" style="font-size: 0.72rem; color: #475569;"><i class="fas fa-check-circle text-primary me-1"></i>${cand.match_badge}</div>` : ''}
        `;

        itemDiv.addEventListener('click', () => {
            document.querySelectorAll('.candidate-sku-item').forEach(el => el.classList.remove('selected-sku'));
            itemDiv.classList.add('selected-sku');
            const rad = itemDiv.querySelector('input[type="radio"]');
            if (rad) rad.checked = true;
            selectedCandidateSku = cand.sku;
            window.currentSelectedCandidateCost = cand.preco_custo || 0.0;
            recalculateCompetitorMargin();
        });

        container.appendChild(itemDiv);
    });
}

async function handleConfirmLink() {
    if (!selectedCandidateSku) {
        alert('Por favor, selecione um SKU do inventário para vincular este produto.');
        return;
    }
    if (!currentExtractedData) {
        alert('Dados do produto não disponíveis.');
        return;
    }

    const editTitle = document.getElementById('scannerEditTitle');
    const editPrice = document.getElementById('scannerEditPrice');
    const editGtin = document.getElementById('scannerEditGtin');
    const btn = document.getElementById('btnScannerConfirmLink');

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Salvando...';
    }

    try {
        const response = await fetch('/inventory/api/scanner/confirm-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sku: selectedCandidateSku,
                extracted_data: currentExtractedData,
                role: currentScanRole,
                override_title: editTitle ? editTitle.value.trim() : '',
                override_price: editPrice ? parseFloat(editPrice.value) : null,
                override_gtin: editGtin ? editGtin.value.trim() : ''
            })
        });

        const data = await response.json();
        if (data.success) {
            const modalEl = document.getElementById('globalProductScannerModal');
            if (modalEl) {
                const modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();
            }
            alert(`✅ ${data.message}`);
            // Se estiver na tela de estoque ou detalhes, recarrega
            if (window.location.pathname.includes('/inventory')) {
                setTimeout(() => window.location.reload(), 600);
            }
        } else {
            alert(`❌ Erro: ${data.error || 'Não foi possível confirmar o vínculo.'}`);
        }
    } catch (err) {
        alert('Erro de comunicação ao salvar vínculo.');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-check-circle me-1"></i> Confirmar Vínculo com SKU';
        }
    }
}

async function handleCreateSkuFromListing() {
    const skuInput = document.getElementById('newSkuCodeInput');
    const costInput = document.getElementById('newSkuCostInput');
    const editTitle = document.getElementById('scannerEditTitle');
    const editPrice = document.getElementById('scannerEditPrice');

    const sku = skuInput ? skuInput.value.trim().toUpperCase() : '';
    const cost = costInput ? parseFloat(costInput.value) || 0.0 : 0.0;
    const title = editTitle ? editTitle.value.trim() : (currentExtractedData ? currentExtractedData.title : '');
    const price = editPrice ? parseFloat(editPrice.value) || 0.0 : (currentExtractedData ? currentExtractedData.price : 0.0);

    if (!sku) {
        alert('Informe o código do novo SKU (Ex: ECO-NOVO-PRODUTO).');
        return;
    }

    try {
        const response = await fetch('/inventory/api/scanner/create-sku-from-listing', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sku: sku,
                descricao: title,
                preco_custo: cost,
                preco_revenda: price,
                extracted_data: currentExtractedData,
                role: currentScanRole
            })
        });

        const data = await response.json();
        if (data.success) {
            alert(`✅ ${data.message}`);
            const modalEl = document.getElementById('globalProductScannerModal');
            if (modalEl) {
                const modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();
            }
            if (window.location.pathname.includes('/inventory')) {
                setTimeout(() => window.location.reload(), 600);
            }
        } else {
            alert(`❌ Erro: ${data.error || 'Não foi possível cadastrar novo SKU.'}`);
        }
    } catch (err) {
        alert('Erro ao criar novo SKU no estoque.');
    }
}

async function handleQuickFillAttributes() {
    if (!selectedCandidateSku) return;
    try {
        const response = await fetch('/inventory/api/scanner/quick-fill-attributes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sku: selectedCandidateSku,
                attributes: currentExtractedData ? currentExtractedData.raw_attributes : {}
            })
        });
        const data = await response.json();
        if (data.success) {
            alert('⚡ Atributos copiados com sucesso do fornecedor!');
            const qBox = document.getElementById('scannerQuickFillBox');
            if (qBox) qBox.innerHTML = '<span class="text-success small fw-bold"><i class="fas fa-check-double me-1"></i> Ficha técnica sincronizada!</span>';
        }
    } catch (err) {
        alert('Erro ao sincronizar atributos.');
    }
}

function resetScannerToInput() {
    const inputSection = document.getElementById('scannerInputSection');
    const resultSection = document.getElementById('scannerResultSection');
    const loadingState = document.getElementById('scannerLoadingState');
    const btnBack = document.getElementById('btnScannerBack');
    const btnConfirm = document.getElementById('btnScannerConfirmLink');
    const alertErr = document.getElementById('scannerAlertError');

    if (alertErr) {
        alertErr.classList.add('d-none');
        alertErr.textContent = '';
    }
    if (resultSection) resultSection.classList.add('d-none');
    if (loadingState) loadingState.classList.add('d-none');
    if (inputSection) inputSection.classList.remove('d-none');
    if (btnBack) btnBack.style.display = 'none';
    if (btnConfirm) btnConfirm.style.display = 'none';
}
