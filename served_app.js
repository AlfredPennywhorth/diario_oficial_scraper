let socket;
let allResults = [];
let reconnectInterval = 3000;

function connectWS() {
    console.log("Tentando conectar ao WebSocket...");
    socket = new WebSocket("ws://127.0.0.1:8085/ws/logs");

    socket.onopen = () => {
        console.log("Conectado ao WebSocket");
        updateStatus("Conectado ao servidor.");
        // Verificar atualizações quando conectar
        checkForUpdates();
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            if (data.type === 'log') {
                updateStatus(data.message);
            } else if (data.type === 'result') {
                allResults = data.data || [];
                renderAll(allResults);
            } else if (data.type === 'complete') {
                updateStatus("Raspagem concluída!");
                toggleLoading(false);
            } else if (data.type === 'error') {
                const errorMsg = data.message || "Erro desconhecido";
                updateStatus("Erro: " + errorMsg);
                showErrorState(errorMsg);
                toggleLoading(false);
            }
        } catch (e) {
            console.error("Erro ao processar mensagem WS:", e);
        }
    };

    socket.onclose = () => {
        console.log("WS Desconectado. Tentando reconectar em 3s...");
        updateStatus("Desconectado. Reconectando...");
        setTimeout(connectWS, reconnectInterval);
    };

    socket.onerror = (err) => {
        console.error("Erro no WebSocket:", err);
        socket.close(); // Force close to trigger logic above
    };
}

function renderAll(results) {
    renderGrid(results);
    renderTextView(results);
    updateStats(results);
}

function startSearch() {
    const startRaw = document.getElementById('startDate').value;
    const endRaw = document.getElementById('endDate').value;
    const checkboxes = document.querySelectorAll('input[name="searchTerm"]:checked');
    const terms = Array.from(checkboxes).map(cb => cb.value);

    if (!startRaw || !endRaw) {
        alert("Por favor, preencha as datas.");
        return;
    }

    const startParts = startRaw.split('-');
    const endParts = endRaw.split('-');
    const start = `${startParts[2]}/${startParts[1]}/${startParts[0]}`;
    const end = `${endParts[2]}/${endParts[1]}/${endParts[0]}`;

    toggleLoading(true);
    document.getElementById('resultsGrid').innerHTML = '<div class="empty-state"><p>Pesquisando...</p></div>';

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            action: 'start_search',
            payload: { start_date: start, end_date: end, terms: terms }
        }));
    } else {
        alert("Sem conexão com o servidor. Aguarde a reconexão...");
        toggleLoading(false);
    }
}

function updateStatus(msg) {
    const log = document.getElementById('statusLog');
    if (log) log.innerText = msg;
}

function showErrorState(msg) {
    document.getElementById('resultsGrid').innerHTML = `
        <div class="empty-state" style="color: var(--danger-color, #ff4444)">
            <i class="fa-solid fa-triangle-exclamation"></i>
            <p>Ocorreu um erro durante a raspagem.</p>
            <small>${msg}</small>
        </div>
    `;
}

