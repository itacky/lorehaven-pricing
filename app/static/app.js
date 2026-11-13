// Lorehaven pricing simulator — UI only. All numbers come from the Python simulate() via /api/simulate.
const form = document.getElementById("controls");
const presetSelect = document.getElementById("preset");
const errorBox = document.getElementById("form-error");
const horizonButtons = document.querySelectorAll("#horizon-buttons button");
let presets = {};
let debounceTimer = null;
let compareRequest = 0;

const money = (x) => "$" + Math.round(x).toLocaleString("en-US");
const money2 = (x) => "$" + x.toFixed(2);
const pct = (x) => (100 * x).toFixed(1) + "%";
const count = (x) => Math.round(x).toLocaleString("en-US");

const KPIS = [
  { key: "ltv_per_1000_prospects", label: "Lifetime revenue", format: money, tile: "revenue" },
  { key: "members_at_end_per_1000", label: "Members at the end", format: count, tile: "members" },
  { key: "first_quarter_revenue_per_1000", label: "First-quarter revenue", format: money, tile: "first" },
  { key: "average_quarterly_churn", label: "Leaving per quarter", format: pct, tile: "churn", points: true },
];

// ---------- form <-> policy ----------
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
    if (input.type === "checkbox") input.checked = Boolean(value); else input.value = String(value);
  }
  syncControls();
}

// Keep the slider labels, horizon buttons and "random depth" state in step with the form values.
function syncControls() {
  for (const name of ["offer_share_high", "offer_share_low"]) {
    document.getElementById(`${name}_out`).textContent = `${form.elements[name].value}%`;
  }
  const quarters = Number(form.elements.horizon_quarters.value);
  horizonButtons.forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.quarters) === quarters)));
  document.querySelectorAll(".chips").forEach((c) => c.classList.toggle("disabled", form.random_depths.checked));
}

// ---------- simulation ----------
async function simulate(policy) {
  const response = await fetch("/api/simulate", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(policy),
  });
  return { ok: response.ok, body: await response.json() };
}

async function runSimulation() {
  syncControls();
  form.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  const policy = formToPolicy();
  const { ok, body } = await simulate(policy);
  if (!ok) {
    errorBox.textContent = body.error;
    errorBox.hidden = false;
    const field = body.field && form.elements[body.field];
    if (field && field.setAttribute) field.setAttribute("aria-invalid", "true");
    return;
  }
  errorBox.hidden = true;
  renderKpis(body.scenario.kpis, body.baseline.kpis);
  renderChart(body.scenario.quarters, body.baseline.quarters);
  renderGuardrails(body.scenario.kpis);
  renderWarnings(body.scenario.warnings);
  renderCompare(policy, body.scenario.kpis.ltv_per_1000_prospects);
}

// ---------- results ----------
function renderKpis(scenario, baseline) {
  document.getElementById("kpis").innerHTML = KPIS.map((k) => {
    const now = scenario[k.key], before = baseline[k.key];
    let pill, cls = "";
    if (k.points) {
      const diff = 100 * (now - before);
      pill = Math.abs(diff) < 0.05 ? "same" : `${diff > 0 ? "+" : "−"}${Math.abs(diff).toFixed(1)} pts`;
      cls = Math.abs(diff) < 0.05 ? "" : diff > 0 ? "worse" : "better";
    } else {
      const relative = before ? (now - before) / before : 0;
      pill = Math.abs(relative) < 0.0005 ? "same" : `${relative > 0 ? "+" : "−"}${Math.abs(100 * relative).toFixed(0)}%`;
    }
    return `<div class="kpi ${k.tile}">
      <p class="label">${k.label}</p>
      <p class="value">${k.format(now)}</p>
      <p class="delta"><span class="pill ${cls}">${pill}</span>vs ${k.format(before)}</p></div>`;
  }).join("");
}

function renderGuardrails(kpis) {
  const base = Number(form.elements.base_price.value) || 1;
  const paidShare = Math.max(0, Math.min(1, kpis.average_revenue_per_member_quarter / base));
  const discounted = kpis.share_of_member_quarters_discounted;
  document.getElementById("guardrails").innerHTML = `
    <div><div class="meter-row"><span>Paid per member per quarter</span>
      <strong>${money2(kpis.average_revenue_per_member_quarter)} <span class="of">of ${money2(base)}</span></strong></div>
      <div class="meter"><div style="width:${(100 * paidShare).toFixed(1)}%;background:var(--ink)"></div></div></div>
    <div><div class="meter-row"><span>Member-quarters at a discount</span><strong>${pct(discounted)}</strong></div>
      <div class="meter"><div style="width:${(100 * discounted).toFixed(1)}%;background:var(--accent)"></div></div></div>
    <div class="meter-row plain"><span>Discounts given per 1,000 prospects</span><strong>${money(kpis.discount_cost_per_1000)}</strong></div>`;
}

