# ui_server.py
from __future__ import annotations

import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from bot.runtime import BotRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ui")

app = FastAPI()
runtime = BotRuntime(cfg_path="config.yaml", log=logging.getLogger("polyscalp"))

HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Polyscalp UI</title>

  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

  <style>
    :root{
      --bg0:#07090b; --bg1:#0b0f14;
      --glass: rgba(255,255,255,.06);
      --stroke: rgba(255,255,255,.12);
      --muted: rgba(255,255,255,.65);
      --text: rgba(255,255,255,.92);
      --shadow: 0 20px 80px rgba(0,0,0,.45);
      --radius2: 26px;
    }
    *{ box-sizing:border-box; }
    html,body{ height:100%; }
    body{
      margin:0;
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background:
        radial-gradient(1200px 600px at 12% 18%, rgba(69,180,140,.30), transparent 55%),
        radial-gradient(1000px 700px at 88% 22%, rgba(120,130,250,.22), transparent 55%),
        radial-gradient(900px 900px at 55% 92%, rgba(255,180,90,.12), transparent 50%),
        linear-gradient(180deg, var(--bg0), var(--bg1));
      overflow-x:hidden;
    }
    body::before{
      content:"";
      position:fixed; inset:0; pointer-events:none; opacity:.22;
      background-image:
        linear-gradient(rgba(255,255,255,.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px);
      background-size: 120px 120px;
      mask-image: radial-gradient(closest-side at 55% 45%, rgba(0,0,0,.95), transparent 82%);
    }
    body::after{
      content:"";
      position:fixed; inset:-120px; pointer-events:none;
      background: radial-gradient(900px 700px at 50% 30%, transparent 40%, rgba(0,0,0,.45) 78%);
    }

    .wrap{ max-width: 1300px; margin: 0 auto; padding: 24px 22px 40px; position:relative; z-index:1; }
    .topbar{
      display:flex; align-items:center; justify-content:space-between; gap: 16px;
      padding: 10px 14px; border-radius: 999px;
      background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08);
      backdrop-filter: blur(10px); box-shadow: 0 8px 40px rgba(0,0,0,.25);
    }
    .brand{ display:flex; align-items:center; gap:10px; font-weight:650; letter-spacing:.2px; }
    .dot{ width:10px; height:10px; border-radius:50%; background: rgba(120,220,180,.9); box-shadow: 0 0 18px rgba(120,220,180,.45); }
    .navlinks{ display:flex; gap:18px; font-size:14px; color: var(--muted); }
    .navlinks a{ color:inherit; text-decoration:none; }
    .navlinks a:hover{ color: rgba(255,255,255,.9); }

    .grid{ margin-top: 26px; display:grid; grid-template-columns: 1.25fr .75fr; gap: 22px; align-items:start; }
    .hero{ padding: 22px 6px 6px; }
    .kicker{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: rgba(255,255,255,.55); margin-bottom: 10px; }
    .title{ font-size: clamp(34px, 4vw, 54px); line-height: 1.05; letter-spacing: .02em; font-weight: 720; margin: 0 0 10px; }
    .subtitle{ color: rgba(255,255,255,.7); font-size: 14px; margin: 0 0 18px; }

    .actions{ display:flex; gap: 10px; margin: 8px 0 14px; flex-wrap: wrap; }
    .btn{
      border: 1px solid rgba(255,255,255,.12);
      background: rgba(255,255,255,.06);
      color: rgba(255,255,255,.92);
      padding: 10px 12px;
      border-radius: 12px;
      cursor:pointer;
      backdrop-filter: blur(10px);
      box-shadow: 0 10px 40px rgba(0,0,0,.25);
      font-weight: 600;
      font-size: 13px;
    }
    .btn:hover{ background: rgba(255,255,255,.09); }
    .btn.primary{ border-color: rgba(120,220,180,.25); background: rgba(120,220,180,.10); }
    .btn.danger{ border-color: rgba(255,120,120,.25); background: rgba(255,120,120,.10); }

    .card{
      background: var(--glass);
      border: 1px solid var(--stroke);
      border-radius: var(--radius2);
      padding: 16px 16px;
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow);
      margin-bottom: 12px;
    }
    .card h3{ margin: 0 0 10px; font-size: 14px; letter-spacing: .02em; }
    .muted{ color: var(--muted); font-size: 12px; }

    .statusbar{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.08);
      overflow:hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .cards3{ display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; margin-top: 12px; }
    .mini{
      border-radius: 16px;
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.07);
      padding: 12px 12px;
      min-height: 86px;
    }
    .mini .label{
      font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
      color: rgba(255,255,255,.62); margin-bottom: 8px;
    }
    .mini .val{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 14px; color: rgba(255,255,255,.90);
    }

    .side{ display:flex; flex-direction:column; gap: 12px; }
    .tbl{ width:100%; border-collapse: collapse; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
    .tbl th, .tbl td{ text-align:left; padding:10px 10px; border-bottom: 1px solid rgba(255,255,255,.08); white-space:nowrap; }
    .tbl th{ color: rgba(255,255,255,.65); font-weight: 700; letter-spacing:.06em; text-transform: uppercase; font-size: 11px; }

    .chartWrap{ height: 240px; }
    .chartWrapSm{ height: 200px; }
    canvas{ display:block; width:100% !important; height:100% !important; }

    @media (max-width: 980px){
      .grid{ grid-template-columns: 1fr; }
      .cards3{ grid-template-columns: 1fr; }
    }
  </style>
</head>

<body>
  <div class="wrap">
    <div class="topbar">
      <div class="brand"><span class="dot"></span><span>POLYSCALP</span></div>
      <div class="navlinks">
        <a href="#statusCard">Status</a>
        <a href="#bookCard">Book</a>
        <a href="#tradeChartsCard">Trade Charts</a>
      </div>
    </div>

    <div class="grid">
      <!-- LEFT -->
      <div>
        <div class="hero">
          <div class="kicker">POLYMARKET · BTC UP/DOWN · 15 MIN</div>
          <h1 class="title">Trading Dashboard</h1>
          <p class="subtitle">Live snapshot + scanner + paper execution + manual close.</p>

          <div class="actions" id="control">
            <button class="btn primary" onclick="startBot()">Start</button>
            <button class="btn" onclick="stopBot()">Stop</button>
            <button class="btn danger" onclick="closeAll()">Close All</button>
            <span class="muted" id="runflag" style="align-self:center;">…</span>
          </div>

          <section class="card" id="statusCard">
            <h3>Status</h3>
            <div class="statusbar" id="status">Connecting…</div>

            <div class="cards3">
              <div class="mini"><div class="label">Slug</div><div class="val" id="slug">--</div></div>
              <div class="mini"><div class="label">TTE</div><div class="val" id="tte">--</div></div>
              <div class="mini"><div class="label">Balance</div><div class="val" id="bal">--</div></div>

              <div class="mini"><div class="label">YES bid/ask</div><div class="val" id="yes">--</div></div>
              <div class="mini"><div class="label">NO bid/ask</div><div class="val" id="no">--</div></div>
              <div class="mini"><div class="label">bet_frac</div><div class="val" id="betfrac">--</div></div>
            </div>
          </section>

          <section class="card" id="bookCard">
            <h3>Bid/Ask (live ~100ms)</h3>
            <div class="muted" style="margin-bottom:10px;">YES + NO bid/ask stream (time-based).</div>
            <div class="chartWrap"><canvas id="bookChart"></canvas></div>
          </section>

          <section class="card" id="tradeChartsCard">
            <h3>Trade-close charts</h3>
            <div class="muted" style="margin-bottom:10px;">
              These update ONLY when a position fully closes (shares -> 0).
            </div>

            <div class="cards3">
              <div class="mini"><div class="label">Total PnL</div><div class="val" id="pnlTotal">--</div></div>
              <div class="mini"><div class="label">Realized PnL</div><div class="val" id="pnlReal">--</div></div>
              <div class="mini"><div class="label">Winrate</div><div class="val" id="winrate">--</div></div>
            </div>

            <div class="chartWrap" style="margin-top:12px;"><canvas id="equityChart"></canvas></div>
            <div class="chartWrapSm" style="margin-top:12px;"><canvas id="pnlChart"></canvas></div>
            <div class="chartWrapSm" style="margin-top:12px;"><canvas id="wrChart"></canvas></div>
          </section>
        </div>
      </div>

      <!-- RIGHT -->
      <div class="side">
        <div class="card">
          <h3>Positions</h3>
          <div class="muted" style="margin-bottom:8px;">Click Close to force-close stuck positions.</div>
          <div style="overflow:auto;">
            <table class="tbl">
              <thead>
                <tr><th>asset</th><th>shares</th><th>avg_px</th><th>action</th></tr>
              </thead>
              <tbody id="positionsBody"></tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <h3>Open Orders</h3>
          <div class="muted" style="margin-bottom:8px;">Resting limit orders</div>
          <div style="overflow:auto;">
            <table class="tbl">
              <thead>
                <tr><th>id</th><th>asset</th><th>side</th><th>px</th><th>shares</th><th>age</th></tr>
              </thead>
              <tbody id="ordersBody"></tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <h3>Quick tips</h3>
          <div class="muted">
            • Trade charts update on FULL close only (shares -> 0).<br/>
            • Book chart updates continuously (time-based) for visibility.
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function fmt2(x){
      if (x === null || x === undefined) return "--";
      if (typeof x === "number") return x.toFixed(2);
      return String(x);
    }
    function esc(s){ return String(s ?? "--").replaceAll("'", "\\'"); }
    function n2(x){ return (x===null||x===undefined) ? "--" : (typeof x==="number" ? x.toFixed(2) : String(x)); }

    async function startBot() { await fetch("/api/start", { method: "POST" }); }
    async function stopBot()  { await fetch("/api/stop",  { method: "POST" }); }
    async function closePos(assetId){
      await fetch("/api/close", {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({asset_id: assetId})
      });
    }
    async function closeAll(){ await fetch("/api/close_all", { method:"POST" }); }

    function renderPositions(list){
      const body = document.getElementById("positionsBody");
      body.innerHTML = "";
      (list || []).forEach(p => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td>${esc(p.asset_id)}</td>`+
          `<td>${n2(p.shares)}</td>`+
          `<td>${n2(p.avg_px)}</td>`+
          `<td><button class="btn danger" style="padding:6px 10px; font-size:12px;" onclick="closePos('${esc(p.asset_id)}')">Close</button></td>`;
        body.appendChild(tr);
      });
      if((list||[]).length===0){
        const tr=document.createElement("tr");
        tr.innerHTML = `<td colspan="4" class="muted" style="padding:12px 10px;">No positions</td>`;
        body.appendChild(tr);
      }
    }

    function renderOrders(list){
      const body = document.getElementById("ordersBody");
      body.innerHTML = "";
      (list || []).forEach(o => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td>${esc(o.id)}</td>`+
          `<td>${esc(o.asset_id)}</td>`+
          `<td>${esc(o.side)}</td>`+
          `<td>${n2(o.price)}</td>`+
          `<td>${n2(o.shares)}</td>`+
          `<td>${o.age_sec ?? "--"}s</td>`;
        body.appendChild(tr);
      });
      if((list||[]).length===0){
        const tr=document.createElement("tr");
        tr.innerHTML = `<td colspan="6" class="muted" style="padding:12px 10px;">No open orders</td>`;
        body.appendChild(tr);
      }
    }

    // ---------- Trade-close charts (x-axis = trade number, not time) ----------
    const MAX_TRADE_POINTS = 300;
    const tradeLabels = [];
    const equitySeries = [];
    const betSeries = [];   // %
    const pnlSeries = [];
    const wrSeries = [];    // %

    function pushTradePoint(label, equity, betFrac, pnlTotal, winrate){
      tradeLabels.push(label);
      equitySeries.push(equity);
      betSeries.push((betFrac==null? null : betFrac*100.0));
      pnlSeries.push(pnlTotal);
      wrSeries.push((winrate==null? null : winrate*100.0));

      if (tradeLabels.length > MAX_TRADE_POINTS){
        tradeLabels.shift(); equitySeries.shift(); betSeries.shift(); pnlSeries.shift(); wrSeries.shift();
      }
    }

    const equityChart = new Chart(document.getElementById("equityChart"), {
      type: "line",
      data: {
        labels: tradeLabels,
        datasets: [
          { label: "Equity", data: equitySeries, tension: 0.25, pointRadius: 0 },
          { label: "Bet %", data: betSeries, tension: 0.25, pointRadius: 0, yAxisID: "y2" }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#cfd6e4" } } },
        scales: {
          x: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } },
          y: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } },
          y2: { position: "right", ticks: { color: "#9aa6bd" }, grid: { display: false } }
        }
      }
    });

    const pnlChart = new Chart(document.getElementById("pnlChart"), {
      type: "line",
      data: { labels: tradeLabels, datasets: [{ label: "Total PnL", data: pnlSeries, tension: 0.25, pointRadius: 0 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#cfd6e4" } } },
        scales: {
          x: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } },
          y: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } }
        }
      }
    });

    const wrChart = new Chart(document.getElementById("wrChart"), {
      type: "line",
      data: { labels: tradeLabels, datasets: [{ label: "Winrate %", data: wrSeries, tension: 0.25, pointRadius: 0 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#cfd6e4" } } },
        scales: {
          x: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } },
          y: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" }, min: 0, max: 100 }
        }
      }
    });

    function redrawTradeCharts(){
      equityChart.update("none");
      pnlChart.update("none");
      wrChart.update("none");
    }

    // ---------- Book chart (time-based, ~100ms) ----------
    const MAX_BOOK_POINTS = 400;
    const bookLabels = [];
    const yesBidSeries = [];
    const yesAskSeries = [];
    const noBidSeries = [];
    const noAskSeries = [];

    function pushBookPoint(label, yb, ya, nb, na){
      bookLabels.push(label);
      yesBidSeries.push(yb);
      yesAskSeries.push(ya);
      noBidSeries.push(nb);
      noAskSeries.push(na);
      if (bookLabels.length > MAX_BOOK_POINTS){
        bookLabels.shift();
        yesBidSeries.shift(); yesAskSeries.shift(); noBidSeries.shift(); noAskSeries.shift();
      }
    }

    const bookChart = new Chart(document.getElementById("bookChart"), {
      type: "line",
      data: {
        labels: bookLabels,
        datasets: [
          { label: "YES bid", data: yesBidSeries, tension: 0.2, pointRadius: 0 },
          { label: "YES ask", data: yesAskSeries, tension: 0.2, pointRadius: 0 },
          { label: "NO bid",  data: noBidSeries,  tension: 0.2, pointRadius: 0 },
          { label: "NO ask",  data: noAskSeries,  tension: 0.2, pointRadius: 0 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#cfd6e4" } } },
        scales: {
          x: { ticks: { color: "#9aa6bd", maxRotation: 0, autoSkip: true }, grid: { color: "rgba(255,255,255,.06)" } },
          y: { ticks: { color: "#9aa6bd" }, grid: { color: "rgba(255,255,255,.06)" } }
        }
      }
    });

    function redrawBookChart(){ bookChart.update("none"); }

    // ---------- WS stream ----------
    let ws;
    let lastTradeSeq = null;
    let haveBaseline = false;
    let lastBookPushMs = 0;

    function connect() {
      ws = new WebSocket(`ws://${location.host}/ws`);

      ws.onmessage = (ev) => {
        const s = JSON.parse(ev.data);

        renderPositions(s.positions);
        renderOrders(s.open_orders);

        document.getElementById("runflag").textContent =
          s.running ? "RUNNING" : (s.status || "STOPPED");

        const line =
          `slug=${fmt2(s.slug)} | tte=${fmt2(s.tte)}s | ` +
          `YES ${fmt2(s.yes_bid)}/${fmt2(s.yes_ask)} | ` +
          `NO ${fmt2(s.no_bid)}/${fmt2(s.no_ask)} | ` +
          `bal=${s.balance ?? "--"} | bet_frac=${s.bet_frac ?? "--"}`;

        document.getElementById("status").textContent = line;

        document.getElementById("slug").textContent = fmt2(s.slug);
        document.getElementById("tte").textContent = (s.tte === null || s.tte === undefined) ? "--" : `${s.tte}s`;
        document.getElementById("bal").textContent = (s.balance === null || s.balance === undefined) ? "--" : String(s.balance);
        document.getElementById("yes").textContent = `${fmt2(s.yes_bid)}/${fmt2(s.yes_ask)}`;
        document.getElementById("no").textContent  = `${fmt2(s.no_bid)}/${fmt2(s.no_ask)}`;
        document.getElementById("betfrac").textContent = (s.bet_frac === null || s.bet_frac === undefined) ? "--" : String(s.bet_frac);

        // cards (these can update continuously)
        const pnl = s.pnl || {};
        const st = s.stats || {};
        const winrate = st.winrate;

        document.getElementById("pnlTotal").textContent = (pnl.total==null) ? "--" : pnl.total.toFixed(2);
        document.getElementById("pnlReal").textContent  = (pnl.realized==null) ? "--" : pnl.realized.toFixed(2);
        document.getElementById("winrate").textContent  = (winrate==null) ? "--" : (winrate*100.0).toFixed(2) + "%";

        // --- Book chart: push by time (~100ms) ---
        const nowMs = Date.now();
        if (nowMs - lastBookPushMs >= 100) {
          lastBookPushMs = nowMs;
          const t = new Date(nowMs);
          const label = t.toLocaleTimeString() + "." + String(t.getMilliseconds()).padStart(3,"0");
          pushBookPoint(
            label,
            (typeof s.yes_bid === "number" ? s.yes_bid : null),
            (typeof s.yes_ask === "number" ? s.yes_ask : null),
            (typeof s.no_bid  === "number" ? s.no_bid  : null),
            (typeof s.no_ask  === "number" ? s.no_ask  : null),
          );
          redrawBookChart();
        }

        // --- Trade charts: update ONLY on trade close (trade_seq changes) ---
        const seq = (s.trade_seq === undefined || s.trade_seq === null) ? null : s.trade_seq;

        // add baseline once (not time-based)
        if (!haveBaseline && typeof s.balance === "number") {
          haveBaseline = true;
          pushTradePoint("START", s.balance, s.bet_frac, (typeof pnl.total==="number"?pnl.total:0.0), winrate);
          redrawTradeCharts();
        }

        if (seq !== null && seq !== lastTradeSeq) {
          // if seq increments, that means a position fully closed
          lastTradeSeq = seq;

          const label = "T" + String(seq);
          if (typeof s.balance === "number") {
            pushTradePoint(
              label,
              s.balance,
              s.bet_frac,
              (typeof pnl.total==="number"?pnl.total:0.0),
              winrate
            );
            redrawTradeCharts();
          }
        }
      };

      ws.onclose = () => setTimeout(connect, 500);
    }

    connect();
  </script>
</body>
</html>
"""

@app.get("/")
async def home():
    return HTMLResponse(HTML)

@app.post("/api/start")
async def api_start():
    await runtime.start()
    return JSONResponse({"ok": True, "running": runtime.is_running()})

@app.post("/api/stop")
async def api_stop():
    await runtime.stop()
    return JSONResponse({"ok": True, "running": runtime.is_running()})

class CloseReq(BaseModel):
    asset_id: str
    shares: float | None = None
    price: float | None = None

@app.post("/api/close")
async def api_close(req: CloseReq):
    await runtime.cmd_close_position(req.asset_id, req.shares, req.price)
    return JSONResponse({"ok": True})

@app.post("/api/close_all")
async def api_close_all():
    await runtime.cmd_close_all()
    return JSONResponse({"ok": True})

@app.websocket("/ws")
async def ws_status(ws: WebSocket):
    await ws.accept()
    seq = 0
    try:
        await ws.send_text(json.dumps(runtime.snapshot))
        while True:
            seq, snap = await runtime.wait_for_update(seq)
            await ws.send_text(json.dumps(snap))
    except WebSocketDisconnect:
        return
    except Exception:
        return
