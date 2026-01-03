// Global state
let ws;
let lastSeq = 0;
let tradeChartData = {
    labels: [],
    equity: [],
    pnl:  []
};

// Chart instances
let bookChart, equityChart;

// Initialize
document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    connectWS();
});

// WebSocket connection
function connectWS() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    
    ws.onmessage = (e) => {
        const snap = JSON.parse(e.data);
        updateUI(snap);
    };
    
    ws.onclose = () => setTimeout(connectWS, 1000);
}

// Initialize charts
function initCharts() {
    const bookCtx = document.getElementById("bookChart");
    if (bookCtx) {
        bookChart = new Chart(bookCtx, {
            type: "line",
            data: {
                labels: [],
                datasets: [
                    { label: "YES Bid", data: [], borderColor: "#3b82f6", tension: 0.1, fill: false },
                    { label:  "YES Ask", data: [], borderColor:  "#60a5fa", tension: 0.1, fill: false },
                    { label: "NO Bid", data: [], borderColor:  "#ef4444", tension: 0.1, fill: false },
                    { label: "NO Ask", data: [], borderColor: "#f87171", tension: 0.1, fill: false }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio:  false,
                plugins: {
                    legend: { labels: { color: "#cbd5e1" } }
                },
                scales: {
                    x: { ticks: { color: "#cbd5e1" }, grid: { color: "#334155" } },
                    y: { ticks: { color:  "#cbd5e1" }, grid: { color: "#334155" }, min: 0, max: 1 }
                }
            }
        });
    }

    const eqCtx = document.getElementById("equityChart");
    if (eqCtx) {
        equityChart = new Chart(eqCtx, {
            type: "line",
            data: {
                labels: [],
                datasets:  [
                    { label: "Equity", data: [], borderColor:  "#10b981", tension: 0.2, fill: true, backgroundColor: "rgba(16, 185, 129, 0.1)" },
                    { label: "Total PnL", data: [], borderColor: "#f59e0b", tension: 0.2, fill: true, backgroundColor: "rgba(245, 158, 11, 0.1)" }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins:  {
                    legend: { labels: { color: "#cbd5e1" } }
                },
                scales: {
                    x: { ticks: { color:  "#cbd5e1" }, grid: { color: "#334155" } },
                    y: { ticks: { color: "#cbd5e1" }, grid: { color: "#334155" } }
                }
            }
        });
    }
}

// Update UI from snapshot
function updateUI(snap) {
    // Status badge
    const badge = document.getElementById("status-badge");
    const btnStart = document.getElementById("btn-start");
    const btnStop = document.getElementById("btn-stop");
    
    if (snap.running) {
        badge.className = "badge badge-running";
        badge.textContent = "RUNNING";
        btnStart.disabled = true;
        btnStop.disabled = false;
    } else {
        badge.className = "badge badge-stopped";
        badge. textContent = "STOPPED";
        btnStart.disabled = false;
        btnStop.disabled = true;
    }

    // Market info
    document.getElementById("market-slug").textContent = snap.slug || "--";
    document.getElementById("market-tte").textContent = snap. tte !== undefined ? `${snap.tte}s` : "--";

    // Portfolio stats
    const balance = snap.balance || 0;
    const pnl = snap.pnl?. total || 0;
    const winrate = snap.stats?.winrate || 0;
    const betFrac = snap.bet_frac || 0;

    document.getElementById("stat-balance").textContent = `$${balance.toFixed(2)}`;
    const pnlEl = document.getElementById("stat-pnl");
    pnlEl.textContent = `$${pnl.toFixed(2)}`;
    pnlEl.className = pnl >= 0 ? "stat-value pnl" : "stat-value pnl negative";
    document.getElementById("stat-winrate").textContent = `${(winrate * 100).toFixed(1)}%`;
    document.getElementById("stat-bet-frac").textContent = `${(betFrac * 100).toFixed(0)}%`;

    // Live prices
    document.getElementById("price-yes-bid").textContent = fmt(snap.yes_bid);
    document.getElementById("price-yes-ask").textContent = fmt(snap.yes_ask);
    document.getElementById("price-no-bid").textContent = fmt(snap.no_bid);
    document.getElementById("price-no-ask").textContent = fmt(snap.no_ask);

    // Trade stats
    const total = (snap.stats?.wins || 0) + (snap.stats?.losses || 0);
    document.getElementById("stats-total").textContent = total;
    document.getElementById("stats-wins").textContent = snap.stats?.wins || 0;
    document.getElementById("stats-losses").textContent = snap.stats?.losses || 0;

    // Positions table
    renderPositions(snap.positions || []);

    // Orders table
    renderOrders(snap.open_orders || []);

    // Update book chart
    updateBookChart(snap);

    // Update equity chart (only on trade close)
    updateEquityChart(snap);
}

function fmt(x) {
    return typeof x === "number" ? x.toFixed(4) : "--";
}

function renderPositions(positions) {
    const tbody = document.getElementById("positions-table");
    tbody.innerHTML = "";
    
    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="no-data">No positions</td></tr>';
        return;
    }

    positions.forEach(p => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${p.asset_id. slice(0, 8)}...</td>
            <td>${p.shares. toFixed(4)}</td>
            <td>$${p.avg_px.toFixed(4)}</td>
            <td><button class="btn btn-danger btn-sm" onclick="closePos('${p.asset_id}')">Close</button></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderOrders(orders) {
    const tbody = document. getElementById("orders-table");
    tbody.innerHTML = "";
    
    if (orders.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="no-data">No open orders</td></tr>';
        return;
    }

    orders.forEach(o => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${o.side}</td>
            <td>$${o.price.toFixed(4)}</td>
            <td>${o.shares.toFixed(4)}</td>
            <td>${o.age_sec}s</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateBookChart(snap) {
    if (! bookChart) return;

    const now = new Date();
    const label = now.toLocaleTimeString();

    // Keep last 100 points
    if (bookChart.data.labels.length > 100) {
        bookChart.data.labels. shift();
        bookChart.data. datasets. forEach(d => d.data.shift());
    }

    bookChart.data.labels.push(label);
    bookChart.data. datasets[0].data.push(snap. yes_bid || null);
    bookChart.data. datasets[1].data.push(snap.yes_ask || null);
    bookChart.data.datasets[2].data.push(snap.no_bid || null);
    bookChart.data.datasets[3].data.push(snap. no_ask || null);

    bookChart.update("none");
}

function updateEquityChart(snap) {
    if (!equityChart || !snap.trade_seq) return;

    // Update only on trade close (trade_seq changes)
    static let lastTradeSeq = 0;
    if (snap. trade_seq === lastTradeSeq) return;
    lastTradeSeq = snap.trade_seq;

    const label = `T${snap.trade_seq}`;
    const balance = snap.balance || 0;
    const pnl = snap.pnl?.total || 0;

    // Keep last 50 trades
    if (equityChart. data.labels.length > 50) {
        equityChart. data.labels.shift();
        equityChart.data.datasets. forEach(d => d.data. shift());
    }

    equityChart.data.labels.push(label);
    equityChart.data.datasets[0].data.push(balance);
    equityChart.data.datasets[1].data.push(pnl);

    equityChart.update("none");
}

// API calls
async function startBot() {
    await fetch("/api/start", { method: "POST" });
}

async function stopBot() {
    await fetch("/api/stop", { method: "POST" });
}

async function closePos(assetId) {
    await fetch("/api/close", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_id: assetId })
    });
}

async function closeAll() {
    if (confirm("Close ALL positions?")) {
        await fetch("/api/close_all", { method: "POST" });
    }
}
