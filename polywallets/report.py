"""Write CSV / JSON / self-contained HTML outputs."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

CSV_FIELDS = [
    "copy_rank", "score", "wallet", "userName", "tags", "realized_pnl", "pending_realized_pnl",
    "unrealized_pnl", "roi", "win_rate", "n_closed", "profit_factor", "sharpe", "max_drawdown",
    "profitable_week_rate", "top_market_share", "volume", "n_trades", "median_trade_usd",
    "trades_per_active_day", "markets_traded", "vw_entry_price", "sweeper_share", "longshot_share",
    "sell_ratio", "top_category", "median_hold_hours", "copy_pnl", "copy_roi", "penalties", "boards",
]


def _clean(o):
    """JSON can't carry inf/nan."""
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None if math.isnan(o) else (1e9 if o > 0 else -1e9)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def write_csv(rows: list[dict], path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = dict(r)
            out["tags"] = "; ".join(r.get("tags", []))
            out["boards"] = " ".join(r.get("boards", []))
            out["penalties"] = "; ".join(f"{k} x{v}" for k, v in r.get("penalties", {}).items())
            out["copy_pnl"] = r.get("copy", {}).get("pnl")
            out["copy_roi"] = r.get("copy", {}).get("roi")
            for k, v in out.items():
                if isinstance(v, float):
                    out[k] = round(v, 4)
            w.writerow(out)


def write_json(payload: dict, path: Path) -> None:
    path.write_text(json.dumps(_clean(payload), indent=1))


def write_html(payload: dict, path: Path) -> None:
    data = json.dumps(_clean(payload)).replace("</", "<\\/")
    path.write_text(HTML.replace("__DATA__", data))


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket Wallet Scout</title>
<style>
:root{--bg:#f7f7f5;--panel:#fff;--ink:#16181d;--muted:#666b75;--line:#e4e4e0;--accent:#2f5bea;
--pos:#14804a;--neg:#c2352b;--chip:#eef0f4;--bar:#2f5bea;--bar2:#9fb3f5}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#111317;--panel:#191c22;--ink:#e8e9ec;
--muted:#9aa0ab;--line:#2a2e36;--accent:#7b9bff;--pos:#41c37f;--neg:#ff7a6e;--chip:#232731;--bar:#7b9bff;--bar2:#3d4f8f}}
:root[data-theme="dark"]{--bg:#111317;--panel:#191c22;--ink:#e8e9ec;--muted:#9aa0ab;--line:#2a2e36;--accent:#7b9bff;
--pos:#41c37f;--neg:#ff7a6e;--chip:#232731;--bar:#7b9bff;--bar2:#3d4f8f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.sub{color:var(--muted)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:18px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:800px){.grid2{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.barrow{display:grid;grid-template-columns:150px 1fr 70px;gap:8px;align-items:center;margin:4px 0;font-size:13px}
.barrow .track{height:10px;background:var(--chip);border-radius:5px;overflow:hidden}.barrow .fill{height:100%;background:var(--bar)}
.barrow .v{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted)}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
input,select{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit}
.tablewrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{position:sticky;top:0;background:var(--panel);cursor:pointer;font-size:12px;color:var(--muted);user-select:none}
th:nth-child(-n+3),td:nth-child(-n+3){text-align:left}
tbody tr{cursor:pointer}tbody tr:hover{background:var(--chip)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 8px;font-size:11px;margin:1px 2px 1px 0}
.chip.warn{color:var(--neg)}
.name{font-weight:600;max-width:220px;overflow:hidden;text-overflow:ellipsis}#detail h1{overflow-wrap:anywhere}.addr{color:var(--muted);font-size:12px;font-family:ui-monospace,monospace}
#detail{position:fixed;inset:0 0 0 auto;width:min(560px,100%);background:var(--panel);border-left:1px solid var(--line);
transform:translateX(100%);transition:transform .2s;overflow-y:auto;padding:20px;z-index:5;box-shadow:-8px 0 30px rgba(0,0,0,.15)}
#detail.open{transform:none}#detail .close{float:right;cursor:pointer;border:0;background:var(--chip);color:var(--ink);border-radius:6px;padding:4px 10px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.stats div{background:var(--chip);border-radius:8px;padding:8px}
.stats b{display:block;font-variant-numeric:tabular-nums}.stats span{font-size:11px;color:var(--muted)}
svg text{fill:var(--muted);font-size:10px}
.wf td,.wf th{text-align:right}.wf td:first-child,.wf th:first-child{text-align:left}
.note{color:var(--muted);font-size:12px;margin-top:8px}
a{color:var(--accent)}
</style>
</head>
<body>
<div class="wrap">
<h1>Polymarket Wallet Scout</h1>
<div class="sub" id="subtitle"></div>
<div class="kpis" id="kpis"></div>

<div id="wfsec"></div>

<h2>Cohort</h2>
<div class="grid2">
  <div class="card"><div class="sub" style="margin-bottom:8px">Archetypes (wallets)</div><div id="tags"></div></div>
  <div class="card"><div class="sub" style="margin-bottom:8px">Realized PnL by archetype</div><div id="tagpnl"></div></div>
</div>

<h2>Wallets</h2>
<div class="controls">
  <input id="q" placeholder="Search name or address" size="28">
  <select id="tagf"><option value="">All archetypes</option></select>
  <select id="catf"><option value="">All categories</option></select>
  <label class="sub"><input type="checkbox" id="profonly"> Profitable only</label>
</div>
<div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="note">Score = 50% profit (PnL, ROI percentiles) + 50% consistency (Sharpe, profitable weeks, profit factor), times penalties for things a follower can't reproduce. Click a row for details.</div>
</div>
<aside id="detail"></aside>

<script>
const D=__DATA__;
const $=s=>document.querySelector(s);
const usd=v=>v==null?"–":(v<0?"-":"")+"$"+Math.abs(v).toLocaleString(undefined,{maximumFractionDigits:Math.abs(v)<100?2:0});
const pct=v=>v==null?"–":(v*100).toFixed(1)+"%";
const num=(v,d=2)=>v==null?"–":Math.abs(v)>=1e8?"∞":(+v).toFixed(d);
const cls=v=>v>0?"pos":v<0?"neg":"";
const date=t=>new Date(t*1000).toISOString().slice(0,10);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const S=D.summary, R=D.wallets;

$("#subtitle").textContent=`${S.wallets} wallets · ${date(D.window[0])} → ${date(D.window[1])} (${D.days} days) · generated ${date(D.generated)}`;
$("#kpis").innerHTML=[
 [S.wallets,"wallets analyzed"],[S.profitable+" ("+pct(S.profitable/S.wallets)+")","profitable in window"],
 [usd(S.total_realized),"combined realized PnL"],[usd(S.total_volume),"combined volume"],
 [pct(S.median_win_rate),"median win rate"],[pct(S.one_hit_share),"one-hit wallets"]
].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join("");

function bars(el,obj,fmt){const vals=Object.values(obj),m=Math.max(...vals.map(Math.abs),1);
 el.innerHTML=Object.entries(obj).map(([k,v])=>`<div class="barrow"><span>${esc(k)}</span><div class="track"><div class="fill" style="width:${Math.abs(v)/m*100}%;${v<0?"background:var(--neg)":""}"></div></div><span class="v">${fmt(v)}</span></div>`).join("");}
bars($("#tags"),S.tags,v=>v);
bars($("#tagpnl"),S.pnl_by_tag,usd);

if(D.walk_forward&&D.walk_forward.by_score){const W=D.walk_forward;
 const row=(n,x)=>`<tr><td>${n}</td><td>${x.wallets.length}</td><td>${usd(x.invested)}</td><td class="${cls(x.pnl)}">${usd(x.pnl)}</td><td class="${cls(x.roi)}">${pct(x.roi)}</td></tr>`;
 $("#wfsec").innerHTML=`<h2>Does the ranking predict anything?</h2><div class="card"><div class="sub">Ranked on ${date(W.train_window[0])} → ${date(W.train_window[1])}, then copied ${date(W.test_window[0])} → ${date(W.test_window[1])} (unseen) at $${D.sim.stake}/trade, ${D.sim.slippage*100}¢ slippage.</div>
 <div class="tablewrap" style="margin-top:10px;border:0"><table class="wf"><thead><tr><th>Strategy</th><th>Wallets</th><th>Invested</th><th>PnL</th><th>ROI</th></tr></thead><tbody>
 ${row("Top "+W.top_n+" by copy score",W.by_score)}${row("Top "+W.top_n+" by raw PnL",W.by_raw_pnl)}${row("Copy everyone",W.everyone)}</tbody></table></div>
 <div class="note">Open positions in the test window are marked at current prices, so unresolved markets can still move.</div></div>`;}

const tagset=new Set(),catset=new Set();R.forEach(r=>{r.tags.forEach(t=>tagset.add(t));catset.add(r.top_category)});
[...tagset].sort().forEach(t=>$("#tagf").insertAdjacentHTML("beforeend",`<option>${esc(t)}</option>`));
[...catset].sort().forEach(t=>$("#catf").insertAdjacentHTML("beforeend",`<option>${esc(t)}</option>`));

const COLS=[["copy_rank","#",v=>v],["userName","Wallet",(v,r)=>`<div class="name">${esc(v||"anon")}</div><div class="addr">${r.wallet.slice(0,6)}…${r.wallet.slice(-4)}</div>`],
 ["tags","Type",v=>v.map(t=>`<span class="chip">${esc(t)}</span>`).join("")],["score","Score",v=>`<b>${num(v,1)}</b>`],
 ["realized_pnl","Realized",v=>`<span class="${cls(v)}">${usd(v)}</span>`],["roi","ROI",v=>`<span class="${cls(v)}">${pct(v)}</span>`],
 ["win_rate","Win %",pct],["n_closed","Closed",v=>v],["sharpe","Sharpe",v=>num(v)],["profitable_week_rate","+Weeks",pct],
 ["volume","Volume",usd],["median_trade_usd","Med. trade",usd],["top_category","Focus",v=>esc(v)],
 ["copy_roi","Copy ROI",(v)=>v==null?"–":`<span class="${cls(v)}">${pct(v)}</span>`]];
R.forEach(r=>r.copy_roi=r.copy?r.copy.roi:null);
let sortKey="copy_rank",asc=true;
$("#tbl thead").innerHTML="<tr>"+COLS.map(([k,l])=>`<th data-k="${k}">${l}</th>`).join("")+"</tr>";
$("#tbl thead").onclick=e=>{const k=e.target.dataset.k;if(!k)return;asc=sortKey===k?!asc:k==="copy_rank";sortKey=k;render()};
["q","tagf","catf","profonly"].forEach(id=>$("#"+id).addEventListener("input",render));
function render(){const q=$("#q").value.toLowerCase(),tf=$("#tagf").value,cf=$("#catf").value,po=$("#profonly").checked;
 const rows=R.filter(r=>(!q||(r.userName||"").toLowerCase().includes(q)||r.wallet.includes(q))&&(!tf||r.tags.includes(tf))&&(!cf||r.top_category===cf)&&(!po||r.realized_pnl>0))
  .sort((a,b)=>{let x=a[sortKey],y=b[sortKey];if(Array.isArray(x)){x=x.join();y=y.join()}if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*(asc?1:-1)});
 $("#tbl tbody").innerHTML=rows.map(r=>`<tr data-w="${r.wallet}">`+COLS.map(([k,,f])=>`<td>${f(r[k],r)}</td>`).join("")+"</tr>").join("");}
$("#tbl tbody").onclick=e=>{const tr=e.target.closest("tr");if(tr)detail(R.find(r=>r.wallet===tr.dataset.w))};

function spark(daily){const ks=Object.keys(daily);if(ks.length<2)return '<div class="note">Not enough closed positions to chart.</div>';
 let c=0;const pts=ks.map(k=>c+=daily[k]);const W=500,H=140,p=24,mn=Math.min(0,...pts),mx=Math.max(0,...pts),rg=mx-mn||1;
 const x=i=>p+i*(W-2*p)/(pts.length-1),y=v=>H-p-(v-mn)/rg*(H-2*p);
 const d=pts.map((v,i)=>(i?"L":"M")+x(i).toFixed(1)+","+y(v).toFixed(1)).join("");
 return `<svg viewBox="0 0 ${W} ${H}" width="100%"><line x1="${p}" x2="${W-p}" y1="${y(0)}" y2="${y(0)}" stroke="var(--line)"/>
 <path d="${d}" fill="none" stroke="${c>=0?"var(--pos)":"var(--neg)"}" stroke-width="2"/>
 <text x="${p}" y="${H-6}">${ks[0]}</text><text x="${W-p}" y="${H-6}" text-anchor="end">${ks[ks.length-1]}</text>
 <text x="${p}" y="12">${usd(mx)}</text></svg>`;}

function detail(r){const st=(v,l)=>`<div><b>${v}</b><span>${l}</span></div>`;const el=$("#detail");
 const cats={};Object.entries(r.category_share).slice(0,6).forEach(([k,v])=>cats[k]=v);
 el.innerHTML=`<button class="close" onclick="this.parentNode.classList.remove('open')">Close</button>
 <h1>${esc(r.userName||"anon")}</h1><div class="addr">${r.wallet}</div>
 <div style="margin:8px 0">${r.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join("")}${Object.entries(r.penalties).map(([k,v])=>`<span class="chip warn">${esc(k)} ×${v}</span>`).join("")}</div>
 <div class="sub"><a href="https://polymarket.com/profile/${r.wallet}" target="_blank" rel="noopener">Polymarket profile</a>${r.xUsername?` · <a href="https://x.com/${esc(r.xUsername)}" target="_blank" rel="noopener">@${esc(r.xUsername)}</a>`:""} · ${r.boards.join(" ")}</div>
 <div class="stats">${st(num(r.score,1),"copy score #"+r.copy_rank)+st(`<span class="${cls(r.realized_pnl)}">${usd(r.realized_pnl)}</span>`,"realized")+st(usd(r.unrealized_pnl),"open PnL")
 +st(pct(r.roi),"ROI on cost")+st(pct(r.win_rate),r.n_closed+" closed")+st(num(r.profit_factor),"profit factor")
 +st(num(r.sharpe),"Sharpe (daily)")+st(usd(r.max_drawdown),"max drawdown")+st(pct(r.top_market_share),"PnL from top market")
 +st(r.n_trades,"trades")+st(num(r.trades_per_active_day,1),"trades / active day")+st(usd(r.median_trade_usd),"median trade")
 +st(num(r.vw_entry_price,3),"avg entry price")+st(pct(r.sell_ratio),"sold before resolution")+st(r.median_hold_hours==null?"–":num(r.median_hold_hours,1)+"h","median hold")}</div>
 <h2>Cumulative realized PnL</h2>${spark(r.daily_pnl)}
 <h2>Where they trade</h2><div id="dcats"></div>
 ${r.best_trade?`<h2>Best / worst</h2><div class="card"><div class="pos">${usd(r.best_trade.pnl)} · ${esc(r.best_trade.title)} [${esc(r.best_trade.outcome)}]</div><div class="neg" style="margin-top:6px">${usd(r.worst_trade.pnl)} · ${esc(r.worst_trade.title)} [${esc(r.worst_trade.outcome)}]</div></div>`:""}
 ${r.copy?`<h2>If you'd copied them</h2><div class="card">$${D.sim.stake}/trade on ${r.copy.copied_trades} trades (${r.copy.skipped_trades} skipped) → <b class="${cls(r.copy.pnl)}">${usd(r.copy.pnl)}</b> on ${usd(r.copy.invested)} (${pct(r.copy.roi)}), ${pct(r.copy.market_hit_rate)} of markets green.<div class="note">In-sample: same window that produced the score.</div></div>`:""}`;
 bars(el.querySelector("#dcats"),cats,pct);el.classList.add("open");}
render();
</script>
</body>
</html>
"""
