const state = {
    loadedTickers: new Set(),
    activeTicker: null,
    latestPrediction: null,
    engineInterval: null,
    backtestButtons: new Map()  // Store button references by ticker
};

let chartRefreshInterval = null;

const el = {
    tickerInput: document.getElementById("tickerInput"),
    loadStockBtn: document.getElementById("loadStockBtn"),
    loadedTickers: document.getElementById("loadedTickers"),
    chartTitle: document.getElementById("chartTitle"),
    predHigh: document.getElementById("predHigh"),
    predLow: document.getElementById("predLow"),
    currentPrice: document.getElementById("currentPrice"),
    signalBadge: document.getElementById("signalBadge"),
    confidence: document.getElementById("confidence"),
    predictionMeta: document.getElementById("predictionMeta"),
    approveBtn: document.getElementById("approveBtn"),
    rejectBtn: document.getElementById("rejectBtn"),
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
    const budget = portfolioCash * 0.10;
    return Math.max(1, Math.floor(budget / price));
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

            saveTickers();
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
}

function saveTickers() {
    localStorage.setItem('loadedTickers', JSON.stringify([...state.loadedTickers]));
    localStorage.setItem('activeTicker', state.activeTicker || '');
}

function renderChart(data) {
    if (!data || !window.Plotly) return;

    document.getElementById('chartPlaceholder').style.display = 'none';
    el.chartTitle.textContent = `${data.ticker} - Price Chart`;

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

    el.predHigh.textContent = fmtMoney(pred.predicted_high);
    el.predLow.textContent = fmtMoney(pred.predicted_low);
    el.currentPrice.textContent = fmtMoney(pred.current_price);

    el.confidence.textContent = fmtPct(pred.confidence);

    el.predictionMeta.textContent =
        `${pred.ticker} | horizon: ${pred.days_ahead} day(s)`;

    setSignalBadge(pred.signal);
}

async function loadStock(rawTicker) {
    const ticker = (rawTicker || "").trim().toUpperCase();

    if (!ticker) {
        showToast("Please enter a ticker.", 'warning');
        return;
    }

    el.loadStockBtn.disabled = true;
    el.loadStockBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Loading...';

    try {
        const [pred, chart] = await Promise.all([
            apiGet(`/api/predict/${ticker}`),
            apiGet(`/api/chart/${ticker}`)
        ]);

        state.activeTicker = ticker;
        state.loadedTickers.add(ticker);
        saveTickers();

        renderTickerChips();
        renderPrediction(pred);
        renderChart(chart);
        startChartRefresh(ticker);

    } catch (error) {
        console.error(error);
        showToast(`Load stock failed: ${error.message}`, 'error');
    } finally {
        el.loadStockBtn.disabled = false;
        el.loadStockBtn.textContent = 'Load Stock';
    }
}

async function executeTradeFromPrediction() {
    console.log('executeTradeFromPrediction called', state.latestPrediction);

    if (!state.latestPrediction) {
        showToast("No prediction available.", 'info');
        return;
    }

    const p = state.latestPrediction;

    if (!["BUY", "SELL"].includes(p.signal)) {
        showToast(`Signal is ${p.signal} — no trade executed. Wait for a BUY or SELL signal.`, 'info');
        return;
    }

    el.approveBtn.disabled = true;
    el.approveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Executing...';

    try {
        console.log('Executing trade:', {ticker: p.ticker, signal: p.signal, price: p.current_price, shares: calcShares(p.current_price)});

        const trade = await apiPost("/api/trade", {
            ticker: p.ticker,
            signal_type: p.signal,
            price: p.current_price,
            shares: calcShares(p.current_price)
        });

        await refreshPortfolio();

        showToast(trade.message || "Trade executed successfully.", 'success');

    } catch (error) {
        console.error(error);
        showToast(`Trade failed: ${error.message}`, 'error');
    } finally {
        el.approveBtn.disabled = false;
        el.approveBtn.textContent = 'Approve';
    }
}

async function refreshPortfolio() {

    try {

        const data = await apiGet("/api/portfolio");

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

        if ((data.transactions || []).length > 0) {
            document.getElementById('emptyTxRow')?.remove();
        }

        const rows = [...(data.transactions || [])]
            .reverse()
            .slice(0, 20);

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

        if (
            pred.signal === "BUY" ||
            pred.signal === "SELL"
        ) {

            await apiPost("/api/trade", {
                ticker: pred.ticker,
                signal_type: pred.signal,
                price: pred.current_price,
                shares: calcShares(pred.current_price)
            });

            await refreshPortfolio();
            showToast(`Auto-trade executed: ${pred.signal} ${calcShares(pred.current_price)} shares of ${pred.ticker} @ $${pred.current_price}`, 'success');
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

    if (getMode() !== "full") {
        showToast(
            "Switch to Fully Autonomous mode first.",
            'info'
        );
        return;
    }

    state.engineInterval = setInterval(
        autonomousTick,
        30000
    );

    if (el.startEngineBtn) {
        el.startEngineBtn.textContent = "Engine Running ●";
        el.startEngineBtn.style.color = "green";
    }

    autonomousTick();
}

function stopEngine() {

    if (state.engineInterval) {

        clearInterval(state.engineInterval);
        state.engineInterval = null;
    }

    if (el.startEngineBtn) {
        el.startEngineBtn.textContent = "Start Engine";
        el.startEngineBtn.style.color = "";
    }
}

el.loadStockBtn?.addEventListener(
    "click",
    () => loadStock(el.tickerInput.value)
);

el.tickerInput?.addEventListener(
    "keydown",
    (e) => {
        if (e.key === "Enter") {
            loadStock(el.tickerInput.value);
        }
    }
);

el.approveBtn?.addEventListener(
    "click",
    executeTradeFromPrediction
);

el.rejectBtn?.addEventListener(
    "click",
    () => {

        state.latestPrediction = null;

        el.predictionMeta.textContent =
            "Prediction rejected.";

        setSignalBadge("HOLD");
    }
);

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

const savedTickers = localStorage.getItem('loadedTickers');
const savedActive = localStorage.getItem('activeTicker');
if (savedTickers) {
    try {
        const tickers = JSON.parse(savedTickers);
        tickers.forEach((t) => state.loadedTickers.add(t));
        renderTickerChips();
        if (savedActive && state.loadedTickers.has(savedActive)) {
            loadStock(savedActive);
        }
    } catch (e) {
        localStorage.removeItem('loadedTickers');
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

checkDbStatus();


refreshPortfolio();