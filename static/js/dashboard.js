const state = {
    loadedTickers: new Set(),
    activeTicker: null,
    latestPrediction: null,
    engineInterval: null,
    backtestButtons: new Map(),  // Store button references by ticker
    allPredictions: {}
};

let chartRefreshInterval = null;
let activeChartTicker = null;
let chartDataCache = {};

const el = {
    loadedTickers: document.getElementById("loadedTickers"),
    chartTitle: document.getElementById("chartTitle"),
    predHigh: document.getElementById("predHigh"),
    predLow: document.getElementById("predLow"),
    currentPrice: document.getElementById("currentPrice"),
    signalBadge: document.getElementById("signalBadge"),
    confidence: document.getElementById("confidence"),
    predictionMeta: document.getElementById("predictionMeta"),
    modeSemi: document.getElementById("modeSemi"),
    modeFull: document.getElementById("modeFull"),
    startEngineBtn: document.getElementById("startEngineBtn"),
    stopEngineBtn: document.getElementById("stopEngineBtn"),
    cashBadge: document.getElementById("cashBadge"),
    pnlBadge: document.getElementById("pnlBadge"),
    statCash: document.getElementById("statCash"),
    statTotal: document.getElementById("statTotal"),
    statPnl: document.getElementById("statPnl"),
    statWinRate: document.getElementById("statWinRate"),
    txTableBody: document.getElementById("txTableBody"),
    backtestActions: document.getElementById("backtestActions"),
    backtestResultsCard: document.getElementById("backtestResultsCard")
};

function fmtMoney(v) {
    return `$${Number(v || 0).toFixed(2)}`;
}

function fmtPct(v) {
    return `${Number(v || 0).toFixed(2)}%`;
}

function getMode() {
    return el.modeFull?.checked ? "full" : "semi";
}

function updateEngineButtonVisibility() {
    if (el.modeFull?.checked) {
        if (el.startEngineBtn) {
            el.startEngineBtn.disabled = false;
            el.startEngineBtn.style.opacity = "1";
        }
        if (el.stopEngineBtn) {
            el.stopEngineBtn.disabled = false;
            el.stopEngineBtn.style.opacity = "1";
        }
        return;
    }

    if (el.startEngineBtn) {
        el.startEngineBtn.disabled = true;
        el.startEngineBtn.style.opacity = "0.4";
    }
    if (el.stopEngineBtn) {
        el.stopEngineBtn.disabled = true;
        el.stopEngineBtn.style.opacity = "0.4";
    }
    stopEngine();
}

let portfolioCash = 100000;

function calcShares(price) {
    if (!price || price <= 0) return 1;
    const budget = (portfolioCash || 100000) * 0.10;
    const calculated = Math.floor(budget / price);
    return Math.max(1, calculated);
}