// Helper to determine type and visual class (Unified Logic)
function determineType(item) {
    const term = item.term || '';
    const summary = item.summary || '';
    const modality = item.modality || '';
    const fullTerm = (term + " " + summary + " " + modality).toUpperCase();

    let tipo = 'OUTRO';

    // Regra 5/6: Se doc_type, type, publication_number ou contract_number indicar Acordo de Cooperação, usar layout específico
    const pubNumStr = item.publication_number || '';
    const contNumStr = item.contract_number || '';
    const isAcordo = (
        item.doc_type === "ACORDO_COOPERACAO" ||
        item.type === "ACORDO_COOPERACAO" ||
        pubNumStr.includes("Acordo de Cooperação") ||
        contNumStr.includes("Acordo de Cooperação") ||
        /Acordo\s+de\s+Coopera/i.test(pubNumStr) ||
        /Acordo\s+de\s+Coopera/i.test(contNumStr)
    );

    if (isAcordo) {
        tipo = 'ACORDO_COOPERACAO';
    } else if (item.doc_type && item.doc_type !== 'OUTRO') {
        tipo = item.doc_type;
    } else {
        // Fallback inference using hierarchy (Synchronized with Backend)
        if (fullTerm.includes('ADITAMENTO') || fullTerm.includes('TERMO ADITIVO') || fullTerm.includes('APOSTILAMENTO')) {
            tipo = 'ADITAMENTO';
        } else if (fullTerm.includes('CONTRATO Nº') || fullTerm.includes('CONTRATO N.º') || fullTerm.includes('FORMALIZAÇÃO DO CONTRATO') || fullTerm.includes('EXTRATO DE CONTRATO')) {
            tipo = 'CONTRATO';
        } else if (/\b(ACORDOS?\ DE\ COOPERA[ÇC][ÃA]O|TERMO\ DE\ COOPERA[ÇC][ÃA]O)\b/.test(fullTerm)) {
            tipo = 'ACORDO_COOPERACAO';
        } else if (/\b(TERMO\ DE\ PARCERIA|CONV[ÊE]NIO|TERMO\ DE\ FOMENTO|TERMO\ DE\ COLABORA[ÇC][ÃA]O)\b/.test(fullTerm)) {
            tipo = 'PARCERIA';
        } else if (fullTerm.includes('ESCLARECIMENTO') || fullTerm.includes('QUESTIONAMENTO') || fullTerm.includes('IMPUGNAÇ') || fullTerm.includes('NOTIFICAÇÃO') || fullTerm.includes('DESPACHO')) {
            tipo = 'DIVERSOS';
        } else if (fullTerm.includes('DISPENSA')) {
            tipo = 'PEDIDO_COMPRA';
        } else if (fullTerm.includes('PREGÃO') || fullTerm.includes('PREGAO') || fullTerm.includes('ABERTURA DE LICITAÇÃO') || fullTerm.includes('AVISO DE LICITAÇÃO') || fullTerm.includes('ATA DE REGISTRO DE PREÇOS') || fullTerm.includes('SISTEMA DE REGISTRO DE PREÇOS')) {
            tipo = 'PREGAO';
        }
    }

    // Map type to visual class
    let visualClass = 'outro';
    let label = term || tipo;
    let icon = 'fa-file';

    if (tipo === 'ADITAMENTO' || tipo === 'APOSTILAMENTO') {
        visualClass = 'aditamento';
        icon = 'fa-file-pen';
        label = item.amendment_number ? `ADITAMENTO ${item.amendment_number}` : 'ADITAMENTO';
    }
    else if (tipo === 'PARCERIA' || tipo === 'ACORDO_COOPERACAO') {
        visualClass = 'parceria';
        icon = 'fa-handshake';
        label = tipo === 'ACORDO_COOPERACAO' ? 'ACORDO COOPERAÇÃO' : 'PARCERIA';
    }
    else if (tipo === 'DOACAO') {
        visualClass = 'doacao';
        icon = 'fa-gift';
        label = 'DOAÇÃO';
    }
    else if (tipo === 'CONTRATO' || tipo === 'EMPENHO') {
        visualClass = 'contrato';
        icon = 'fa-file-signature';
        label = tipo === 'EMPENHO' ? 'EMPENHO' : 'CONTRATO';
    }
    else if (tipo === 'PREGAO') {
        visualClass = 'pregao';
        icon = 'fa-gavel';
        label = 'LICITAÇÃO';
    }
    else if (tipo === 'HOMOLOGACAO') {
        visualClass = 'destaque';
        icon = 'fa-award';
        label = 'HOMOLOGAÇÃO';
    }
    else if (tipo === 'DIVERSOS') {
        visualClass = 'diversos';
        icon = 'fa-paperclip';
        label = 'DIVERSOS';
    }
    else if (tipo === 'PEDIDO_COMPRA') {
        visualClass = 'compra';
        icon = 'fa-cart-shopping';
        label = 'PEDIDO COMPRA';
    }

    return { tipo, visualClass, label, icon };
}

