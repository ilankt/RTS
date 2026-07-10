"""Render a balance-sim JSON (from tools/balance_sim.py) into an HTML report.

Usage:
    python tools/render_balance_report.py tools/balance_20_fixed.json out.html \
        --label "20 matches, combat-cadence fixed"
"""
from __future__ import annotations

import argparse
import json
import sys

TEMPLATE = """<title>RTS Balance Sim — Results</title>
<style>
  :root {
    --plane: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
    --muted: #898781; --grid: #e1e0d9; --baseline: #c3c2b7;
    --ring: rgba(11,11,11,0.10); --accent: #8a6d1c; --track: #f0efec;
    --p-balanced: #2a78d6; --p-boomer: #1baf7a; --p-rusher: #eda100; --p-turtle: #008300;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --plane: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
      --muted: #898781; --grid: #2c2c2a; --baseline: #383835;
      --ring: rgba(255,255,255,0.10); --accent: #e3b23c; --track: #232322;
      --p-balanced: #3987e5; --p-boomer: #199e70; --p-rusher: #c98500; --p-turtle: #008300;
    }
  }
  :root[data-theme="light"] {
    --plane: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e;
    --muted: #898781; --grid: #e1e0d9; --baseline: #c3c2b7;
    --ring: rgba(11,11,11,0.10); --accent: #8a6d1c; --track: #f0efec;
    --p-balanced: #2a78d6; --p-boomer: #1baf7a; --p-rusher: #eda100; --p-turtle: #008300;
  }
  :root[data-theme="dark"] {
    --plane: #0d0d0d; --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7;
    --muted: #898781; --grid: #2c2c2a; --baseline: #383835;
    --ring: rgba(255,255,255,0.10); --accent: #e3b23c; --track: #232322;
    --p-balanced: #3987e5; --p-boomer: #199e70; --p-rusher: #c98500; --p-turtle: #008300;
  }
  body { background: var(--plane); color: var(--ink); font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.45; margin: 0; padding: 40px 20px 64px; }
  .wrap { max-width: 880px; margin: 0 auto; display: flex; flex-direction: column; gap: 28px; }
  header .eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 0.09em; text-transform: uppercase; color: var(--accent); margin: 0 0 6px; }
  header h1 { font-size: 26px; font-weight: 650; margin: 0 0 6px; text-wrap: balance; }
  header .meta { color: var(--ink-2); font-size: 13.5px; margin: 0; }
  header .meta .sep { color: var(--muted); padding: 0 6px; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .tile { background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 14px 16px 12px; }
  .tile .label { font-size: 11px; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
  .tile .value { font-size: 26px; font-weight: 650; margin-top: 2px; }
  .tile .sub { font-size: 12px; color: var(--ink-2); margin-top: 1px; }
  section.card { background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 18px 20px 16px; }
  section.card h2 { font-size: 15px; font-weight: 650; margin: 0 0 2px; }
  section.card .desc { font-size: 12.5px; color: var(--ink-2); margin: 0 0 14px; max-width: 65ch; }
  .legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 0 0 14px; }
  .legend .key { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--ink-2); }
  .chip { width: 10px; height: 10px; border-radius: 3px; flex: none; }
  .rows { display: flex; flex-direction: column; gap: 9px; }
  .row { display: grid; grid-template-columns: 96px 1fr 84px; align-items: center; gap: 10px; }
  .row .name { font-size: 13px; color: var(--ink); text-transform: capitalize; }
  .row .val { font-size: 12.5px; color: var(--ink-2); text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .track { background: var(--track); border-radius: 4px; height: 20px; display: flex; gap: 2px; overflow: hidden; }
  .seg { height: 100%; min-width: 2px; }
  .seg:last-child { border-radius: 0 4px 4px 0; }
  .seg:first-child { border-radius: 4px 0 0 4px; }
  @media (prefers-reduced-motion: no-preference) { .seg { transition: opacity 120ms ease; } }
  .track:hover .seg { opacity: 0.55; }
  .track .seg:hover { opacity: 1; }
  .footnote { font-size: 12px; color: var(--muted); margin: 12px 0 0; max-width: 70ch; }
  details.data { margin-top: 12px; }
  details.data summary { font-size: 12px; color: var(--ink-2); cursor: pointer; }
  details.data summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .tablewrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 8px; }
  th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); padding: 6px 12px 6px 0; border-bottom: 1px solid var(--baseline); }
  td { padding: 7px 12px 7px 0; border-bottom: 1px solid var(--grid); vertical-align: top; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-2); white-space: nowrap; }
  .tag { display: inline-block; font-size: 10.5px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); border: 1px solid var(--grid); border-radius: 999px; padding: 1px 8px; margin-left: 6px; }
  .winner { font-weight: 600; text-transform: capitalize; }
  .draw { color: var(--muted); }
  footer { font-size: 12px; color: var(--muted); }
  footer code { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 11.5px; background: var(--track); border-radius: 4px; padding: 1px 6px; color: var(--ink-2); }
  #tip { position: fixed; pointer-events: none; z-index: 10; display: none; background: var(--ink); color: var(--plane); font-size: 12px; line-height: 1.35; border-radius: 6px; padding: 6px 9px; max-width: 260px; font-variant-numeric: tabular-nums; }
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">RTS · Balance Simulator · MASTER_PLAN §8.8</p>
    <h1>__TITLE__</h1>
    <p class="meta">__META__</p>
  </header>
  <div class="tiles" id="tiles"></div>
  <section class="card">
    <h2>Wins by personality</h2>
    <p class="desc">Bar length is the share of appearances won. Mirror matches guarantee their personality a win — the footnote separates them out.</p>
    <div class="rows" id="winrate"></div>
    <p class="footnote" id="winrate-note"></p>
  </section>
  <section class="card">
    <h2>Units trained</h2>
    <p class="desc">Segments are one personality's production; hover for exact counts.</p>
    <div class="legend" id="legend-units"></div>
    <div class="rows" id="units"></div>
    <details class="data"><summary>Data table</summary><div class="tablewrap" id="units-table"></div></details>
  </section>
  <section class="card">
    <h2>Buildings constructed</h2>
    <p class="desc" id="buildings-desc">Production per personality across all matches.</p>
    <div class="legend" id="legend-buildings"></div>
    <div class="rows" id="buildings"></div>
    <details class="data"><summary>Data table</summary><div class="tablewrap" id="buildings-table"></div></details>
  </section>
  <section class="card">
    <h2>Match log</h2>
    <div class="tablewrap">
      <table id="matches">
        <thead><tr><th>Seed</th><th>Matchup</th><th>Winner</th><th class="num">Length</th><th>Outcome</th></tr></thead>
        <tbody></tbody>
      </table>
    </div>
  </section>
  <footer>__FOOTER__</footer>
</div>
<div id="tip" role="presentation"></div>

<script>
  const DATA = __DATA__;
  const PERSONALITIES = ["balanced", "boomer", "rusher", "turtle"];
  const COLOR = { balanced: "var(--p-balanced)", boomer: "var(--p-boomer)", rusher: "var(--p-rusher)", turtle: "var(--p-turtle)" };

  const tip = document.getElementById("tip");
  function showTip(event, html) { tip.innerHTML = html; tip.style.display = "block"; moveTip(event); }
  function moveTip(event) {
    const pad = 12;
    let x = event.clientX + pad, y = event.clientY + pad;
    const rect = tip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 8) x = event.clientX - rect.width - pad;
    if (y + rect.height > window.innerHeight - 8) y = event.clientY - rect.height - pad;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }
  function hideTip() { tip.style.display = "none"; }
  function fmtLength(s) { return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`; }

  const decisive = DATA.matches - DATA.timeouts;
  const coverage = (DATA.never_trained.length === 0 && DATA.never_built.length === 0) ? "100%" :
    `${DATA.never_trained.length + DATA.never_built.length} gaps`;
  const tiles = [
    { label: "Matches", value: DATA.matches, sub: `${DATA.players_per_match} players each` },
    { label: "Decisive", value: decisive, sub: `${DATA.timeouts} timeout draw${DATA.timeouts === 1 ? "" : "s"}` },
    { label: "Avg length", value: fmtLength(DATA.avg_match_sim_seconds), sub: "decisive matches, sim time" },
    { label: "Roster coverage", value: coverage, sub: "units & buildings used" },
  ];
  document.getElementById("tiles").innerHTML = tiles
    .map(t => `<div class="tile"><div class="label">${t.label}</div><div class="value">${t.value}</div><div class="sub">${t.sub}</div></div>`).join("");

  document.getElementById("winrate").innerHTML = PERSONALITIES.map(p => {
    const rec = DATA.win_rate_by_personality[p];
    if (!rec) return "";
    const pct = Math.round(rec.win_rate * 100);
    return `<div class="row">
      <span class="name"><span class="chip" style="background:${COLOR[p]};display:inline-block;margin-right:7px;vertical-align:-1px"></span>${p}</span>
      <div class="track" data-tip="${p}: won ${rec.wins} of ${rec.appearances} appearances (${pct}%)">
        <div class="seg" style="width:${Math.max(rec.win_rate * 100, 0.5)}%;background:${COLOR[p]}"></div>
      </div>
      <span class="val">${rec.wins} / ${rec.appearances}</span>
    </div>`;
  }).join("");

  const mirrors = DATA.matches_detail.filter(m => { const s = Object.values(m.personalities); return s[0] === s[1]; });
  const mirrorWins = mirrors.filter(m => m.completed).length;
  document.getElementById("winrate-note").textContent =
    `${mirrors.length} of ${DATA.matches} matches were mirrors (same personality on both sides); ` +
    `${mirrorWins} of those ended decisively and gift their personality a win. ` +
    `Timeouts count as losses for both sides in the rate above.`;

  function legendHTML() { return PERSONALITIES.map(p => `<span class="key"><span class="chip" style="background:${COLOR[p]}"></span>${p}</span>`).join(""); }
  document.getElementById("legend-units").innerHTML = legendHTML();
  document.getElementById("legend-buildings").innerHTML = legendHTML();

  function stackedRows(totals, byPersonality, noun) {
    const types = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);
    const max = Math.max(...Object.values(totals));
    return types.map(type => {
      const total = totals[type];
      const segs = PERSONALITIES.map(p => {
        const count = (byPersonality[p] || {})[type] || 0;
        if (!count) return "";
        return `<div class="seg" style="width:${(count / max) * 100}%;background:${COLOR[p]}"
          data-tip="<b style='text-transform:capitalize'>${p}</b> ${noun} ${count} ${type.replace(/_/g, " ")}${count === 1 ? "" : "s"} — of ${total} total"></div>`;
      }).join("");
      return `<div class="row">
        <span class="name">${type.replace(/_/g, " ")}</span>
        <div class="track" style="background:transparent">${segs}</div>
        <span class="val">${total}</span>
      </div>`;
    }).join("");
  }
  document.getElementById("units").innerHTML = stackedRows(DATA.unit_usage_total, DATA.unit_usage_by_personality, "trained");
  document.getElementById("buildings").innerHTML = stackedRows(DATA.building_usage_total, DATA.building_usage_by_personality, "built");

  function dataTable(totals, byPersonality) {
    const types = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);
    const head = `<tr><th>Type</th>${PERSONALITIES.map(p => `<th class="num">${p}</th>`).join("")}<th class="num">Total</th></tr>`;
    const rows = types.map(type =>
      `<tr><td>${type.replace(/_/g, " ")}</td>${PERSONALITIES.map(p => `<td class="num">${(byPersonality[p] || {})[type] || 0}</td>`).join("")}<td class="num">${totals[type]}</td></tr>`).join("");
    return `<table><thead>${head}</thead><tbody>${rows}</tbody></table>`;
  }
  document.getElementById("units-table").innerHTML = dataTable(DATA.unit_usage_total, DATA.unit_usage_by_personality);
  document.getElementById("buildings-table").innerHTML = dataTable(DATA.building_usage_total, DATA.building_usage_by_personality);

  document.querySelector("#matches tbody").innerHTML = DATA.matches_detail.map(m => {
    const sides = Object.values(m.personalities);
    const mirror = sides[0] === sides[1];
    const matchup = sides.map(p => `<span class="pill"><span class="chip" style="background:${COLOR[p]}"></span>${p}</span>`)
      .join(`<span style="color:var(--muted);padding:0 7px">vs</span>`);
    const winner = m.winner_personality
      ? `<span class="winner"><span class="chip" style="background:${COLOR[m.winner_personality]};display:inline-block;margin-right:6px;vertical-align:-1px"></span>${m.winner_personality}</span>`
      : `<span class="draw">—</span>`;
    const outcome = m.completed
      ? `Castle destroyed${mirror ? `<span class="tag">mirror</span>` : ""}`
      : `<span class="draw">Timeout at cap</span>`;
    return `<tr><td class="num">${m.seed}</td><td>${matchup}</td><td>${winner}</td><td class="num">${fmtLength(m.sim_seconds)}</td><td>${outcome}</td></tr>`;
  }).join("");

  document.querySelectorAll("[data-tip]").forEach(el => {
    el.addEventListener("mouseenter", e => showTip(e, el.dataset.tip));
    el.addEventListener("mousemove", moveTip);
    el.addEventListener("mouseleave", hideTip);
  });
</script>
"""