function showToast(message, type = 'info') {
    const colors = { success: '#16a34a', error: '#dc2626', info: '#2563eb', warning: '#d97706' };
    const toast = document.createElement('div');
    toast.style.cssText = `background:#1e293b;color:#f1f5f9;padding:.65rem 1rem;border-radius:8px;border-left:3px solid ${colors[type]||colors.info};font-size:13px;max-width:300px;box-shadow:0 4px 12px rgba(0,0,0,.4);`;
    toast.textContent = message;
    document.getElementById('toastContainer')?.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function setSignalBadge(signal) {
    if (!el.signalBadge) return;

    el.signalBadge.textContent = signal || "-";
    el.signalBadge.className = "badge";

    switch (signal) {
        case "BUY":
            el.signalBadge.classList.add("text-bg-success");
            break;

        case "SELL":
            el.signalBadge.classList.add("text-bg-danger");
            break;

        default:
            el.signalBadge.classList.add("text-bg-secondary");
    }
}

function startChartRefresh(ticker) {
    if (chartRefreshInterval) clearInterval(chartRefreshInterval);
    chartRefreshInterval = setInterval(async () => {
        if (!ticker) return;
        try {
            const chart = await apiGet(`/api/chart/${ticker}`);
            renderChart(chart);
        } catch (e) {
            console.warn('Chart refresh failed:', e);
        }
    }, 300000); // every 5 minutes
}

async function apiGet(url) {
    try {
        const res = await fetch(url);

        if (!res.ok) {
            let errorMessage = `Request failed: ${res.status}`;

            try {
                const errorData = await res.json();
                errorMessage = errorData.error || errorMessage;
            } catch {
                // Ignore JSON parse errors
            }

            throw new Error(errorMessage);
        }

        return await res.json();
    } catch (error) {
        console.error("GET request failed:", error);
        throw error;
    }
}

async function apiPost(url, body = {}) {
    try {
        const res = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(body)
        });

        if (!res.ok) {
            let errorMessage = `Request failed: ${res.status}`;

            try {
                const errorData = await res.json();
                errorMessage = errorData.error || errorMessage;
            } catch {
                // Ignore JSON parse errors
            }

            throw new Error(errorMessage);
        }

        return await res.json();
    } catch (error) {
        console.error("POST request failed:", error);
        throw error;
    }
}


async function loadUserPortfolio() {
    try {
        const me = await apiGet('/api/auth/me');
        console.log('api/auth/me response:', JSON.stringify(me));
        
        if (!me.logged_in) {
            console.log('Not logged in, redirecting to login');
            window.location.href = '/login';
            return;
        }
        
        console.log('Logged in as:', me.username, 'stocks:', me.stocks);
        
        const usernameEl = document.getElementById('usernameDisplay');
        if (usernameEl) usernameEl.textContent = me.username;
        
        if (me.stocks && me.stocks.length > 0) {
            for (const ticker of me.stocks) {
                state.loadedTickers.add(ticker);
            }
            renderTickerChips();
            renderChartTabs();
            
            await loadStock(me.stocks[0]);
            
            const predictionPromises = me.stocks.map(async (ticker) => {
                try {
                    const pred = await apiGet('/api/predict/' + ticker);
                    state.allPredictions[ticker] = pred;
                    renderPrediction(pred);
                } catch(e) {
                    console.warn('Prediction failed for ' + ticker + ':', e.message);
                }
            });
            
            await Promise.all(predictionPromises);
            await refreshPortfolio();
        }
        
    } catch(e) {
        console.error('Failed to load user portfolio:', e);
        window.location.href = '/login';
    }
}

function renderTickerChips() {
    if (!el.loadedTickers || !el.backtestActions) return;

    el.loadedTickers.innerHTML = "";
    el.backtestActions.innerHTML = "";

    state.loadedTickers.forEach((ticker) => {

        const chip = document.createElement("span");
        chip.className = "chip";

        chip.innerHTML = `
            <span class="chip-label" style="cursor:pointer">
                ${ticker}
            </span>

            <button type="button" aria-label="Remove ${ticker}">
                &times;
            </button>
        `;

        const label = chip.querySelector(".chip-label");
        const removeBtn = chip.querySelector("button");

        label?.addEventListener("click", () => {
            loadStock(ticker);
        });

        removeBtn?.addEventListener("click", () => {
            state.loadedTickers.delete(ticker);

            if (state.activeTicker === ticker) {
                state.activeTicker = null;
            }

            renderTickerChips();
        });

        el.loadedTickers.appendChild(chip);

        const btBtn = document.createElement("button");

        btBtn.type = "button";
        btBtn.className = "btn btn-sm btn-outline-info";
        btBtn.textContent = `Run Backtest ${ticker}`;

        // Store button reference for use in runBacktest
        state.backtestButtons.set(ticker, btBtn);

        btBtn.addEventListener("click", () => {
            runBacktest(ticker);
        });

        el.backtestActions.appendChild(btBtn);
    });

    renderChartTabs();
}