const WARN_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l10 18H2L12 3z"/><path d="M12 10v5M12 18v.5"/></svg>`;
const OK_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>`;

function renderWarnings(warnings) {
  const box = document.getElementById("warnings");
  box.classList.toggle("ok", warnings.length === 0);
  box.innerHTML = warnings.length
    ? `${WARN_ICON}<div><h2>Outside what the data saw</h2><ul>${warnings.map((w) => `<li>${w}</li>`).join("")}</ul>
       <p style="margin-top:8px"><a href="#assumptions">See all assumptions</a></p></div>`
    : `${OK_ICON}<div><h2>Inside the tested range</h2><ul><li>Every price and offer in this policy is within what the data tested.</li></ul></div>`;
}

// Lifetime revenue of each preset at the current horizon, next to the policy on screen.
async function renderCompare(policy, currentValue) {
  const request = ++compareRequest;
  const shared = { horizon_quarters: policy.horizon_quarters, discount_rate_pct: policy.discount_rate_pct };
  const rows = await Promise.all(Object.entries(presets).map(async ([id, p]) => {
    const { ok, body } = await simulate({ ...p.values, ...shared });
    return { id, label: p.label, value: ok ? body.scenario.kpis.ltv_per_1000_prospects : null };
  }));
  if (request !== compareRequest) return;            // a newer run has started
  const matching = rows.find((r) => r.value !== null && Math.abs(r.value - currentValue) < 0.5);
  const list = matching ? rows : [{ id: "_yours", label: "Your policy", value: currentValue }, ...rows];
  const current = matching ? matching.id : "_yours";
  const valid = list.filter((r) => r.value !== null).sort((a, b) => b.value - a.value);
  const top = Math.max(...valid.map((r) => r.value), 1);
  const years = Number(policy.horizon_quarters) / 4;
  document.getElementById("compare-caption").textContent =
    `Lifetime revenue per 1,000 prospects over ${Number.isInteger(years) ? years : years.toFixed(1)} years`;
  document.getElementById("compare-bars").innerHTML = valid.map((r) => `
    <div class="bar-row${r.id === current ? " current" : ""}">
      <span class="name">${r.label}${r.id === current && matching ? " (on screen)" : ""}</span>
      <div class="track"><div style="width:${(100 * Math.max(r.value, 0) / top).toFixed(1)}%"></div></div>
      <span class="amount">${money(r.value)}</span></div>`).join("");
}

function niceStep(rough) {
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((candidate) => candidate >= rough);
}

function renderChart(scenario, baseline) {
  const box = document.getElementById("chart");
  const width = box.clientWidth, height = box.clientHeight;
  const pad = { left: 44, right: 14, top: 12, bottom: 28 };
  const n = scenario.length;
  const rawMax = Math.max(...scenario.map((q) => q.members), ...baseline.map((q) => q.members)) || 1;
  const step = niceStep(rawMax / 4);
  const maxY = Math.ceil(rawMax / step) * step;
  const plotW = width - pad.left - pad.right;
  const x = (i) => pad.left + (n === 1 ? 0.5 : i / (n - 1)) * plotW;
  const y = (v) => height - pad.bottom - (v / maxY) * (height - pad.top - pad.bottom);
  const path = (rows) => rows.map((q, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(q.members).toFixed(1)}`).join("");
  const ticks = Array.from({ length: Math.round(maxY / step) + 1 }, (_, i) => i * step);
  const labelEvery = Math.ceil(n / 12);
  box.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Members per 1,000 prospects: ${count(scenario[n - 1].members)} under your policy and ${count(baseline[n - 1].members)} today by quarter ${n}">
    <defs><linearGradient id="scenario-fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f29a2e" stop-opacity="0.28"/><stop offset="1" stop-color="#f29a2e" stop-opacity="0.02"/></linearGradient></defs>
    ${ticks.map((t) => `<line class="${t === 0 ? "axis" : "grid"}" x1="${pad.left}" x2="${width - pad.right}" y1="${y(t)}" y2="${y(t)}"/>
      <text class="axis-label" x="${pad.left - 10}" y="${y(t) + 4}" text-anchor="end">${count(t)}</text>`).join("")}
    ${scenario.map((q, i) => (i % labelEvery && i !== n - 1) ? "" :
      `<text class="axis-label" x="${x(i)}" y="${height - 8}" text-anchor="middle">Q${q.quarter}</text>`).join("")}
    <path class="area-scenario" d="${path(scenario)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z"/>
    <path class="line-baseline" d="${path(baseline)}"/>
    <path class="line-scenario" d="${path(scenario)}"/>
    <g id="hover" visibility="hidden">
      <line class="hover-line" id="hover-line" y1="${pad.top}" y2="${height - pad.bottom}"/>
      <circle class="dot-baseline" id="dot-baseline" r="5"/>
      <circle class="dot-scenario" id="dot-scenario" r="6"/>
    </g>
    <rect class="hit" x="${pad.left - 10}" y="0" width="${plotW + 20}" height="${height}"/>
  </svg><div class="tooltip" id="tooltip" hidden></div>`;

  const svg = box.querySelector("svg"), tip = box.querySelector("#tooltip"), hover = box.querySelector("#hover");
  const show = (i) => {
    const xs = x(i), ys = y(scenario[i].members), yb = y(baseline[i].members);
    box.querySelector("#hover-line").setAttribute("x1", xs); box.querySelector("#hover-line").setAttribute("x2", xs);
    box.querySelector("#dot-scenario").setAttribute("cx", xs); box.querySelector("#dot-scenario").setAttribute("cy", ys);
    box.querySelector("#dot-baseline").setAttribute("cx", xs); box.querySelector("#dot-baseline").setAttribute("cy", yb);
    hover.setAttribute("visibility", "visible");
    tip.hidden = false;
    const onRight = xs + 16 + 196 <= width;            // sit beside the line, never on the dots
    tip.style.left = `${onRight ? xs + 16 : xs - 16 - 196}px`;
    tip.style.top = `${Math.min(Math.max((ys + yb) / 2, 50), height - 50)}px`;
    tip.innerHTML = `<strong>Quarter ${scenario[i].quarter}</strong>
      <span class="row"><span>Your policy</span><strong>${count(scenario[i].members)} · ${money(scenario[i].revenue)}</strong></span>
      <span class="row"><span>Today</span><strong>${count(baseline[i].members)} · ${money(baseline[i].revenue)}</strong></span>`;
  };
  svg.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const px = (event.clientX - rect.left) * (width / rect.width);
    show(Math.max(0, Math.min(n - 1, Math.round((px - pad.left) / (plotW / Math.max(n - 1, 1))))));
  });
  svg.addEventListener("mouseleave", () => { tip.hidden = true; hover.setAttribute("visibility", "hidden"); });
}

// ---------- events ----------
function scheduleRun(delay = 250) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(runSimulation, delay);
}

function loadPreset(id) {
  presetSelect.value = id;
  fillForm(presets[id].values);
  scheduleRun(0);
}

form.addEventListener("input", (event) => {
  if (event.target === presetSelect) { loadPreset(presetSelect.value); return; }
  syncControls();
  scheduleRun();
});

document.querySelectorAll(".stepper button").forEach((button) => button.addEventListener("click", () => {
  const input = form.elements[button.dataset.target];
  const next = Math.max(Number(input.min) || 0, (Number(input.value) || 0) + Number(button.dataset.step));
  input.value = String(Math.round(next * 2) / 2);
  scheduleRun();
}));

horizonButtons.forEach((button) => button.addEventListener("click", () => {
  form.elements.horizon_quarters.value = button.dataset.quarters;
  scheduleRun(0);
}));

document.getElementById("load-recommended").addEventListener("click", () => loadPreset("recommended"));
document.getElementById("reset-today").addEventListener("click", () => loadPreset("status_quo"));
window.addEventListener("resize", () => scheduleRun(150));

(async function start() {
  presets = await (await fetch("/api/presets")).json();
  presetSelect.innerHTML = Object.entries(presets).map(([id, p]) => `<option value="${id}">${p.label}</option>`).join("");
  loadPreset(presetSelect.value);
})();