def main():
    parser = argparse.ArgumentParser(description="Render a balance-sim JSON to an HTML report.")
    parser.add_argument("input", help="Path to balance_sim.py output JSON")
    parser.add_argument("output", help="Path to write the HTML report")
    parser.add_argument("--title", default=None)
    parser.add_argument("--label", default="", help="Short run label shown in the header meta.")
    parser.add_argument("--footer", default=None)
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)

    seeds = [m["seed"] for m in data.get("matches_detail", [])]
    seed_range = f"seeds {min(seeds)}–{max(seeds)}" if seeds else ""
    title = args.title or f"AI vs AI — {data['matches']}-match run"
    meta_parts = [
        f"{data['players_per_match']}-player matches",
        seed_range,
        "5× speed, capped at 2,400 sim-seconds",
    ]
    if args.label:
        meta_parts.append(args.label)
    meta = '<span class="sep">·</span>'.join(part for part in meta_parts if part)
    footer = args.footer or (
        f"Generated from <code>{args.input}</code>. "
        "Reproduce with <code>python tools/balance_sim.py --matches "
        f"{data['matches']} --players {data['players_per_match']}</code>, then render with "
        "<code>python tools/render_balance_report.py</code>."
    )

    html = (
        TEMPLATE
        .replace("__TITLE__", title)
        .replace("__META__", meta)
        .replace("__FOOTER__", footer)
        .replace("__DATA__", json.dumps(data, separators=(",", ":")))
    )
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