function renderGrid(results) {
    const grid = document.getElementById('resultsGrid');
    if (!results || results.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fa-regular fa-face-frown"></i>
                <p>Nenhum resultado encontrado.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = '';
    results.forEach(item => {
        const { tipo, visualClass, label, icon } = determineType(item);
        const typeClass = `type-${visualClass}`;

        const card = document.createElement('div');
        card.className = `card ${typeClass}`;

        if (tipo === 'ACORDO_COOPERACAO') {
            const normalizedTermo = (item.contract_number && item.contract_number !== '-') 
                ? item.contract_number.replace(/PUBLICACAO\s*/i, '').trim() 
                : "S/N";
            const orgaoCompleto = `${item.contractor || '-'}${item.company_doc && item.company_doc !== '-' ? ', CNPJ nº ' + item.company_doc : ''}`;
            const vigInicio = item.validity_start || '-';
            const vigFim = item.validity_end || '-';

            card.innerHTML = `
                <div class="card-header">
                    <span class="badge ${typeClass}"><i class="fa-solid ${icon}"></i> ${label}</span>
                    <span class="meta-date"><i class="fa-regular fa-calendar"></i> ${item.date}</span>
                </div>
                
                <div class="card-body-acordo" style="margin-top: 1rem; font-size: 0.9rem; line-height: 1.5; text-align: left;">
                    <p style="margin: 4px 0;"><strong>Número do Processo:</strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>
                    <p style="margin: 4px 0;"><strong>Número do Termo:</strong> <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">${normalizedTermo}</a></p>
                    <p style="margin: 4px 0;"><strong>Nome da Organização:</strong> <span class="val">${orgaoCompleto}</span></p>
                    <p style="margin: 4px 0;"><strong>Objeto:</strong> <span class="val">${item.object_text || '-'}</span></p>
                    <p style="margin: 4px 0;"><strong>Data da Assinatura:</strong> <span class="val">${item.data_assinatura || item.validity_start || '-'}</span></p>
                    <p style="margin: 4px 0;"><strong>Data de Publicação:</strong> <span class="val">${item.date}</span></p>
                    <p style="margin: 4px 0;"><strong>Vigência:</strong> <span class="val">${vigInicio} a ${vigFim}</span></p>
                </div>
                
                <div class="card-footer">
                    <a href="${item.link_pdf}" target="_blank" class="link-btn"><i class="fa-solid fa-file-pdf"></i> Ver PDF</a>
                    <a href="${item.link_html}" target="_blank" class="link-btn" style="color:var(--text-dim);font-size:0.8rem;font-weight:400">Ver Web</a>
                </div>
            `;
        } else {
            card.innerHTML = `
                <div class="card-header">
                    <span class="badge ${typeClass}"><i class="fa-solid ${icon}"></i> ${label}</span>
                    <span class="meta-date"><i class="fa-regular fa-calendar"></i> ${item.date}</span>
                </div>
                
                <div class="meta-row" style="margin-top: 1rem; margin-bottom:0.5rem">
                    <span><strong>Processo:</strong> ${item.process_number || '-'}</span>
                </div>
                
                <p class="snippet" title="${item.summary}" style="-webkit-line-clamp: 8; line-clamp: 8;">${item.summary}</p>
                
                <div class="card-footer">
                    <a href="${item.link_pdf}" target="_blank" class="link-btn"><i class="fa-solid fa-file-pdf"></i> Ver PDF</a>
                    <a href="${item.link_html}" target="_blank" class="link-btn" style="color:var(--text-dim);font-size:0.8rem;font-weight:400">Ver Web</a>
                </div>
            `;
        }
        grid.appendChild(card);
    });
}

function toggleLoading(isLoading) {
    const btn = document.getElementById('btnSearch');
    const statusBox = document.getElementById('statusArea');
    const bar = statusBox.querySelector('.loading-bar');

    if (isLoading) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Trabalhando...';
        statusBox.classList.remove('hidden');
        if (bar) bar.style.opacity = '1';
    } else {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Iniciar Raspagem';
        if (bar) bar.style.opacity = '0';
    }
}

// Init
connectWS();

window.addEventListener('DOMContentLoaded', () => {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    const formattedDate = `${yyyy}-${mm}-${dd}`;

    const startInput = document.getElementById('startDate');
    const endInput = document.getElementById('endDate');

    if (startInput) startInput.value = formattedDate;
    if (endInput) endInput.value = formattedDate;

    // Carregar versão atual
    loadCurrentVersion();
});

