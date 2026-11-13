// Lorehaven pricing simulator — UI only. All numbers come from the Python simulate() via /api/simulate.
const form = document.getElementById("controls");
const presetSelect = document.getElementById("preset");
const errorBox = document.getElementById("form-error");
let presets = {};
let debounceTimer = null;

const money = (x) => "$" + Math.round(x).toLocaleString("en-US");
const money2 = (x) => "$" + x.toFixed(2);
const pct = (x) => (100 * x).toFixed(1) + "%";
const count = (x) => Math.round(x).toLocaleString("en-US");

const KPIS = [
  { key: "ltv_per_1000_prospects", label: "Revenue per 1,000 prospects", format: money, primary: true,
    explain: "Total membership revenue over the horizon (lifetime value)." },
  { key: "members_at_end_per_1000", label: "Members at the end", format: count,
    explain: "Members per 1,000 starting prospects in the last quarter." },
  { key: "first_quarter_revenue_per_1000", label: "First-quarter revenue", format: money,
    explain: "Revenue per 1,000 prospects in quarter one." },
  { key: "average_quarterly_churn", label: "Members leaving per quarter", format: pct, lowerIsBetter: true,
    explain: "Average share of members who cancel each quarter." },
];
const GUARDRAILS = [
  ["Average revenue per member per quarter", "average_revenue_per_member_quarter", money2],
  ["Discounts given away per 1,000 prospects", "discount_cost_per_1000", money],
  ["Member-quarters paying a discounted price", "share_of_member_quarters_discounted", pct],
  ["Members leaving per quarter", "average_quarterly_churn", pct],
];

function formToPolicy() {
  const f = new FormData(form);
  return {
    base_price: f.get("base_price"),
    offer_share_high: f.get("offer_share_high"), discount_high: f.get("discount_high"),
    offer_share_low: f.get("offer_share_low"), discount_low: f.get("discount_low"),
    lapsed_get_offers: form.lapsed_get_offers.checked,
    random_depths: form.random_depths.checked,
    new_member_discount: f.get("new_member_discount"),
    established_member_discount: f.get("established_member_discount"),
    horizon_quarters: f.get("horizon_quarters"), discount_rate_pct: f.get("discount_rate_pct"),
  };
}

function fillForm(values) {
  for (const [name, value] of Object.entries(values)) {
    const input = form.elements[name];
    if (!input) continue;
    if (input.type === "checkbox") input.checked = Boolean(value); else input.value = value;
  }
}

async function runSimulation() {
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  const response = await fetch("/api/simulate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formToPolicy()),
  });
  const body = await response.json();
  if (!response.ok) {
    errorBox.textContent = body.error;
    errorBox.hidden = false;
    if (body.field && form.elements[body.field]) form.elements[body.field].setAttribute("aria-invalid", "true");
    return;
  }
  errorBox.hidden = true;
  renderKpis(body.scenario.kpis, body.baseline.kpis);
  renderChart(body.scenario.quarters, body.baseline.quarters);
  renderGuardrails(body.scenario.kpis, body.scenario.warnings);
}

function renderKpis(scenario, baseline) {
  document.getElementById("kpis").innerHTML = KPIS.map((k) => {
    const diff = scenario[k.key] - baseline[k.key];
    const relative = baseline[k.key] ? diff / baseline[k.key] : 0;
    const better = k.lowerIsBetter ? diff < 0 : diff > 0;
    const sign = diff >= 0 ? "+" : "−";
    const deltaText = Math.abs(relative) < 0.0005 ? "same as today"
      : `${sign}${Math.abs(100 * relative).toFixed(0)}% vs today`;
    return `<div class="kpi${k.primary ? " primary" : ""}">
      <div class="label">${k.label}</div>
      <div class="value">${k.format(scenario[k.key])}</div>
      <div class="delta ${Math.abs(relative) < 0.0005 ? "" : better ? "up" : "down"}">${deltaText}</div>
      <div class="explain">${k.explain}</div></div>`;
  }).join("");
}

function renderGuardrails(kpis, warnings) {
  document.getElementById("guardrails").innerHTML = GUARDRAILS
    .map(([label, key, fmt]) => `<dt>${label}</dt><dd>${fmt(kpis[key])}</dd>`).join("");
  document.getElementById("warnings").innerHTML = warnings.length
    ? warnings.map((w) => `<li>${w}</li>`).join("")
    : `<li class="ok">All prices in this policy are inside the range the data tested.</li>`;
}

function niceStep(rough) {
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((candidate) => candidate >= rough);
}

function renderChart(scenario, baseline) {
  const box = document.getElementById("chart");
  const width = box.clientWidth, height = box.clientHeight;
  const pad = { left: 44, right: 12, top: 10, bottom: 26 };
  const n = scenario.length;
  const rawMax = Math.max(...scenario.map((q) => q.members), ...baseline.map((q) => q.members)) || 1;
  const step = niceStep(rawMax / 4);
  const maxY = Math.ceil(rawMax / step) * step;
  const x = (i) => pad.left + (n === 1 ? 0.5 : i / (n - 1)) * (width - pad.left - pad.right);
  const y = (v) => height - pad.bottom - (v / maxY) * (height - pad.top - pad.bottom);
  const path = (rows) => rows.map((q, i) => `${i ? "L" : "M"}${x(i)},${y(q.members)}`).join("");
  const ticks = Array.from({ length: Math.round(maxY / step) + 1 }, (_, i) => i * step);
  box.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img">
    ${ticks.map((t) => `<line class="grid" x1="${pad.left}" x2="${width - pad.right}" y1="${y(t)}" y2="${y(t)}"/>
      <text class="axis-label" x="${pad.left - 8}" y="${y(t) + 4}" text-anchor="end">${count(t)}</text>`).join("")}
    ${scenario.map((q, i) => `<text class="axis-label" x="${x(i)}" y="${height - 6}" text-anchor="middle">Q${q.quarter}</text>`).join("")}
    <path class="area-scenario" d="${path(scenario)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z"/>
    <path class="line-baseline" d="${path(baseline)}"/>
    <path class="line-scenario" d="${path(scenario)}"/>
    <line class="hover-line" id="hover-line" y1="${pad.top}" y2="${height - pad.bottom}" visibility="hidden"/>
  </svg><div class="tooltip" id="tooltip" hidden></div>`;
  const svg = box.querySelector("svg"), tip = box.querySelector("#tooltip"), guide = box.querySelector("#hover-line");
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((event.clientX - rect.left) - pad.left) / ((width - pad.left - pad.right) / Math.max(n - 1, 1)))));
    guide.setAttribute("x1", x(i)); guide.setAttribute("x2", x(i)); guide.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(x(i), 120), width - 120)}px`; tip.style.top = `${pad.top}px`;
    tip.innerHTML = `Q${scenario[i].quarter}<br>Your policy: ${count(scenario[i].members)} members, ${money(scenario[i].revenue)}<br>Today: ${count(baseline[i].members)} members, ${money(baseline[i].revenue)}`;
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; guide.setAttribute("visibility", "hidden"); });
}

form.addEventListener("input", (event) => {
  if (event.target === presetSelect) { fillForm(presets[presetSelect.value].values); }
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runSimulation, 250);
});
window.addEventListener("resize", () => { clearTimeout(debounceTimer); debounceTimer = setTimeout(runSimulation, 150); });

(async function start() {
  presets = await (await fetch("/api/presets")).json();
  presetSelect.innerHTML = Object.entries(presets).map(([id, p]) => `<option value="${id}">${p.label}</option>`).join("");
  fillForm(presets[presetSelect.value].values);
  runSimulation();
})();