function renderChartTabs() {
    const tabsEl = document.getElementById('chartTabs');
    if (!tabsEl) return;
    tabsEl.innerHTML = '';
    state.loadedTickers.forEach(ticker => {
        const tab = document.createElement('button');
        tab.className = 'btn btn-sm ' +
            (ticker === activeChartTicker
                ? 'btn-primary'
                : 'btn-outline-secondary');
        tab.textContent = ticker;
        tab.addEventListener('click', () => switchChartTab(ticker));
        tabsEl.appendChild(tab);
    });
}

async function switchChartTab(ticker) {
    activeChartTicker = ticker;
    const manualTickerEl = document.getElementById('manualTradeTicker');
    if (manualTickerEl) manualTickerEl.textContent = ticker;
    renderChartTabs();
    if (chartDataCache[ticker]) {
        renderChart(chartDataCache[ticker]);
    } else {
        try {
            const chart = await apiGet('/api/chart/' + ticker);
            chartDataCache[ticker] = chart;
            renderChart(chart);
        } catch(e) {
            console.error('Chart load failed:', e);
        }
    }
}

// localStorage persistence removed: tickers are stored per-user in the database

function renderChart(data) {
    if (!data || !window.Plotly) return;

    const chartSubtitle = document.getElementById('chartSubtitle');
    if (chartSubtitle) {
        chartSubtitle.textContent = `Candlestick + SMA + Bollinger Bands`;
    }

    const traces = [
        {
            x: data.dates,
            open: data.open,
            high: data.high,
            low: data.low,
            close: data.close,
            type: "candlestick",
            name: "OHLC"
        },
        {
            x: data.dates,
            y: data.sma_20,
            type: "scatter",
            mode: "lines",
            name: "SMA 20",
            line: {
                color: "#3b82f6",
                width: 1.5
            }
        },
        {
            x: data.dates,
            y: data.sma_50,
            type: "scatter",
            mode: "lines",
            name: "SMA 50",
            line: {
                color: "#f59e0b",
                width: 1.5
            }
        },
        {
            x: data.dates,
            y: data.bb_upper,
            type: "scatter",
            mode: "lines",
            name: "BB Upper",
            line: {
                color: "#6b7280",
                width: 1,
                dash: "dot"
            }
        },
        {
            x: data.dates,
            y: data.bb_lower,
            type: "scatter",
            mode: "lines",
            name: "BB Lower",
            line: {
                color: "#6b7280",
                width: 1,
                dash: "dot"
            }
        }
    ];

    const layout = {
        template: "plotly_dark",
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "#10151f",
        margin: {
            t: 10,
            l: 40,
            r: 20,
            b: 30
        },
        xaxis: {
            rangeslider: {
                visible: false
            }
        },
        yaxis: {
            fixedrange: false
        },
        legend: {
            orientation: "h",
            y: 1.02,
            x: 0
        }
    };

    Plotly.newPlot(
        "chart",
        traces,
        layout,
        {
            responsive: true,
            displaylogo: false
        }
    );
}