// View Switching
function switchView(view) {
    const grid = document.getElementById('resultsGrid');
    const text = document.getElementById('resultsText');
    const btnCards = document.getElementById('btnViewCards');
    const btnText = document.getElementById('btnViewText');

    if (view === 'cards') {
        grid.classList.remove('hidden');
        text.classList.add('hidden');
        btnCards.classList.add('active');
        btnText.classList.remove('active');
    } else {
        grid.classList.add('hidden');
        text.classList.remove('hidden');
        btnCards.classList.remove('active');
        btnText.classList.add('active');
    }
    // Scroll to top to ensure user sees the change
    document.querySelector('.content').scrollTop = 0;
}

function updateStats(results) {
    const statsBox = document.getElementById('statsBox');
    const content = document.getElementById('statsContent');

    if (!results || results.length === 0) {
        statsBox.classList.add('hidden');
        return;
    }

    let contratos = 0;
    let pregoes = 0;
    let aditamentos = 0;
    let outros = 0;

    results.forEach(r => {
        const t = ((r.term || '') + (r.summary || '')).toUpperCase();
        if (t.includes('CONTRATO')) contratos++;
        else if (t.includes('PREGÃO') || t.includes('PREGAO')) pregoes++;
        else if (t.includes('ADITAMENTO')) aditamentos++;
        else outros++;
    });

    content.innerHTML = `
        <div class="stat-row"><strong>Contratos:</strong> <span>${contratos}</span></div>
        <div class="stat-row"><strong>Pregões:</strong> <span>${pregoes}</span></div>
        <div class="stat-row"><strong>Aditamentos:</strong> <span>${aditamentos}</span></div>
        <div class="stat-row"><strong>Outros:</strong> <span>${outros}</span></div>
        <hr style="border-color: rgba(255,255,255,0.1); margin: 0.5rem 0;">
        <div class="stat-row" style="font-size: 1rem;"><strong>Total:</strong> <span>${results.length}</span></div>
    `;
    statsBox.classList.remove('hidden');
}


function clearResults() {
    document.getElementById('resultsGrid').innerHTML = `
        <div class="empty-state">
            <i class="fa-regular fa-folder-open"></i>
            <p>Resultados limpos.</p>
        </div>
    `;
    allResults = [];
}

function exportCSV() {
    if (allResults.length === 0) {
        alert("Nada para exportar!");
        return;
    }

    const headers = ["Data", "Termo", "Objeto", "Valor", "Processo", "Contratada", "Link PDF"];
    let csvContent = headers.join(",") + "\n";

    allResults.forEach(row => {
        const line = [
            row.date,
            `"${row.term}"`,
            `"${row.object_text.replace(/"/g, '""')}"`,
            `"${row.value}"`,
            row.process_number,
            `"${row.contractor}"`,
            row.link_pdf
        ];
        csvContent += line.join(",") + "\n";
    });

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "resultados_diario.csv");
    document.body.appendChild(link);
    link.click();
}

function normalizarTermo(termo) {
    if (!termo) return "S/N";
    let t = termo;
    t = t.replace(/PUBLICACAO/gi, "");
    t = t.replace(/nº/gi, "");
    t = t.replace(/n\.º/gi, "");
    t = t.replace(/N°/gi, "");
    t = t.replace(/n°/gi, "");
    t = t.replace(/\s+/g, " ").trim();
    return t || "S/N";
}

