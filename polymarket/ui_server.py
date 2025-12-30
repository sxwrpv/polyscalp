# ui_server.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

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

  <style>
    :root{
      --bg0:#07090b;
      --bg1:#0b0f14;
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
      position:fixed;
      inset:0;
      pointer-events:none;
      opacity:.22;
      background-image:
        linear-gradient(rgba(255,255,255,.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px);
      background-size: 120px 120px;
      mask-image: radial-gradient(closest-side at 55% 45%, rgba(0,0,0,.95), transparent 82%);
    }

    body::after{
      content:"";
      position:fixed;
      inset:-120px;
      pointer-events:none;
      background: radial-gradient(1600px 1200px at 50% 30%, transparent 40%, rgba(0,0,0,.45) 78%);
    }

    .wrap{
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px 22px 40px;
      position:relative;
      z-index:1;
    }

    .topbar{
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 16px;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.08);
      backdrop-filter: blur(10px);
      box-shadow: 0 8px 40px rgba(0,0,0,.25);
    }
    .brand{ display:flex; align-items:center; gap:10px; font-weight:650; letter-spacing:.2px; }
    .dot{ width:10px; height:10px; border-radius:50%; background: rgba(120,220,180,.9); box-shadow: 0 0 18px rgba(120,220,180,.45); }
    .navlinks{ display:flex; gap:18px; font-size:14px; color: var(--muted); }
    .navlinks a{ color:inherit; text-decoration:none; }
    .navlinks a:hover{ color: rgba(255,255,255,.9); }

    .grid{
      margin-top: 26px;
      display:grid;
      grid-template-columns: 1.25fr .75fr;
      gap: 22px;
      align-items:start;
    }

    .hero{ padding: 22px 6px 6px; }
    .kicker{ font-size: 11px; letter-spacing: .22em; text-transform: uppercase; color: rgba(255,255,255,.55); margin-bottom: 10px; }
    .title{ font-size: clamp(34px, 4vw, 54px); line-height: 1.05; letter-spacing: .02em; font-weight: 720; margin: 0 0 10px; }
    .subtitle{ color: rgba(255,255,255,.7); font-size: 14px; margin: 0 0 18px; }

    .chips{ display:flex; flex-wrap:wrap; gap: 10px; margin-bottom: 14px; }
    .chip{
      min-width: 170px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(255,255,255,.045);
      border: 1px solid rgba(255,255,255,.08);
      backdrop-filter: blur(10px);
    }
    .chip b{ display:block; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.85); margin-bottom: 4px; }
    .chip span{ display:block; font-size: 12px; color: rgba(255,255,255,.55); }

    .actions{ display:flex; gap: 10px; margin: 8px 0 24px; }
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
    .btn.danger{ border-color: rgba(255,120,120,.25); background: rgba(255,120,120,.08); }

    .bigwords{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: clamp(36px, 5.8vw, 64px);
      line-height: 1.1;
      letter-spacing: .02em;
      margin: 0;
      padding: 10px 0 18px;
      color: rgba(255,255,255,.9);
    }

    .card{
      background: var(--glass);
      border: 1px solid var(--stroke);
      border-radius: var(--radius2);
      padding: 16px 16px;
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow);
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

    .cards3{
      display:grid;
      grid-template-columns: repeat(3, minmax(0,1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .mini{
      border-radius: 16px;
      background: rgba(255,255,255,.04);
      border: 1px solid rgba(255,255,255,.07);
      padding: 12px 12px;
      min-height: 86px;
    }
    .mini .label{
      font-size: 11px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: rgba(255,255,255,.62);
      margin-bottom: 8px;
    }
    .mini .val{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 14px;
      color: rgba(255,255,255,.90);
      word-break: break-word;
    }

    .side{ display:flex; flex-direction:column; gap: 12px; }

    .portrait{
      border-radius: 22px;
      border: 1px solid rgba(255,255,255,.10);
      background:
        radial-gradient(800px 320px at 30% 0%, rgba(120,220,180,.18), transparent 60%),
        radial-gradient(800px 320px at 80% 10%, rgba(120,130,250,.16), transparent 60%),
        rgba(255,255,255,.04);
      backdrop-filter: blur(16px);
      box-shadow: var(--shadow);
      padding: 18px;
      min-height: 220px;
      display:flex;
      align-items:center;
      justify-content:center;
      position:relative;
      overflow:hidden;
    }
    .portrait::before{
      content:"";
      position:absolute;
      inset:0;
      background:
        linear-gradient(180deg, rgba(255,255,255,.06), transparent 40%),
        radial-gradient(600px 300px at 50% 0%, rgba(255,255,255,.10), transparent 60%);
      opacity:.7;
    }
    .logoBox{ position:relative; display:flex; flex-direction:column; align-items:center; gap: 10px; text-align:center; }
    .logoMark{
      width: 64px; height: 64px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,.14);
      background: rgba(255,255,255,.06);
      display:grid; place-items:center;
      font-weight: 800;
      letter-spacing: .02em;
      box-shadow: 0 10px 60px rgba(0,0,0,.25);
    }
    .logoBox .name{ font-size: 16px; font-weight: 720; }
    .logoBox .desc{ font-size: 12px; color: rgba(255,255,255,.68); max-width: 260px; }

    .tbl{ width:100%; border-collapse: collapse; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 12px; }
    .tbl th, .tbl td{ text-align:left; padding:10px 10px; border-bottom: 1px solid rgba(255,255,255,.08); white-space:nowrap; }
    .tbl th{ color: rgba(255,255,255,.65); font-weight: 700; letter-spacing:.06em; text-transform: uppercase; font-size: 11px; }

    .canvasWrap{
      margin-top: 10px;
      border-radius: 18px;
      border: 1px solid rgba(255,255,255,.10);
      background: rgba(0,0,0,.20);
      overflow:hidden;
    }
    canvas{ width:100%; height:260px; display:block; }

    .legend{
      display:flex;
      gap: 10px;
      flex-wrap:wrap;
      font-size: 12px;
      color: rgba(255,255,255,.70);
      margin-top: 10px;
    }
    .legItem{ display:flex; align-items:center; gap:8px; }
    .sw{ width:10px; height:10px; border-radius:4px; background:#fff; opacity:.9; }

    .footerNote{ text-align:center; color: rgba(255,255,255,.55); font-size: 12px; margin-top: 18px; }

    .reveal{ opacity:0; transform: translateY(10px); transition: 500ms ease; }
    .reveal.show{ opacity:1; transform: translateY(0); }

    @media (max-width: 980px){
      .grid{ grid-template-columns: 1fr; }
      .chips .chip{ min-width: 160px; }
      .cards3{ grid-template-columns: 1fr; }
      canvas{ height:220px; }
    }
  </style>
</head>

<body>
  <div class="wrap">
    <div class="topbar">
      <div class="brand">
        <span class="dot"></span>
        <span>POLYSCALP</span>
      </div>
      <div class="navlinks">
        <a href="#about">About</a>
        <a href="#market">Market</a>
        <a href="#control">Control</a>
      </div>
    </div>

    <div class="grid">
      <!-- LEFT -->
      <div>
        <div class="hero">
          <div class="kicker">POLYMARKET · BTC UP/DOWN · 15 MIN</div>
          <h1 class="title">Trading Dashboard</h1>
          <p class="subtitle">Live book snapshot + scanner + paper execution.</p>

          <div class="chips reveal">
            <div class="chip"><b>WS</b><span>market subscription</span></div>
            <div class="chip"><b>SCANNER</b><span>next market rotation</span></div>
            <div class="chip"><b>EXECUTION</b><span>paper fills + sizing</span></div>
          </div>

          <div class="actions reveal" id="control">
            <button class="btn primary" onclick="startBot()">Start</button>
            <button class="btn" onclick="stopBot()">Stop</button>
            <button class="btn danger" onclick="resetChart()">Reset chart</button>
            <span class="muted" id="runflag" style="align-self:center;">…</span>
          </div>

          <div class="bigwords reveal">
            Live<br/>Status<br/>Line
          </div>

          <section class="card reveal" id="about">
            <h3>Status</h3>
            <div class="statusbar" id="status">Connecting…</div>

            <div class="cards3" id="market">
              <div class="mini"><div class="label">Slug</div><div class="val" id="slug">--</div></div>
              <div class="mini"><div class="label">TTE</div><div class="val" id="tte">--</div></div>
              <div class="mini"><div class="label">Balance</div><div class="val" id="bal">--</div></div>

              <div class="mini"><div class="label">YES bid/ask</div><div class="val" id="yes">--</div></div>
              <div class="mini"><div class="label">NO bid/ask</div><div class="val" id="no">--</div></div>
              <div class="mini"><div class="label">bet_frac</div><div class="val" id="betfrac">--</div></div>
            </div>
          </section>

          <section class="card reveal" style="margin-top:12px;">
            <h3>Live chart</h3>
            <div class="muted">Balance (equity) + YES/NO mid prices. Stored in browser memory (not server).</div>
            <div class="canvasWrap"><canvas id="chart" width="1100" height="260"></canvas></div>
            <div class="legend">
              <div class="legItem"><span class="sw" id="swBal" style="background:#ffffff;"></span> Balance</div>
              <div class="legItem"><span class="sw" id="swYes" style="background:#7cf0c0;"></span> YES mid</div>
              <div class="legItem"><span class="sw" id="swNo"  style="background:#ff7a7a;"></span> NO mid</div>
            </div>
          </section>

          <div class="footerNote reveal">
            Your chart won’t “prove” profitability; it only visualizes your paper model + mid marks.
          </div>
        </div>
      </div>

      <!-- RIGHT -->
      <div class="side">
        <div class="portrait reveal">
          <div class="logoBox">
            <div class="logoMark">PM</div>
            <div class="name">Polyscalp</div>
            <div class="desc">UI reads snapshots from /ws. If you see 0.01/0.99 constantly, your feed mapping is wrong.</div>
          </div>
        </div>

        <div class="card reveal">
          <h3>PnL</h3>
          <div class="cards3">
            <div class="mini"><div class="label">Realized</div><div class="val" id="pnl_real">--</div></div>
            <div class="mini"><div class="label">Unrealized</div><div class="val" id="pnl_unreal">--</div></div>
            <div class="mini"><div class="label">Total</div><div class="val" id="pnl_total">--</div></div>
          </div>
        </div>

        <div class="card reveal">
          <h3>Winrate</h3>
          <div class="cards3">
            <div class="mini"><div class="label">Wins</div><div class="val" id="st_wins">--</div></div>
            <div class="mini"><div class="label">Losses</div><div class="val" id="st_losses">--</div></div>
            <div class="mini"><div class="label">Winrate</div><div class="val" id="st_wr">--</div></div>
          </div>
        </div>

        <div class="card reveal" style="margin-top:12px;">
          <h3>Positions</h3>
          <div class="muted" style="margin-bottom:8px;">Live paper positions (by asset)</div>
          <div style="overflow:auto;">
            <table class="tbl">
              <thead><tr><th>asset</th><th>shares</th><th>avg_px</th></tr></thead>
              <tbody id="positionsBody"></tbody>
            </table>
          </div>
        </div>

        <div class="card reveal" style="margin-top:12px;">
          <h3>Open Orders</h3>
          <div class="muted" style="margin-bottom:8px;">Resting limit orders</div>
          <div style="overflow:auto;">
            <table class="tbl">
              <thead><tr><th>id</th><th>asset</th><th>side</th><th>px</th><th>shares</th><th>age</th></tr></thead>
              <tbody id="ordersBody"></tbody>
            </table>
          </div>
        </div>

        <div class="card reveal">
          <h3>Quick tips</h3>
          <div class="muted">
            • If balance resets, your PaperExecution isn't loading/saving state correctly.<br/>
            • Winrate is meaningless unless your “trade close” definition is consistent.<br/>
            • Chart uses whatever you mark to mid — garbage in, pretty garbage out.
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    // scroll reveal
    const io = new IntersectionObserver((entries)=> {
      entries.forEach(e => { if(e.isIntersecting) e.target.classList.add("show"); });
    }, {threshold: 0.08});
    document.querySelectorAll(".reveal").forEach(el => io.observe(el));

    function fmt2(x){
      if (x === null || x === undefined) return "--";
      if (typeof x === "number") return x.toFixed(2);
      return String(x);
    }
    function esc(s){ return String(s ?? "--"); }
    function n2(x){ return (x===null||x===undefined) ? "--" : (typeof x==="number" ? x.toFixed(2) : String(x)); }

    // ------- tables -------
    function renderPositions(list){
      const body = document.getElementById("positionsBody");
      if(!body) return;
      body.innerHTML = "";
      (list || []).forEach(p => {
        const tr = document.createElement("tr");
        tr.innerHTML =
          `<td>${esc(p.asset_id)}</td>`+
          `<td>${n2(p.shares)}</td>`+
          `<td>${n2(p.avg_px)}</td>`;
        body.appendChild(tr);
      });
      if((list||[]).length===0){
        const tr=document.createElement("tr");
        tr.innerHTML = `<td colspan="3" class="muted" style="padding:12px 10px;">No positions</td>`;
        body.appendChild(tr);
      }
    }

    function renderOrders(list){
      const body = document.getElementById("ordersBody");
      if(!body) return;
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

    // ------- chart (no external libs) -------
    const MAX_PTS = 1800; // ~ 7.5 min at 0.25s; browser-side only
    let tsArr = [], balArr = [], yesArr = [], noArr = [];

    function resetChart(){
      tsArr = []; balArr = []; yesArr = []; noArr = [];
      drawChart();
    }

    function pushPoint(ts, balance, yesMid, noMid){
      if (typeof ts !== "number") return;
      tsArr.push(ts);
      balArr.push(typeof balance === "number" ? balance : null);
      yesArr.push(typeof yesMid === "number" ? yesMid : null);
      noArr.push(typeof noMid === "number" ? noMid : null);

      if (tsArr.length > MAX_PTS){
        tsArr.shift(); balArr.shift(); yesArr.shift(); noArr.shift();
      }
    }

    function drawLine(ctx, xs, ys, x0,y0,w,h, ymin, ymax, color, width){
      ctx.strokeStyle = color;
      ctx.lineWidth = width;
      ctx.beginPath();

      let started = false;
      const n = xs.length;
      for(let i=0;i<n;i++){
        const yv = ys[i];
        if (yv === null || yv === undefined) { started=false; continue; }
        const x = x0 + (i/(n-1 || 1))*w;
        const y = y0 + (1 - ((yv - ymin) / (ymax - ymin || 1)))*h;
        if(!started){ ctx.moveTo(x,y); started=true; }
        else ctx.lineTo(x,y);
      }
      ctx.stroke();
    }

    function drawChart(){
      const canvas = document.getElementById("chart");
      if(!canvas) return;
      const ctx = canvas.getContext("2d");
      const W = canvas.width, H = canvas.height;

      // clear
      ctx.clearRect(0,0,W,H);

      // background grid
      ctx.globalAlpha = 1.0;
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      for(let x=0; x<=W; x+=110){
        ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke();
      }
      for(let y=0; y<=H; y+=65){
        ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke();
      }

      if(tsArr.length < 2) return;

      // compute ranges (balance has different scale than prices)
      const balVals = balArr.filter(v => typeof v === "number");
      const yesVals = yesArr.filter(v => typeof v === "number");
      const noVals  = noArr.filter(v => typeof v === "number");

      // left axis for balance
      let balMin = Math.min(...balVals, 0);
      let balMax = Math.max(...balVals, 1);

      // right axis for prices (0..1-ish)
      let prMin = 0.0, prMax = 1.0;
      const prVals = yesVals.concat(noVals);
      if(prVals.length){
        const mn = Math.min(...prVals);
        const mx = Math.max(...prVals);
        // keep some padding but clamp to [0,1]
        prMin = Math.max(0.0, mn - 0.05);
        prMax = Math.min(1.0, mx + 0.05);
        if(prMax - prMin < 0.08){ prMin = Math.max(0.0, prMin-0.04); prMax = Math.min(1.0, prMax+0.04); }
      }

      const padL = 52, padR = 52, padT = 12, padB = 20;
      const x0 = padL, y0 = padT, w = W - padL - padR, h = H - padT - padB;

      // axes labels
      ctx.fillStyle = "rgba(255,255,255,0.65)";
      ctx.font = "12px ui-monospace, Menlo, Consolas, monospace";
      ctx.fillText(`bal ${balMin.toFixed(2)}..${balMax.toFixed(2)}`, 10, 18);
      ctx.fillText(`px ${prMin.toFixed(2)}..${prMax.toFixed(2)}`, W - 120, 18);

      // map prices onto same chart by drawing them with price-range scaling
      // (so they remain visible). This is “visual convenience”, not statistical correctness.
      drawLine(ctx, tsArr, balArr, x0,y0,w,h, balMin, balMax, "rgba(255,255,255,0.95)", 2.2);

      // prices: draw with their own scaling but same plot area
      // we temporarily reuse the same function with prMin/prMax
      drawLine(ctx, tsArr, yesArr, x0,y0,w,h, prMin, prMax, "rgba(124,240,192,0.90)", 1.8);
      drawLine(ctx, tsArr, noArr,  x0,y0,w,h, prMin, prMax, "rgba(255,122,122,0.90)", 1.8);

      // border
      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.lineWidth = 1;
      ctx.strokeRect(x0,y0,w,h);
    }

    // ------- websocket -------
    let ws;
    function wsUrl(){
      const proto = (location.protocol === "https:") ? "wss" : "ws";
      return `${proto}://${location.host}/ws`;
    }

    function connect() {
      ws = new WebSocket(wsUrl());

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
          `bal=${fmt2(s.balance)} | bet_frac=${fmt2(s.bet_frac)}`;

        document.getElementById("status").textContent = line;

        document.getElementById("slug").textContent = fmt2(s.slug);
        document.getElementById("tte").textContent = (s.tte === null || s.tte === undefined) ? "--" : `${s.tte}s`;
        document.getElementById("bal").textContent = fmt2(s.balance);
        document.getElementById("yes").textContent = `${fmt2(s.yes_bid)}/${fmt2(s.yes_ask)}`;
        document.getElementById("no").textContent  = `${fmt2(s.no_bid)}/${fmt2(s.no_ask)}`;
        document.getElementById("betfrac").textContent = fmt2(s.bet_frac);

        // pnl + stats
        const pnl = s.pnl || {};
        document.getElementById("pnl_real").textContent   = fmt2(pnl.realized);
        document.getElementById("pnl_unreal").textContent = fmt2(pnl.unrealized);
        document.getElementById("pnl_total").textContent  = fmt2(pnl.total);

        const st = s.stats || {};
        document.getElementById("st_wins").textContent   = (st.wins ?? "--");
        document.getElementById("st_losses").textContent = (st.losses ?? "--");
        document.getElementById("st_wr").textContent     = (st.winrate === undefined || st.winrate === null) ? "--" : (typeof st.winrate==="number" ? (st.winrate*100).toFixed(2)+"%" : String(st.winrate));

        // chart points
        const yesMid = (typeof s.yes_bid==="number" && typeof s.yes_ask==="number") ? (s.yes_bid+s.yes_ask)/2 : null;
        const noMid  = (typeof s.no_bid==="number"  && typeof s.no_ask==="number")  ? (s.no_bid+s.no_ask)/2   : null;
        pushPoint(s.ts, (typeof s.balance==="number" ? s.balance : null), yesMid, noMid);
        drawChart();
      };

      ws.onclose = () => setTimeout(connect, 500);
    }

    async function startBot() { await fetch("/api/start", { method: "POST" }); }
    async function stopBot()  { await fetch("/api/stop",  { method: "POST" }); }

    // initial
    connect();
    drawChart();
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


@app.websocket("/ws")
async def ws_status(ws: WebSocket):
    await ws.accept()
    seq = -1
    try:
        await ws.send_text(json.dumps(runtime.snapshot, default=str, separators=(",", ":")))
        while True:
            seq, snap = await runtime.wait_for_update(seq)
            await ws.send_text(json.dumps(snap, default=str, separators=(",", ":")))
    except WebSocketDisconnect:
        return
    except Exception:
        return