function renderPrediction(pred) {
    if (!pred) return;
    state.latestPrediction = pred;
    
    const container = document.getElementById('allPredictionsContainer');
    if (!container) return;
    
    // Remove existing card for this ticker if present
    const existingCard = document.getElementById('pred-card-' + pred.ticker);
    if (existingCard) existingCard.remove();
    
    // Create new prediction card
    const signalColors = {
        'BUY': 'success',
        'SELL': 'danger', 
        'HOLD': 'secondary'
    };
    const color = signalColors[pred.signal] || 'secondary';
    
    const card = document.createElement('div');
    card.id = 'pred-card-' + pred.ticker;
    card.className = 'mb-3 p-3';
    card.style.cssText = 'background:#0f1116;border:1px solid #2a3040;border-radius:8px;';
    card.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-2">
            <strong>${pred.ticker}</strong>
            <span class="badge text-bg-${color}">${pred.signal}</span>
        </div>
        <div class="d-flex justify-content-between mb-1">
            <span class="small-muted">Current Price</span>
            <span>$${Number(pred.current_price).toFixed(2)}</span>
        </div>
        <div class="d-flex justify-content-between mb-1">
            <span class="small-muted">Predicted High</span>
            <span class="text-success">$${Number(pred.predicted_high).toFixed(2)}</span>
        </div>
        <div class="d-flex justify-content-between mb-1">
            <span class="small-muted">Predicted Low</span>
            <span class="text-danger">$${Number(pred.predicted_low).toFixed(2)}</span>
        </div>
        <div class="d-flex justify-content-between mb-2">
            <span class="small-muted">Confidence</span>
            <span>${pred.confidence}%</span>
        </div>
        <div id="pred-actions-${pred.ticker}">
            <div class="d-flex align-items-center gap-2 mb-2">
                <label style="font-size:0.8rem;color:#8a93a5;white-space:nowrap;">
                    Shares:
                </label>
                <input 
                    type="number" 
                    id="shares-input-${pred.ticker}"
                    class="form-control form-control-sm bg-dark text-light border-secondary"
                    min="1" 
                    step="1"
                    style="width:80px;"
                    value="${calcShares(pred.current_price)}"
                />
                <span style="font-size:0.75rem;color:#8a93a5;">
                    (10% = ${calcShares(pred.current_price)})
                </span>
            </div>
            <div class="d-flex gap-2">
                <button 
                    class="btn btn-sm btn-success w-100" 
                    onclick="approveTrade('${pred.ticker}')">
                    Approve
                </button>
                <button 
                    class="btn btn-sm btn-outline-light w-100" 
                    onclick="rejectTrade('${pred.ticker}')">
                    Reject
                </button>
            </div>
        </div>
    `;
    
    // Prepend so newest prediction is at top
    container.prepend(card);
}

async function approveTrade(ticker) {
    const pred = state.allPredictions[ticker];
    if (!pred) return;
    if (!['BUY','SELL'].includes(pred.signal)) {
        showToast('Signal is HOLD — no trade executed', 'info');
        return;
    }
    const sharesInput = document.getElementById('shares-input-' + ticker);
    const shares = sharesInput 
        ? Math.max(1, parseInt(sharesInput.value) || 1)
        : calcShares(pred.current_price);

    console.log('Approve trade debug:', {
        ticker: pred.ticker,
        signal: pred.signal,
        price: pred.current_price,
        shares: shares,
        portfolioCash: portfolioCash
    });
    try {
        const trade = await apiPost('/api/trade', {
            ticker: pred.ticker,
            signal_type: pred.signal,
            price: pred.current_price,
            shares: shares
        });
        showToast(trade.message, trade.success ? 'success' : 'error');
        await refreshPortfolio();
        // Remove the action buttons after trade
        const actions = document.getElementById('pred-actions-' + ticker);
        if (actions) actions.innerHTML = '<span class="small-muted">Trade submitted</span>';
    } catch(e) {
        showToast('Trade failed: ' + e.message, 'error');
    }
}

function rejectTrade(ticker) {
    const card = document.getElementById('pred-card-' + ticker);
    if (card) card.remove();
    if (state.allPredictions) delete state.allPredictions[ticker];
    showToast('Prediction rejected for ' + ticker, 'info');
}

async function loadStock(rawTicker) {
    const ticker = (rawTicker || "").trim().toUpperCase();

    if (!ticker) {
        showToast("Please enter a ticker.", 'warning');
        return;
    }

    try {
        const [pred, chart] = await Promise.all([
            apiGet(`/api/predict/${ticker}`),
            apiGet(`/api/chart/${ticker}`)
        ]);

        state.allPredictions[pred.ticker] = pred;
        state.activeTicker = ticker;
        state.loadedTickers.add(ticker);
        
        renderTickerChips();
        renderPrediction(pred);
        renderChart(chart);
        activeChartTicker = ticker;
        const manualTickerEl = document.getElementById('manualTradeTicker');
        if (manualTickerEl) manualTickerEl.textContent = ticker;
        chartDataCache[ticker] = chart;
        renderChartTabs();
        startChartRefresh(ticker);

    } catch (error) {
        console.error(error);
        showToast(`Load stock failed: ${error.message}`, 'error');
    }
}



async function refreshPortfolio() {

    try {

        const data = await apiGet("/api/portfolio");
        console.log('Portfolio data received:', JSON.stringify(data));

        portfolioCash = Number(data.cash) || 100000;

        el.cashBadge.textContent =
            `Cash: ${fmtMoney(data.cash)}`;

        el.pnlBadge.textContent =
            `P&L: ${fmtMoney(data.pnl)}`;

        el.pnlBadge.className =
            `badge fs-6 ${
                Number(data.pnl) >= 0
                    ? "text-bg-success"
                    : "text-bg-danger"
            }`;

        el.statCash.textContent = fmtMoney(data.cash);
        el.statTotal.textContent = fmtMoney(data.total_value);
        el.statPnl.textContent = fmtMoney(data.pnl);
        el.statWinRate.textContent = fmtPct(data.win_rate);

        el.statPnl.className =
            `stat-value ${
                Number(data.pnl) >= 0
                    ? "text-success"
                    : "text-danger"
            }`;

        el.txTableBody.innerHTML = "";

        const rows = [...(data.transactions || [])];
        console.log('Transactions to render:', rows.length, rows);

        if (rows.length === 0) {
            // Keep or restore empty state row
            if (!document.getElementById('emptyTxRow')) {
                const emptyRow = document.createElement('tr');
                emptyRow.id = 'emptyTxRow';
                emptyRow.innerHTML = '<td colspan="6" style="text-align:center;color:#4b5563;padding:2rem;">No transactions yet</td>';
                el.txTableBody.appendChild(emptyRow);
            }
            return;
        }
        document.getElementById('emptyTxRow')?.remove();

        rows.forEach((tx) => {

            const pnlCell = tx.signal_type === 'SELL'
                ? `<td class="${Number(tx.cash_impact) >= 0 ? 'text-success' : 'text-danger'}">${fmtMoney(tx.cash_impact)}</td>`
                : `<td class="text-muted">—</td>`;

            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>
                    ${new Date(tx.transaction_date).toLocaleString()}
                </td>

                <td>${tx.ticker}</td>

                <td>
                    <span class="badge ${
                        tx.signal_type === "BUY"
                            ? "text-bg-success"
                            : "text-bg-danger"
                    }">
                        ${tx.signal_type}
                    </span>
                </td>

                <td>${fmtMoney(tx.price)}</td>

                <td>${Number(tx.shares).toFixed(2)}</td>

                ${pnlCell}
            `;

            el.txTableBody.appendChild(tr);
        });

    } catch (error) {
        console.error("Portfolio refresh failed:", error);
    }
}