function renderTextView(results) {
    const container = document.getElementById('resultsText');

    if (results.length === 0) {
        container.innerHTML = '<p>Sem resultados.</p>';
        return;
    }

    let html = `
        <div class="text-doc-header">
            <i class="fa-solid fa-file-contract" style="font-size: 1.5rem; color: var(--primary);"></i>
            <h2>RESULTADOS - DIÁRIO OFICIAL - MAPFRE FIX 20260520</h2>
        </div>
    `;

    results.forEach(item => {
        const { tipo, visualClass } = determineType(item);
        const modality = item.modality || '';
        const objText = item.object_text || '-';

        const P = (label, value) => `<p><strong>${label}</strong> ${value}</p>`;

        html += `<div class="text-item type-${visualClass}">`;

        const pubNumStr = item.publication_number || '';
        const contNumStr = item.contract_number || '';
        const numContStr = item.num_contrato || '';

        const containsAcordo = (str) => {
            if (!str) return false;
            return str.includes("Acordo de Cooperação") || /Acordo\s+de\s+Coopera/i.test(str);
        };

        const isAcordo = (
            tipo === 'ACORDO_COOPERACAO' ||
            item.doc_type === "ACORDO_COOPERACAO" ||
            item.type === "ACORDO_COOPERACAO" ||
            containsAcordo(pubNumStr) ||
            containsAcordo(contNumStr) ||
            containsAcordo(numContStr)
        );

        // --- LAYOUT ACORDO DE COOPERAÇÃO (Priorizado) ---
        if (isAcordo) {
            const processLink = item.link_html || item.process_url || '#';
            const termLink = item.link_pdf || item.document_url || '#';
            
            const rawTermo = item.contract_number || item.num_contrato || item.publication_number || '';
            const termoNorm = normalizarTermo(rawTermo);
            
            html += `<p><strong>Número do Processo:</strong> <a href="${processLink}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>`;
            html += `<p><strong>Número do Termo:</strong> <a href="${termLink}" target="_blank" style="color:blue;text-decoration:none">${termoNorm}</a></p>`;
            
            const cnpjPart = item.company_doc && item.company_doc !== '-' ? `, CNPJ nº ${item.company_doc}` : '';
            html += `<p><strong>Nome da Organização:</strong> ${item.contractor || '-'}${cnpjPart}</p>`;
            
            html += P("Objeto:", objText);
            html += P("Data da Assinatura:", item.data_assinatura || '-');
            html += P("Data de Publicação:", item.date || '-');
            html += P("Vigência:", `${item.validity_start || '-'} a ${item.validity_end || '-'}`);
        }
        else if (tipo === 'ADITAMENTO' || tipo === 'APOSTILAMENTO') {
            const labelTipo = tipo === 'APOSTILAMENTO' ? 'Apostilamento' : 'Aditamento';

            html += `<p><strong>• Processo SEI: </strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>`;

            const numAdit = item.amendment_number || "S/N";
            const numPai = item.parent_contract || "S/N";
            html += `<p>
                 <strong>${labelTipo} nº </strong> <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">${numAdit}</a> 
                 <strong>ao Contrato nº </strong> ${numPai}
             </p>`;

            html += P("Contratada:", `${item.contractor || '-'} ${item.company_doc && item.company_doc !== '-' ? ', ' + item.company_doc : ''}`);
            html += P("Modalidade de Origem:", modality && modality !== '-' ? modality : "Ver contrato original");

            html += P("Objeto do Aditamento:", objText);
            html += P("Data da Assinatura:", item.validity_start || '-');
            html += P("Data da Publicação:", item.date);

            const vigencia = (item.validity_start && item.validity_end && item.validity_end !== '-') ? `${item.validity_start} a ${item.validity_end}` : 'Ver íntegra';
            html += P("Vigência/Prorrogação:", vigencia);
            html += P("Valor:", item.value || 'Sem efeitos financeiros');
        }

        // --- LAYOUT PARCERIA (Convênios, Fomento) ---
        else if (tipo === 'PARCERIA') {
            html += `<p><strong>• Processo SEI: </strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>`;

            const numInst = item.contract_number || "S/N";
            html += `<p>
                 <strong>Instrumento nº </strong> <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">${numInst}</a>
             </p>`;

            html += P("Participe/OS:", item.contractor || '-');
            html += P("Objeto:", objText);
            html += P("Vigência:", `${item.validity_start || '-'} a ${item.validity_end || '-'}`);
            html += P("Valor:", item.value || '-');
            html += P("Data da Publicação:", item.date);
        }

        // --- LAYOUT DOAÇÃO / COMODATO ---
        else if (tipo === 'DOACAO') {
            html += `<p><strong>• Processo SEI: </strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>`;
            html += `<p><strong>Instrumento: </strong> <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">Termo de Doação/Comodato</a></p>`;

            html += P("Doador/Comodatário:", item.contractor || '-');
            html += P("Objeto:", objText);
            html += P("Encargos:", "Sem ônus para a municipalidade"); // Default assumption unless scraped
            html += P("Data da Publicação:", item.date);
        }

        // --- LAYOUT CONTRATO / EMPENHO ---
        else if (tipo === 'CONTRATO' || tipo === 'EMPENHO') {
            const labelInst = tipo === 'EMPENHO' ? 'Nota de Empenho' : 'Contrato';

            html += `<p><strong>• Processo SEI: </strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.process_number || '-'}</a></p>`;

            const numCont = item.contract_number && item.contract_number !== '-' ? item.contract_number : "S/N";
            html += `<p>
                <strong>${labelInst} nº </strong> <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">${numCont}</a> - ${item.contractor} ${item.company_doc && item.company_doc !== '-' ? ', ' + item.company_doc : ''}
            </p>`;

            html += P("Modalidade/Origem:", modality && modality !== '-' ? modality : "Não informada");

            html += P("Objeto:", objText);
            html += P("Data da Assinatura:", item.validity_start || '-');
            html += P("Data da Publicação:", item.date);
            
            const vigencia = (item.validity_start && item.validity_end && item.validity_end !== '-') ? `${item.validity_start} a ${item.validity_end}` : 'Ver íntegra';
            html += P("Vigência:", vigencia);
            
            html += P("Valor:", item.value || 'Sem efeitos financeiros');
        }

        // --- LAYOUT PREGÃO / LICITAÇÃO / OUTROS ---
        else {
            if (tipo === 'DIVERSOS') {
                html += `<p style="opacity: 0.7; font-size: 0.9em;"><em>[Publicação Diversa - Baixa Prioridade]</em></p>`;
            }

            html += P("Número do Processo:", item.process_number || '-');

            const pubNum = item.contract_number && item.contract_number.length > 2 ? item.contract_number : "S/N";
            const pubLabel = (modality && modality !== '-' ? modality : "PUBLICACAO");
            html += `<p>
                <strong>Número da Publicação: </strong> 
                <a href="${item.link_pdf}" target="_blank" style="color:blue;text-decoration:none">${pubLabel} ${pubNum}</a>
             </p>`;

            html += `<p><strong>Documento: </strong> <a href="${item.link_html}" target="_blank" style="color:blue;text-decoration:none">${item.document_id || '-'}</a></p>`;

            if (tipo !== 'DIVERSOS') {
                html += P("Licitante Vencedor:", item.contractor || 'EM PROCESSO');
                html += P("Modalidade:", modality);
                html += P("Data da Abertura:", item.opening_date || '-');
            }

            html += P("Objeto:", objText);
            html += P("Data de Publicação:", item.date);
        }

        html += `</div>`;
    });

    container.innerHTML = html;
}

