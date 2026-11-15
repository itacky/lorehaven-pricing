// Build presentation/Evaluating_the_Lorehaven_Pricing_Strategy.pptx, the PowerPoint version of the interview deck.
//
// Inputs:  outputs/results/metrics.json, outputs/robustness/crosscheck.json, outputs/results/base_cut_gap_by_quarter.csv,
//          outputs/figures/fig1_*.png, fig2_*.png, app/static/audible_logo.png, presentation/assets/audible_logo_light.png
// Outputs: presentation/Evaluating_the_Lorehaven_Pricing_Strategy.pptx
// Usage:   node presentation/build_deck.js   (needs pptxgenjs; every number is read from the results files, none typed here)

const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(__dirname, "Evaluating_the_Lorehaven_Pricing_Strategy.pptx");
const metrics = JSON.parse(fs.readFileSync(path.join(ROOT, "outputs/results/metrics.json"), "utf8"));
const crosscheck = JSON.parse(fs.readFileSync(path.join(ROOT, "outputs/robustness/crosscheck.json"), "utf8"));
const v = (key) => {
  const entry = metrics[key] || crosscheck[key];
  if (!entry) throw new Error(`Unknown metric: ${key}`);
  return entry.value;
};
const pct0 = (x) => `${Math.round(100 * x)}%`;
const pct1 = (x) => `${(100 * x).toFixed(1)}%`;
const k1 = (x) => `$${(x / 1000).toFixed(1)}k`;
const usd2 = (x) => `$${x.toFixed(2)}`;
const signed0 = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(Math.round(100 * x))}%`;

// ---------- palette (Audible-inspired: near-black statement slides, orange accent) ----------
const INK = "17181C", PAPER = "F7F7F5", PAPER2 = "ECECE8", BODY = "474A52", MUTED = "5D616A";
const ORANGE = "F7991C", ORANGE_TEXT = "A64B00", ORANGE_BIG = "B85400", BAR_ORANGE = "E07B00", GREY_BAR = "8D9099";
const LINE = "D3D3CE", CARD = "FCFCFB", DARK_CARD = "24262C", DARK_TEXT = "C8C9CE";
const FONT = "Arial";
const THEME = {
  name: "Lorehaven AERO", headFontFace: FONT, bodyFontFace: FONT,
  colors: { dk1: INK, lt1: PAPER, dk2: BODY, lt2: PAPER2, accent1: BAR_ORANGE, accent2: ORANGE, accent3: ORANGE_TEXT,
            accent4: GREY_BAR, accent5: "0F6B60", accent6: "2A78D6", hlink: ORANGE_TEXT, folHlink: MUTED },
};

const LOGO_DARK = path.join(ROOT, "app/static/audible_logo.png");          // dark lettering, for light slides
const LOGO_LIGHT = path.join(__dirname, "assets/audible_logo_light.png");  // light lettering, for dark slides
const FIG1 = path.join(ROOT, "outputs/figures/fig1_who_the_offer_wins.png");
const FIG2 = path.join(ROOT, "outputs/figures/fig2_retention_by_tenure.png");

// ---------- layout geometry (inches, 13.333 x 7.5) ----------
const X0 = 0.89, W = 11.56, TITLE_Y = 0.6;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.title = "Evaluating the Lorehaven Pricing Strategy";
pres.author = "Immanuel Tacky";
pres.company = "Audible Economics, Research &amp; Optimization (AERO)";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

// ---------- layouts ----------
function contentLayout(name, background, titleColor, logo, footerColor) {
  pres.defineSlideMaster({
    title: name,
    background: { color: background },
    objects: [
      { image: { path: logo, x: X0, y: 6.93, w: 0.76, h: 0.22 } },
      { placeholder: { options: { name: "title", type: "title", x: X0, y: TITLE_Y, w: W, h: 0.75, fontFace: FONT, fontSize: 28,
                                  bold: true, color: titleColor, margin: 0, valign: "top", align: "left" }, text: "" } },
      { placeholder: { options: { name: "footer", type: "body", x: 1.85, y: 6.9, w: 9.4, h: 0.3, fontFace: FONT, fontSize: 11,
                                  color: footerColor, margin: 0, valign: "middle" }, text: "" } },
    ],
    slideNumber: { x: 12.0, y: 6.9, w: 0.45, h: 0.3, fontFace: FONT, fontSize: 11, color: footerColor, align: "right" },
  });
}
contentLayout("LIGHT", PAPER, INK, LOGO_DARK, MUTED);
contentLayout("ALT", PAPER2, INK, LOGO_DARK, MUTED);
contentLayout("DARK", INK, PAPER, LOGO_LIGHT, "9C9EA6");
pres.defineSlideMaster({
  title: "DARK_COVER",
  background: { color: INK },
  objects: [
    { image: { path: LOGO_LIGHT, x: X0, y: 0.7, w: 2.29, h: 0.66 } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 2.5, w: 10.8, h: 2.0, fontFace: FONT, fontSize: 48,
                                bold: true, color: PAPER, margin: 0, valign: "bottom", align: "left" }, text: "" } },
  ],
});

const DEFAULT_FOOTER = "Evaluating the Lorehaven Pricing Strategy";
function contentSlide(layout, section, title, footer = DEFAULT_FOOTER) {
  const slide = pres.addSlide({ masterName: layout, sectionTitle: section });
  slide.addText(title, { placeholder: "title" });
  slide.addText(footer, { placeholder: "footer" });
  return slide;
}
const text = (slide, value, opts) => slide.addText(value, { isTextBox: true, fontFace: FONT, margin: 0, valign: "top", ...opts });
const rule = (slide, x, y, w, color = LINE) => slide.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color, width: 1 } });
const card = (slide, x, y, w, h, fill = CARD, border = LINE) =>
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { color: border, width: 1 } });

// ---------- numbers ----------
const signupList = v("rates.by_price.signup.base12.price12"), signupFive = v("rates.by_price.signup.base12.price7");
const stay = (seg, tenure, price) => v(`rates.stay.base12.${seg}.${tenure}.price${price}`);
const today = v("policy.today.revenue_per_1000_prospects"), recommended = v("policy.recommended.revenue_per_1000_prospects");
const segs = ["cold", "lapsed_low_podcast", "warm_listener", "win_back"];
const incremental = (s) => v(`segment.${s}.incremental_share_at_5`);
const perThousandAt5 = (s) => 1000 * v(`segment.${s}.share_of_prospects`) * v(`rates.signup.base12.${s}.off5`);
const others = ["lapsed_low_podcast", "warm_listener", "win_back"].map(incremental);
const before = v("base_cut.quarters_before"), after = v("base_cut.quarters_after");
const holdout = (arm) => pct0(v(`assumption.holdout_arm_share.${arm}`));

// ======================================================================= 1. cover
pres.addSection({ title: "The question and the short answer" });
let s = pres.addSlide({ masterName: "DARK_COVER", sectionTitle: "The question and the short answer" });
s.addText("Evaluating the Lorehaven Pricing Strategy", { placeholder: "title" });
text(s, "Did the 2017–2019 price changes work, and what should pricing and discounts be next?", { x: X0, y: 4.65, w: 10.8, h: 0.8, fontSize: 20, color: DARK_TEXT });
text(s, "Immanuel Tacky · Audible Economics, Research & Optimization (AERO)", { x: X0, y: 6.55, w: 10, h: 0.3, fontSize: 12, bold: true, color: ORANGE });
s.addNotes("The brief asks two questions: were the 2017–2019 price changes effective, and what should membership pricing and discounts be going forward. Short answer first, then the evidence, the recommendation and what it can’t tell us.");

// ======================================================================= 2. agenda
s = contentSlide("LIGHT", "The question and the short answer", "Agenda");
const agenda = [
  ["01", "The answer", "Were the 2017–2019 price changes effective?", "Slide 3"],
  ["02", "The data and method", "Three years of randomized pricing, and why group averages are enough", "Slides 4–5"],
  ["03", "The evidence", "Who a $5-off discount brings in, who stays, and the 2019 base cut", "Slides 6–8"],
  ["04", "Recommendation", "The policy, what it earns, and the holdout that keeps testing it", "Slides 9–10"],
  ["05", "Limitations and next steps", "What the numbers can’t tell us, and how to resolve each", "Slide 11"],
];
agenda.forEach(([no, title, sub, slides], i) => {
  const y = 1.6 + i * 0.98;
  rule(s, X0, y, W);
  text(s, no, { x: X0, y: y + 0.14, w: 0.9, h: 0.5, fontSize: 24, bold: true, color: ORANGE_BIG });
  text(s, title, { x: 1.95, y: y + 0.14, w: 8.2, h: 0.36, fontSize: 18, bold: true, color: INK });
  text(s, sub, { x: 1.95, y: y + 0.52, w: 8.6, h: 0.3, fontSize: 13, color: BODY });
  text(s, slides, { x: 10.95, y: y + 0.18, w: 1.5, h: 0.3, fontSize: 12, color: MUTED, align: "right" });
});
rule(s, X0, 1.6 + agenda.length * 0.98, W);
s.addNotes("Five parts: the short answer, the data and method, the evidence, the recommendation with its value, and the limitations with how to resolve them.");

// ======================================================================= 3. the answer
s = contentSlide("LIGHT", "The question and the short answer", "Were the 2017–2019 price changes effective?");
const verdicts = [
  ["Random $1–$5 introductory discounts", "Worked", "D7EFEA", "0B4F47", "Strong evidence.", " Discount size was assigned at random, so price is the only difference between groups.",
   `${pct1(signupList)} vs ${pct1(signupFive)}`, "sign-up at list price vs $5 off"],
  ["Base price cut, $15 → $12 (2019)", "Likely helped", "FCE3C2", "7A3B00", "Weak evidence.", " Panem is the only comparison region, and the gap to it also moved in quarters with no price change.",
   "Trailed → led", `vs Panem: behind in all ${before} quarters at $15, ahead in all ${after} after`],
  ["Random $1–$5 member discounts", "Wasteful", "F8DCDC", "8A1F1F", "Good evidence.", " Observed renewal rates by tenure and price.",
   pct0(stay("high_podcast", "established", 11)), "of established engaged members renew at $11 ($1 off) anyway"],
];
verdicts.forEach(([change, verdict, fill, ink, lead, rest, num, cap], i) => {
  const y = 1.65 + i * 1.45;
  rule(s, X0, y, W);
  text(s, change, { x: X0, y: y + 0.42, w: 3.0, h: 0.62, fontSize: 16, bold: true, color: INK });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 4.1, y: y + 0.5, w: 1.45, h: 0.4, rectRadius: 0.08, fill: { color: fill }, line: { color: fill } });
  text(s, verdict, { x: 4.1, y: y + 0.5, w: 1.45, h: 0.4, fontSize: 12, bold: true, color: ink, align: "center", valign: "middle" });
  text(s, [{ text: lead, options: { bold: true, color: INK } }, { text: rest, options: { color: BODY } }], { x: 5.8, y: y + 0.36, w: 3.4, h: 0.8, fontSize: 12 });
  text(s, num, { x: 9.35, y: y + 0.28, w: 3.1, h: 0.45, fontSize: 24, bold: true, color: INK, align: "right" });
  text(s, cap, { x: 9.35, y: y + 0.76, w: 3.1, h: 0.5, fontSize: 12, color: MUTED, align: "right" });
});
rule(s, X0, 1.65 + 3 * 1.45, W);
s.addNotes("Three verdicts. The discounts are the strongest result because Lorehaven randomized them. The base cut points the right way but rests on one comparison region. Giving every member a random discount every quarter mostly pays people who would renew anyway.");

// ======================================================================= 4. the data
pres.addSection({ title: "The data and how the evidence was built" });
s = contentSlide("DARK", "The data and how the evidence was built", "Three years of randomized pricing to learn from");
text(s, "The data", { x: X0, y: 0.32, w: 4, h: 0.25, fontSize: 12, bold: true, color: ORANGE });
const metricsRow = [
  [`${(v("data.panel_rows") / 1e6).toFixed(1)}M`, "customer-quarters, 2017–2019"],
  [`${Math.round(v("data.customers") / 1000)}k`, "customers across the regions"],
  [pct0(v("projection.tested_offer_share")), "of prospects got a random $1–$5 discount each quarter"],
  ["$15→$12", "base price cut in 2019, everywhere except Panem"],
];
metricsRow.forEach(([num, label], i) => {
  const x = X0 + i * 2.97;
  rule(s, x, 2.75, 2.65, ORANGE);
  text(s, num, { x, y: 2.95, w: 2.9, h: 0.9, fontSize: 40, bold: true, color: ORANGE });
  text(s, label, { x, y: 3.95, w: 2.55, h: 0.8, fontSize: 14, color: DARK_TEXT });
});
s.addNotes("The random discounts are what make this analysis possible: inside the discounting regions, who got an offer and how deep it was were drawn at random. The base-price cut was not randomized, which is why its evidence is weaker.");

// ======================================================================= 5. method
s = contentSlide("ALT", "The data and how the evidence was built", "How I evaluated it");
text(s, "Lorehaven assigned discounts at random, so the difference between two group averages is the effect of price. No model is needed for the main results.",
     { x: X0, y: 1.45, w: W, h: 0.7, fontSize: 16, color: BODY });
const steps = [
  ["1 · Rate tables", "Observed rates at every price", "Sign-up and renewal rates by price, segment and member tenure. Every cell has at least 556 customer-quarters."],
  ["2 · Projection", "Two lines of arithmetic", "New members = prospects × sign-up rate at their price. Members kept = members × renewal rate. Observed rates only."],
  ["3 · Cross-check", `Models agree ${v("crosscheck.same_direction")} of ${v("crosscheck.questions")}`,
   `Regressions, inverse-propensity weighting and a fitted-curve simulator answer the same ${v("crosscheck.questions")} questions: same direction, sizes within ${pct0(v("crosscheck.largest_relative_gap"))}.`],
];
steps.forEach(([step, title, body], i) => {
  const x = X0 + i * 3.94;
  card(s, x, 2.45, 3.68, 2.75);
  text(s, step, { x: x + 0.3, y: 2.72, w: 3.1, h: 0.28, fontSize: 12, bold: true, color: ORANGE_TEXT });
  text(s, title, { x: x + 0.3, y: 3.05, w: 3.1, h: 0.6, fontSize: 16, bold: true, color: INK });
  text(s, body, { x: x + 0.3, y: 3.72, w: 3.1, h: 1.4, fontSize: 14, color: BODY });
});
text(s, "The $15→$12 cut was not randomized, so it is compared with Panem, which never changed price.", { x: X0, y: 5.5, w: W, h: 0.3, fontSize: 12, color: MUTED });
s.addNotes("Because prices were randomized, a difference of averages is the causal effect; a regression would only smooth it. I fit the regressions anyway, in a separate appendix, and they agree on every question. The projection is deliberately simple so anyone can check it by hand.");

// ======================================================================= 6. Fig. 1
pres.addSection({ title: "What the randomized discounts and the base cut show" });
s = contentSlide("LIGHT", "What the randomized discounts and the base cut show", "Who a $5-off discount brings in",
                 "Fig. 1 · $12 base, 2019 · assumes nobody is put off by a discount");
s.addImage({ path: FIG1, x: X0, y: 1.5, w: 6.25, h: 4.51, altText: "Fig. 1: join rate and sign-ups per 1,000 prospects by segment, split into would join anyway and join because of $5 off" });
function callouts(slide, items) {
  items.forEach(([num, body], i) => {
    const y = 1.5 + i * 1.62;
    rule(slide, 7.6, y, 4.85, INK);
    text(slide, num, { x: 7.6, y: y + 0.15, w: 4.85, h: 0.6, fontSize: 32, bold: true, color: ORANGE_BIG });
    text(slide, body, { x: 7.6, y: y + 0.8, w: 4.85, h: 0.7, fontSize: 13, color: BODY });
  });
}
callouts(s, [
  [pct0(incremental("cold")), `of cold prospects who join with $5 off would not have joined at list price (${pct0(Math.min(...others))}–${pct0(Math.max(...others))} in the other segments)`],
  [`${Math.round(perThousandAt5("warm_listener"))} per 1,000`, `warm listeners bring the most sign-ups with $5 off; cold prospects (${Math.round(perThousandAt5("cold"))}) are the largest group`],
  [`${usd2(v("first_quarter.everyone_5_off"))} vs ${usd2(v("first_quarter.today"))}`, "first-quarter revenue per prospect if everyone got $5 off vs today"],
]);
s.addNotes("Fig. 1 shows rate on the left and volume on the right. Blue joins anyway; orange joins because of the discount. Most of the people the discount brings in are genuinely new, and because only joiners get the discount, every segment earns more in its first quarter with it.");

// ======================================================================= 7. Fig. 2
s = contentSlide("ALT", "What the randomized discounts and the base cut show", "Who stays: new members vs established members",
                 "Fig. 2 · $12 base, 2019 · every member had a random $1–$5 discount");
s.addImage({ path: FIG2, x: X0, y: 1.5, w: 6.25, h: 4.51, altText: "Fig. 2: share of members who renew by price and tenure, engaged and less-engaged members" });
callouts(s, [
  [`${pct0(stay("low_podcast", "first_renewal", 11))} vs ${pct0(stay("low_podcast", "established", 11))}`, "less-engaged members who renew at $11 ($1 off): first renewal vs established"],
  [`${pct0(stay("high_podcast", "first_renewal", 11))} vs ${pct0(stay("high_podcast", "established", 11))}`, "engaged members, same comparison"],
  [`${pct0(stay("low_podcast", "first_renewal", 11))} at $11, ${pct0(stay("low_podcast", "first_renewal", 7))} at $7`, "less-engaged members at their first renewal: this is where a discount still changes behaviour"],
]);
s.addNotes("New members are the price-sensitive ones. Established members mostly renew at any price, so today’s random discount for every member spends most of the budget on people who would stay anyway. That’s why the recommendation discounts the first two renewals and tapers after.");

// ======================================================================= 8. base cut
s = contentSlide("LIGHT", "What the randomized discounts and the base cut show", "The 2019 base cut: direction clear, size unclear",
                 "Quarter-by-quarter list-price sign-up, cut regions vs Panem");
const gapRows = fs.readFileSync(path.join(ROOT, "outputs/results/base_cut_gap_by_quarter.csv"), "utf8").trim().split("\n").slice(1).map((line) => line.split(","));
const seasons = ["W", "Sp", "Su", "F"];
const labels = gapRows.map(([q]) => `${seasons[q % 4]} ${17 + Math.floor(q / 4)}`);
const gaps = gapRows.map((r) => Math.round(1000 * Number(r[3])) / 10);           // percentage points, 1 decimal
const isAfter = gapRows.map((r) => r[4] === "True");
s.addChart(pres.charts.BAR, [
  { name: "Both at $15", labels, values: gaps.map((g, i) => (isAfter[i] ? 0 : g)) },
  { name: "Cut regions at $12", labels, values: gaps.map((g, i) => (isAfter[i] ? g : 0)) },
], {
  x: X0, y: 1.45, w: W, h: 3.75, barDir: "col", barGrouping: "stacked", barGapWidthPct: 60,
  chartColors: [GREY_BAR, BAR_ORANGE], showLegend: true, legendPos: "t", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: BODY,
  showTitle: true, title: "List-price sign-up rate, cut regions minus Panem (percentage points)", titleFontSize: 12, titleFontFace: "+mn-lt", titleColor: MUTED,
  catAxisLabelColor: MUTED, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt", catAxisLabelPos: "low",
  valAxisLabelColor: MUTED, valAxisLabelFontSize: 11, valAxisLabelFontFace: "+mn-lt", valAxisLabelFormatCode: "0.0",
  valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: "none" },
});
const gapsBefore = gaps.filter((g, i) => !isAfter[i]);
text(s, [{ text: `Behind Panem in all ${before} quarters at $15, ahead in all ${after} after the cut.`, options: { bold: true, color: INK } },
         { text: ` But the gap already swung between ${Math.min(...gapsBefore).toFixed(1).replace("-", "−")} and ${Math.max(...gapsBefore).toFixed(1).replace("-", "−")} points with no price change, and Panem is the only comparison.`, options: { color: BODY } }],
     { x: X0, y: 5.45, w: 5.55, h: 1.2, fontSize: 13 });
text(s, [{ text: `The same $12 drew ${pct1(v("base_cut.offer_rate_2018_at_12"))} sign-up as a $3 discount on $15, but ${pct1(v("base_cut.list_rate_2019_at_12"))} as the list price.`, options: { bold: true, color: INK } },
         { text: " List-price changes need their own experiment.", options: { color: BODY } }],
     { x: 6.9, y: 5.45, w: 5.55, h: 1.2, fontSize: 13 });
s.addNotes("This is the one result that wasn’t randomized. The direction is clear: the cut regions went from trailing Panem to leading it. The size isn’t, because the gap moves by a couple of points between quarters even when prices don’t change.");

// ======================================================================= 9. recommendation
pres.addSection({ title: "Recommendation, its value and how to test it" });
s = contentSlide("DARK", "Recommendation, its value and how to test it", "Recommendation", "Projected from observed 2019 rates");
const recs = [
  ["1 · Price", "Keep the $12 base", "Test any change in a controlled experiment."],
  ["2 · New customers", "$5-off intro discount by default", `With a randomized holdout: ${holdout("5_off")} get $5 off, ${holdout("list")} pay list price, ${holdout("3_off")} get $3 off.`],
  ["3 · Members", "$5 off the first two renewals", "Then $1 off each renewal."],
  ["4 · Former members", "Win-back discounts in a test group", "Until we can see whether people cancel to collect them."],
];
recs.forEach(([step, title, body], i) => {
  const x = X0 + i * 2.95;
  card(s, x, 1.55, 2.78, 2.65, DARK_CARD, "383B43");
  text(s, step, { x: x + 0.25, y: 1.78, w: 2.3, h: 0.28, fontSize: 12, bold: true, color: ORANGE });
  text(s, title, { x: x + 0.25, y: 2.1, w: 2.3, h: 0.66, fontSize: 16, bold: true, color: PAPER });
  text(s, body, { x: x + 0.25, y: 2.85, w: 2.3, h: 1.25, fontSize: 13, color: DARK_TEXT });
});
text(s, signed0(v("headline.recommended_vs_today")), { x: X0, y: 4.55, w: 3.3, h: 1.1, fontSize: 60, bold: true, color: ORANGE, valign: "middle" });
text(s, `revenue per new prospect vs today over 3 years: ${k1(recommended)} vs ${k1(today)} per 1,000 prospects, holdout included (${signed0(v("headline.recommended_vs_today_h40"))} over 10 years).`,
     { x: 4.35, y: 4.6, w: 8.1, h: 1.0, fontSize: 16, color: DARK_TEXT, valign: "middle" });
s.addNotes("One headline number, and it includes the holdout, so it’s the policy as it would actually run. It assumes average 2019 conditions and that customers respond the same way when most prospects get a discount as when a quarter did, which is exactly what the holdout checks.");

// ======================================================================= 10. policies and holdout
s = contentSlide("LIGHT", "Recommendation, its value and how to test it", "What each policy earns, and how the rollout keeps learning",
                 "“Spot” = an 80% chance of a significant result at the 5% level; ~268k prospects a quarter");
text(s, "3-year revenue per 1,000 new prospects", { x: X0, y: 1.45, w: 5.6, h: 0.32, fontSize: 16, bold: true, color: INK });
const policyRows = [
  ["Today’s policy", "today"], ["$5 off every renewal", "offer_5_members_5_off"], ["$1 off every renewal", "offer_5_members_1_off"],
  ["$2 off every renewal", "offer_5_members_2_off"], ["$5 off first two, then $1", "recommended"],
];
s.addChart(pres.charts.BAR, [{ name: "3-year revenue ($k)", labels: policyRows.map((r) => r[0]),
  values: policyRows.map((r) => Math.round(v(`policy.${r[1]}.revenue_per_1000_prospects`) / 100) / 10) }], {
  x: X0 - 0.1, y: 1.8, w: 5.85, h: 2.65, barDir: "bar", barGapWidthPct: 45, catAxisOrientation: "maxMin",
  chartColors: [GREY_BAR, GREY_BAR, GREY_BAR, GREY_BAR, BAR_ORANGE], invertedColors: [GREY_BAR], showLegend: false,
  showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '"$"0.0"k"', dataLabelFontSize: 11, dataLabelFontFace: "+mn-lt", dataLabelColor: INK,
  catAxisLabelColor: BODY, catAxisLabelFontSize: 11, catAxisLabelFontFace: "+mn-lt",
  valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, valAxisMaxVal: 50,
});
card(s, X0, 4.6, 5.6, 0.95);
text(s, [{ text: "Simulator settings, all bars but today:", options: { bold: true, color: INK } },
         { text: ` $12 base, $5-off intro discount for all new prospects, holdout ${holdout("list")} list / ${holdout("3_off")} $3 off. Only the member renewal discounts change.`, options: { color: BODY } }],
     { x: X0 + 0.2, y: 4.7, w: 5.2, h: 0.8, fontSize: 12, valign: "middle" });
text(s, `The recommended mix earns ${pct0(v("headline.recommended_vs_best_single"))} more than the best flat discount ($${v("headline.best_single_member_discount")}). Without the holdout it projects ${k1(v("policy.full_rollout.revenue_per_1000_prospects"))}.`,
     { x: X0, y: 5.7, w: 5.6, h: 0.6, fontSize: 12, color: MUTED });

const RX = 7.05, RW = 5.4;
text(s, "The holdout: 85 / 10 / 5", { x: RX, y: 1.45, w: RW, h: 0.32, fontSize: 16, bold: true, color: INK });
const arms = [[0.85, BAR_ORANGE, INK, `${holdout("5_off")} get $5 off`], [0.10, INK, PAPER, holdout("list")], [0.05, "F9C27A", INK, ""]];
let ax = RX;
arms.forEach(([share, fill, ink, label]) => {
  s.addShape(pres.shapes.RECTANGLE, { x: ax, y: 1.9, w: RW * share, h: 0.48, fill: { color: fill }, line: { color: fill } });
  if (label) text(s, label, { x: ax, y: 1.9, w: RW * share, h: 0.48, fontSize: 12, bold: true, color: ink, align: "center", valign: "middle" });
  ax += RW * share;
});
text(s, `${holdout("list")} pay list price and ${holdout("3_off")} get $3 off, each customer assigned once. Comparing the ${holdout("list")} group with the ${holdout("5_off")} group shows what the discount really does.`,
     { x: RX, y: 2.5, w: RW, h: 0.6, fontSize: 12, color: MUTED });
const mdeSignup = v("holdout.mde_signup_list10_q1"), mdeRenewal = v("holdout.mde_renewal_list10_q3");
const powerRows = [
  ["Sign-ups", [{ text: "After " }, { text: "one quarter", options: { bold: true, color: INK } }, { text: " it can spot a gap as small as " },
                { text: `${(100 * mdeSignup).toFixed(1)} percentage points`, options: { bold: true, color: INK } },
                { text: `. The real gap is about ${Math.round(100 * v("holdout.signup_gap_list_vs_5_off"))} points, so this is confirmed quickly.` }]],
  ["Renewals", [{ text: "After " }, { text: "three quarters", options: { bold: true, color: INK } }, { text: " it can spot a gap as small as " },
                { text: `${Math.round(100 * mdeRenewal)} percentage points`, options: { bold: true, color: INK } },
                { text: ": enough to see whether discount joiners renew less." }]],
  ["Cost", [{ text: "About " }, { text: `${usd2(v("holdout.cost_per_prospect_quarter"))} per prospect per quarter`, options: { bold: true, color: INK } },
            { text: " in first-quarter revenue given up." }]],
];
powerRows.forEach(([label, runs], i) => {
  const y = 3.25 + i * 0.95;
  rule(s, RX, y, RW);
  text(s, label, { x: RX, y: y + 0.12, w: 1.2, h: 0.3, fontSize: 13, bold: true, color: INK });
  text(s, runs, { x: RX + 1.3, y: y + 0.12, w: RW - 1.3, h: 0.75, fontSize: 13, color: BODY });
});
rule(s, RX, 3.25 + 3 * 0.95, RW);
s.addNotes("Every bar except today uses the same simulator settings: $5 off for new prospects with the 10/5 holdout. Only the renewal discounts change. A flat $5 at every renewal earns the least because established members renew anyway. Sign-ups confirm in one quarter; renewals, the open question, in about three.");

// ======================================================================= 11. limitations
pres.addSection({ title: "What the numbers cannot tell us, and next steps" });
s = contentSlide("ALT", "What the numbers cannot tell us, and next steps", "Limitations, and how to resolve each one", "Code, write-up and simulator: lorehaven-pricing repo");
const limits = [
  ["Broader discount coverage is untested", `About ${pct0(v("projection.tested_offer_share"))} of prospects got a discount; the projection assumes the same response when most do.`,
   "expand coverage in stages and compare against the list-price holdout each quarter."],
  ["Base prices come from different years", "$15 is 2017–18 and $12 is 2019; $13–$14 are blended, and full-price renewals were never tested.",
   "test base prices at the same time in comparable markets, with the same discount rules, plus a small full-price member group."],
  ["Gaming is invisible", "The data can’t show people cancelling to collect a win-back discount or waiting for a deeper one.",
   "track promotion history separately from membership tenure and test a cooldown. Assign the win-back policy before customers churn, to see whether expecting an offer causes cancellations."],
  ["Every quarter looks like 2019", "No seasonality or marketing changes, so the projection ranks policies rather than forecasting revenue.",
   "refresh the rate tables each quarter from the holdout and add quarter-specific rates."],
];
limits.forEach(([title, issue, fix], i) => {
  const x = X0 + (i % 2) * 5.86, y = 1.5 + Math.floor(i / 2) * 2.12;
  card(s, x, y, 5.7, 1.98);
  text(s, title, { x: x + 0.25, y: y + 0.18, w: 5.2, h: 0.32, fontSize: 14, bold: true, color: INK });
  text(s, issue, { x: x + 0.25, y: y + 0.55, w: 5.2, h: 0.45, fontSize: 12, color: BODY });
  text(s, [{ text: "Resolve: ", options: { bold: true, color: ORANGE_TEXT } }, { text: fix, options: { color: INK } }], { x: x + 0.25, y: y + 1.05, w: 5.2, h: 0.85, fontSize: 12 });
});
text(s, [{ text: "Each limit has a direct test, and the holdout built into the recommendation ", options: { color: INK } },
         { text: "answers the biggest one within three quarters.", options: { color: ORANGE_TEXT } }],
     { x: X0, y: 5.9, w: W, h: 0.7, fontSize: 16, bold: true });
s.addNotes("None of these is a reason to wait. The recommendation ships with its own experiment: the holdout tells us within about three quarters whether discount joiners renew less, the biggest open question. The other tests can run alongside it.");

// ======================================================================= 12. thank you
pres.addSection({ title: "Thank you and questions" });
s = pres.addSlide({ masterName: "DARK_COVER", sectionTitle: "Thank you and questions" });
s.addText("Thank you", { placeholder: "title", fontSize: 72 });
text(s, "Questions and discussion welcome.", { x: X0, y: 4.65, w: 10.8, h: 0.6, fontSize: 20, color: DARK_TEXT });
text(s, "Immanuel Tacky · Audible Economics, Research & Optimization (AERO)", { x: X0, y: 6.55, w: 10, h: 0.3, fontSize: 12, bold: true, color: ORANGE });
s.addNotes("Happy to walk through the code, the simulator live, or any of the checks behind the numbers.");

(async () => {
  await pres.writeFile({ fileName: OUT });
  // Optional: write the palette into the file's theme (PowerPoint's colour picker). The slides use explicit colours,
  // so the deck looks the same without it. Point PPTX_APPLY_THEME at an apply_theme.js helper to enable it.
  if (process.env.PPTX_APPLY_THEME) {
    const { applyTheme } = require(process.env.PPTX_APPLY_THEME);
    await applyTheme(OUT, THEME);
  }
  console.log(`wrote ${OUT}`);
})();