async function autonomousTick() {
    console.log('Autonomous tick - ticker:', state.activeTicker, 'mode:', getMode());

    if (!state.activeTicker) {
        return;
    }

    try {

        const pred = await apiGet(
            `/api/predict/${state.activeTicker}`
        );

        renderPrediction(pred);

        if (pred.signal === "BUY" || pred.signal === "SELL") {
            const shares = calcShares(pred.current_price);
            try {
                const tradeResult = await apiPost('/api/trade', {
                    ticker: pred.ticker,
                    signal_type: pred.signal,
                    price: pred.current_price,
                    shares: shares
                });
                
                console.log('Auto-trade result:', tradeResult);
                
                if (tradeResult.success) {
                    showToast(
                        'Auto-trade: ' + pred.signal + ' ' + shares + 
                        ' shares of ' + pred.ticker + 
                        ' @ $' + pred.current_price, 
                        'success'
                    );
                    await refreshPortfolio();
                } else {
                    showToast(
                        'Auto-trade skipped: ' + tradeResult.message, 
                        'warning'
                    );
                }
            } catch(e) {
                console.error('Auto-trade failed:', e);
                showToast('Auto-trade error: ' + e.message, 'error');
            }
        }

    } catch (error) {
        console.error(
            "Autonomous tick failed:",
            error
        );
    }
}