// ===== UPDATE SYSTEM =====

async function loadCurrentVersion() {
    try {
        const response = await fetch('/api/version');
        const data = await response.json();
        const versionFooter = document.getElementById('versionFooter');
        if (versionFooter && data.version) {
            versionFooter.innerHTML += ` | API: v${data.version}`;
        }
    } catch (error) {
        console.error('Erro ao carregar versão:', error);
        const versionFooter = document.getElementById('versionFooter');
        if (versionFooter) {
            versionFooter.innerHTML = 'versão desconhecida';
        }
    }
}

async function checkForUpdates() {
    try {
        const response = await fetch('/api/check-update');
        const data = await response.json();

        if (data.available) {
            showUpdateBanner(data);
        }
    } catch (error) {
        console.log('Não foi possível verificar atualizações:', error);
    }
}

function showUpdateBanner(updateInfo) {
    const banner = document.getElementById('updateBanner');
    const message = document.getElementById('updateMessage');
    const link = document.getElementById('updateLink');

    // Montar mensagem
    let msg = `Nova versão ${updateInfo.latest_version} disponível! `;
    if (updateInfo.changelog && updateInfo.changelog.length > 0) {
        msg += `(${updateInfo.changelog[0]})`;
    }

    message.textContent = msg;
    link.href = updateInfo.download_url;

    // Mostrar banner com animação
    banner.classList.remove('hidden');

    // Se é atualização crítica, destacar mais
    if (updateInfo.critical) {
        banner.style.background = 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)';
        message.innerHTML = `<strong>⚠️ ATUALIZAÇÃO CRÍTICA:</strong> ${msg}`;
    }
}

function dismissUpdate() {
    const banner = document.getElementById('updateBanner');
    banner.classList.add('hidden');
}