function renderBacktestResult(res) {

    const deltaVsHold =
        Number(res.total_return) -
        Number(res.buy_hold_return);

    const deltaCls =
        deltaVsHold >= 0
            ? "text-success"
            : "text-danger";

    el.backtestResultsCard.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-2">
            <strong>${res.ticker} Backtest</strong>
            <span class="small-muted">
                ${res.num_trades} trades
            </span>
        </div>

        <div class="row g-2">

            <div class="col-md-4">
                <div class="small-muted">
                    Total Return
                </div>

                <div>
                    ${Number(res.total_return).toFixed(2)}%
                </div>
            </div>

            <div class="col-md-4">
                <div class="small-muted">
                    Sharpe Ratio
                </div>

                <div>
                    ${Number(res.sharpe_ratio).toFixed(2)}
                </div>
            </div>

            <div class="col-md-4">
                <div class="small-muted">
                    Max Drawdown
                </div>

                <div>
                    -${Number(res.max_drawdown).toFixed(2)}%
                </div>
            </div>

            <div class="col-md-4">
                <div class="small-muted">
                    Win Rate
                </div>

                <div>
                    ${Number(res.win_rate).toFixed(2)}%
                </div>
            </div>

            <div class="col-md-4">
                <div class="small-muted">
                    Buy & Hold
                </div>

                <div>
                    ${Number(res.buy_hold_return).toFixed(2)}%
                </div>
            </div>

            <div class="col-md-4">
                <div class="small-muted">
                    vs Buy & Hold
                </div>

                <div class="${deltaCls}">
                    ${deltaVsHold.toFixed(2)}%
                </div>
            </div>

        </div>
    `;
}

async function runBacktest(ticker) {

    const btBtn = state.backtestButtons.get(ticker);
    if (btBtn) {
        btBtn.disabled = true;
        btBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Running...';
    }

    try {

        el.backtestResultsCard.innerHTML = `
            <div class="small-muted">
                Running backtest for ${ticker}...
            </div>
        `;

        const result = await apiGet(
            `/api/backtest/${ticker}`
        );

        renderBacktestResult(result);

    } catch (error) {

        el.backtestResultsCard.innerHTML = `
            <div class="text-danger">
                Backtest failed: ${error.message}
            </div>
        `;
    } finally {
        if (btBtn) {
            btBtn.disabled = false;
            btBtn.textContent = `Run Backtest ${ticker}`;
        }
    }
}

function startEngine() {
    stopEngine();
    if (getMode() !== 'full') {
        showToast('Switch to Fully Autonomous mode first.', 'info');
        return;
    }
    
    state.engineInterval = setInterval(autonomousTick, 30000);
    autonomousTick();
    
    if (el.startEngineBtn) {
        el.startEngineBtn.textContent = 'Engine Running ●';
        el.startEngineBtn.style.color = '#16a34a';
    }
    showToast('Autonomous engine started', 'success');
}

function stopEngine() {
    if (state.engineInterval) {
        clearInterval(state.engineInterval);
        state.engineInterval = null;
    }
    if (el.startEngineBtn) {
        el.startEngineBtn.textContent = 'Start Engine';
        el.startEngineBtn.style.color = '';
    }
}

async function checkDbStatus() {
    try {
        const s = await apiGet('/api/status');
        const badge = document.getElementById('dbStatusBadge');
        if (s.db === 'connected') {
            badge.textContent = `DB ✓ | ${s.transaction_count} trades`;
            badge.className = 'badge text-bg-success fs-6';
        }
    } catch (e) {
        document.getElementById('dbStatusBadge').textContent = 'DB ✗';
        document.getElementById('dbStatusBadge').className = 'badge text-bg-danger fs-6';
    }
}

async function executeManualTrade(signalType) {
    const ticker = activeChartTicker;
    if (!ticker) {
        showToast('No stock selected. Click a chart tab first.', 'info');
        return;
    }
    
    const sharesInput = document.getElementById('manualSharesInput');
    const shares = Math.max(1, parseInt(sharesInput?.value) || 1);
    const statusEl = document.getElementById('manualTradeStatus');
    
    // Get current price from latest prediction or chart data
    let price = 0;
    if (state.allPredictions && state.allPredictions[ticker]) {
        price = state.allPredictions[ticker].current_price;
    }
    
    if (!price || price <= 0) {
        // Fetch current price from indicators endpoint
        try {
            const ind = await apiGet('/api/indicators/' + ticker);
            price = ind.current_price;
        } catch(e) {
            showToast('Could not get current price for ' + ticker, 'error');
            return;
        }
    }
    
    // Disable buttons during request
    const buyBtn = document.getElementById('manualBuyBtn');
    const sellBtn = document.getElementById('manualSellBtn');
    if (buyBtn) buyBtn.disabled = true;
    if (sellBtn) sellBtn.disabled = true;
    if (statusEl) statusEl.textContent = 'Executing...';
    
    try {
        const result = await apiPost('/api/trade', {
            ticker: ticker,
            signal_type: signalType,
            price: price,
            shares: shares
        });
        
        if (result.success) {
            if (statusEl) {
                statusEl.textContent = 
                    signalType + ' ' + shares + ' shares @ $' + 
                    Number(price).toFixed(2) + ' executed';
                statusEl.style.color = 
                    signalType === 'BUY' ? '#16a34a' : '#dc2626';
            }
            showToast(
                signalType + ' ' + shares + ' ' + ticker + 
                ' @ $' + Number(price).toFixed(2), 
                'success'
            );
            await refreshPortfolio();
        } else {
            if (statusEl) {
                statusEl.textContent = result.message;
                statusEl.style.color = '#dc2626';
            }
            showToast(result.message, 'error');
        }
    } catch(e) {
        showToast('Trade failed: ' + e.message, 'error');
        if (statusEl) statusEl.textContent = 'Trade failed';
    } finally {
        if (buyBtn) buyBtn.disabled = false;
        if (sellBtn) sellBtn.disabled = false;
    }
}

document.addEventListener('DOMContentLoaded', () => {

    el.startEngineBtn?.addEventListener(
        "click",
        startEngine
    );

    el.modeSemi?.addEventListener("change", updateEngineButtonVisibility);
    el.modeFull?.addEventListener("change", updateEngineButtonVisibility);

    updateEngineButtonVisibility();

    el.stopEngineBtn?.addEventListener(
        "click",
        stopEngine
    );

    document.getElementById('refreshChartBtn')?.addEventListener('click', async () => {
        if (!state.activeTicker) return;
        try {
            const chart = await apiGet(`/api/chart/${state.activeTicker}`);
            renderChart(chart);
            showToast('Chart refreshed', 'info');
        } catch (error) {
            console.error('Manual chart refresh failed:', error);
            showToast('Chart refresh failed', 'error');
        }
    });

    // Wire up logout and edit-portfolio buttons
    document.getElementById('logoutBtn')?.addEventListener('click', async () => {
        await apiPost('/api/auth/logout', {});
        window.location.href = '/login';
    });

    document.getElementById('editPortfolioBtn')?.addEventListener('click', () => {
        window.location.href = '/signup';
    });

    document.getElementById('manualBuyBtn')?.addEventListener(
        'click', () => executeManualTrade('BUY')
    );
    document.getElementById('manualSellBtn')?.addEventListener(
        'click', () => executeManualTrade('SELL')
    );

    checkDbStatus();
    loadUserPortfolio();
});