/* SmogGuard AI dashboard. Plain JavaScript, no external libraries (works offline). */
"use strict";

const $ = (id) => document.getElementById(id);
const state = { data: null, date: null, area: null, docTitles: {} };
const SUGGESTIONS = [
  "Will schools in Gulberg close tomorrow?",
  "What should elderly people do during hazardous smog?",
  "What is the PM2.5 forecast for DHA on 2026-11-02?",
  "What is the forecast for Karachi tomorrow?",
  "Kal Johar Town mein hawa kaisi hogi?",
  "Do schools still close only above 300?",
];

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
// Bright readable colours on the dark theme. Solid crimson is reserved for >= 165.
function color(pm) {
  if (pm >= 250) return "rgb(176,0,42)";
  if (pm >= 165) return "rgb(255,23,68)";
  const stops = [[60, [0, 200, 100]], [99, [0, 230, 118]], [100, [230, 194, 0]], [129, [255, 179, 0]],
                 [130, [255, 145, 0]], [164, [255, 109, 0]]];
  const v = Math.max(60, Math.min(164, pm));
  for (let i = 0; i < stops.length - 1; i++) {
    const [a, ca] = stops[i], [b, cb] = stops[i + 1];
    if (v <= b) {
      const t = b === a ? 0 : (v - a) / (b - a);
      return `rgb(${ca.map((x, k) => Math.round(x + t * (cb[k] - x))).join(",")})`;
    }
  }
  return "rgb(255,109,0)";
}
const textOn = (pm) => (pm >= 165 ? "#ffffff" : "#0b0e14");
const tint = (c, a) => c.replace("rgb(", "rgba(").replace(")", `,${a})`);
function cellStyle(pm) {
  if (pm >= 165) return `background:${color(pm)};color:#fff`;
  const c = color(pm);
  return `background:${tint(c, 0.13)};color:${c};box-shadow:inset 0 0 0 1px ${tint(c, 0.35)}`;
}
function status(pm, flagged) {
  if (pm >= 165) return { cls: "hazardous", label: "Hazardous" };
  if (flagged) return { cls: "alert", label: "Watch" };
  if (pm >= 100) return { cls: "moderate", label: "Moderate" };
  return { cls: "safe", label: "Safe" };
}
const stBadge = (pm, flagged) => { const x = status(pm, flagged); return `<span class="badge-st ${x.cls}">${x.label}</span>`; };
const bandName = (pm) => (pm >= 250 ? "Hazardous, school closure level" : pm >= 165 ? "Hazardous" : pm >= 100 ? "Unhealthy, not hazardous" : "Below 100");
function fmtDay(d) {
  const dt = new Date(d + "T00:00:00");
  return dt.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}
function docChip(id) {
  const t = state.docTitles[id] ? ` title="${esc(state.docTitles[id])}"` : "";
  return `<span class="chip-doc"${t}>${esc(id)}</span>`;
}

/* ---------------- overview ---------------- */
async function load() {
  const [r, h] = await Promise.all([fetch("/api/overview"), fetch("/api/health")]);
  if (!r.ok) throw new Error("Overview request failed: " + r.status);
  const d = await r.json();
  const health = h.ok ? await h.json() : { llm: "off" };
  state.data = d;
  state.date = d.next_forecast_date;
  d.documents.forEach((doc) => (state.docTitles[doc.doc_id] = doc.title));
  renderStatus(d, health);
  renderHeader(d);
  renderGrid();
  renderMap();
  renderTrend(d);
  renderQuality(d);
  renderModel(d);
  renderDocs(d);
  renderSuggestions();
  selectArea(d.areas.slice().sort((a, b) => peak(b) - peak(a))[0].area);
}
const forecastOn = (a, date) => a.forecasts.find((f) => f.date === date);
const peak = (a) => forecastOn(a, state.date).pm25;

function renderStatus(d, health) {
  const docs = d.documents, cur = docs.filter((x) => x.status === "current").length;
  const sup = docs.filter((x) => x.status === "superseded").length;
  const hidden = docs.filter((x) => x.hidden_content_removed.length || x.quarantined_chunks.length).length;
  const rows = d.areas.reduce((n, a) => n + a.forecasts.length, 0);
  const llm = health.llm || "off";
  $("status").innerHTML = [
    `<span class="pill"><i class="dot"></i>Model: Ridge · MAE ${d.model.test.ridge_one_step.mae.toFixed(1)}</span>`,
    `<span class="pill"><i class="dot"></i>predictions.csv · ${rows} rows</span>`,
    `<span class="pill"><i class="dot"></i>Docs: ${cur} current · ${sup} superseded</span>`,
    `<span class="pill warn"><i class="dot"></i>${hidden} hidden instruction blocked</span>`,
    `<span class="pill ${llm === "off" ? "off" : ""}"><i class="dot"></i>LLM: ${esc(llm === "off" ? "grounded only" : llm)}</span>`,
  ].join("");
}

function renderHeader(d) {
  const m = d.metrics;
  $("window-note").textContent =
    `Sensor data through ${fmtDay(d.last_observed_date)} · forecasts ${fmtDay(d.forecast_dates[0])} to ${fmtDay(d.forecast_dates.at(-1))}`;
  const hz = m.next_hazardous_areas, al = m.next_alert_areas;
  $("hero-line").textContent =
    `${fmtDay(d.next_forecast_date)}: Lahore's 15 areas average ${Math.round(m.next_avg_pm25)} µg/m³ PM2.5. ` +
    (hz ? `${hz} area${hz > 1 ? "s are" : " is"} forecast hazardous; ` : "No area is forecast hazardous; ") +
    `${al} ${al === 1 ? "is" : "are"} on early-warning watch (≥ ${m.alert_level} µg/m³).`;
  const advice = m.advice.slice(0, 2).map(esc).join(" ");
  $("metrics").innerHTML = `
    <div class="metric"><div class="k">Last observed average (${fmtDay(d.last_observed_date)})</div>
      <div class="v">${m.current_avg_pm25} µg/m³</div><div class="s">US AQI ${m.current_avg_aqi}</div></div>
    <div class="metric"><div class="k">Next-day forecast (daily mean)</div>
      <div class="v">${m.next_avg_pm25} µg/m³</div><div class="s">Highest: ${esc(m.next_max.area)} ${m.next_max.pm25}</div></div>
    <div class="metric"><div class="k">Main pollutant ${docChip(m.main_pollutant_source)}</div>
      <div class="v">${m.main_pollutant}</div><div class="s">Fine particles that reach the bloodstream</div></div>
    <div class="metric"><div class="k">Health advice ${docChip(m.advice_source)}</div>
      <div class="s">${advice}</div></div>`;
}

function renderGrid() {
  const d = state.data;
  const areas = d.areas.slice().sort((a, b) => peak(b) - peak(a));
  let head = `<thead><tr><th scope="col">Area</th><th scope="col" class="divider">${fmtDay(d.last_observed_date).split(" ").slice(0, 2).join(" ")}<br><small>observed</small></th>`;
  d.forecast_dates.forEach((dt) => {
    head += `<th scope="col"><button type="button" data-date="${dt}" aria-pressed="${dt === state.date}">${fmtDay(dt).split(" ").slice(0, 2).join(" ")}</button></th>`;
  });
  head += "</tr></thead>";
  let body = "<tbody>";
  areas.forEach((a) => {
    body += `<tr><th scope="row" data-area="${esc(a.area)}">${esc(a.area)}<small>${a.sensor_id}</small></th>`;
    body += `<td class="obs divider" style="${cellStyle(a.last_observed)}" title="Observed ${a.last_observed}">${a.last_observed.toFixed(1)}</td>`;
    a.forecasts.forEach((f) => {
      const sel = f.date === state.date ? " sel" : "";
      const flag = f.pm25 >= state.data.metrics.alert_level && f.pm25 < 165 ? " flag" : "";
      body += `<td class="${(sel + flag).trim()}" style="${cellStyle(f.pm25)}" title="${esc(a.area)} ${f.date}: ${f.pm25} µg/m³ (${status(f.pm25, f.pm25 >= state.data.metrics.alert_level).label})">${f.pm25.toFixed(1)}</td>`;
    });
    body += "</tr>";
  });
  $("haze").innerHTML = head + body + "</tbody>";
  $("haze").querySelectorAll("thead button").forEach((b) =>
    b.addEventListener("click", () => { state.date = b.dataset.date; renderGrid(); renderMap(); selectArea(state.area); }));
  $("haze").querySelectorAll("tbody th").forEach((th) => th.addEventListener("click", () => selectArea(th.dataset.area)));
  $("legend").innerHTML = [[80, "Safe < 100"], [115, "Moderate 100–129"], [150, "Watch 130–164 (dot)"], [170, "Hazardous ≥ 165"]]
    .map(([v, l]) => `<span><i style="background:${color(v)}"></i>${l}</span>`).join("") +
    `<span>Italic = observed reading</span>`;
}

function renderMap() {
  const d = state.data;
  $("map-date").textContent = fmtDay(state.date);
  const lats = d.areas.map((a) => a.lat), lons = d.areas.map((a) => a.lon);
  const [la0, la1, lo0, lo1] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)];
  const k = Math.cos((31.5 * Math.PI) / 180);
  const sx = 380 / ((lo1 - lo0) * k), sy = 280 / (la1 - la0), s = Math.min(sx, sy);
  const X = (lon) => 20 + (lon - lo0) * k * s, Y = (lat) => 300 - (lat - la0) * s;
  let svg = `<text x="20" y="16" fill="#4a5a62">North ↑</text>`;
  d.areas.forEach((a) => {
    const f = forecastOn(a, state.date);
    const r = 9 + Math.max(0, (f.pm25 - 90) / 10);
    svg += `<g><circle data-area="${esc(a.area)}" cx="${X(a.lon).toFixed(1)}" cy="${Y(a.lat).toFixed(1)}" r="${r.toFixed(1)}"
      fill="${color(f.pm25)}" class="${a.area === state.area ? "active" : ""}" tabindex="0" role="button"
      aria-label="${esc(a.area)} ${f.pm25} micrograms"><title>${esc(a.area)}: ${f.pm25} µg/m³</title></circle>
      <text x="${X(a.lon).toFixed(1)}" y="${(Y(a.lat) + 3).toFixed(1)}" text-anchor="middle" fill="${textOn(f.pm25)}">${a.sensor_id}</text></g>`;
  });
  $("map").innerHTML = svg;
  $("map").querySelectorAll("circle").forEach((c) => {
    c.addEventListener("click", () => selectArea(c.dataset.area));
    c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectArea(c.dataset.area); } });
  });
}

function sparkline(points, w = 300, h = 56) {
  const vals = points.map((p) => p.pm25), lo = Math.min(...vals, 60), hi = Math.max(...vals, 170);
  const x = (i) => (i / (points.length - 1)) * (w - 4) + 2, y = (v) => h - 4 - ((v - lo) / (hi - lo)) * (h - 8);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.pm25).toFixed(1)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <line x1="0" x2="${w}" y1="${y(165)}" y2="${y(165)}" stroke="#ff1744" stroke-dasharray="3 3"/>
    <path d="${path}" fill="none" stroke="#00e676" stroke-width="1.6"/></svg>`;
}

function selectArea(name) {
  const a = state.data.areas.find((x) => x.area === name);
  if (!a) return;
  state.area = name;
  const f = forecastOn(a, state.date);
  $("area-detail").innerHTML = `
    <h3>${esc(a.area)} <small class="hint">${a.sensor_id}</small></h3>
    <div class="big" style="color:${color(f.pm25)}">${f.pm25} µg/m³</div>
    <div class="hint">${fmtDay(state.date)} forecast ${stBadge(f.pm25, f.pm25 >= state.data.metrics.alert_level)}</div>
    <dl>
      <dt>Last observed</dt><dd>${a.last_observed} µg/m³ (${fmtDay(state.data.last_observed_date)})</dd>
      <dt>10-day range</dt><dd>${Math.min(...a.forecasts.map((x) => x.pm25))}–${Math.max(...a.forecasts.map((x) => x.pm25))} µg/m³</dd>
      <dt>Native network</dt><dd>${a.native_network === "batch_1" ? "Batch 1 (UTC, PM2.5)" : "Batch 2 (PKT, AQI)"}</dd>
    </dl>
    ${sparkline(a.history.concat(a.forecasts.map((x) => ({ date: x.date, pm25: x.pm25 }))))}
    <p class="hint">Last 21 observed days, then the 10 forecast days. Dashed line: 165 hazardous threshold.</p>`;
  $("map").querySelectorAll("circle").forEach((c) => c.classList.toggle("active", c.dataset.area === name));
}

function renderTrend(d) {
  const obs = d.city_trend.observed, fc = d.city_trend.forecast, all = obs.concat(fc);
  const W = 640, H = 200, L = 34, B = 22, lo = 0, hi = 200;
  const x = (i) => L + (i / (all.length - 1)) * (W - L - 8), y = (v) => H - B - ((v - lo) / (hi - lo)) * (H - B - 10);
  const line = (pts, off) => pts.map((p, i) => `${i ? "L" : "M"}${x(i + off).toFixed(1)},${y(p.pm25).toFixed(1)}`).join("");
  let g = "";
  [0, 50, 100, 150, 200].forEach((v) => (g += `<line x1="${L}" x2="${W - 8}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(255,255,255,0.08)"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`));
  g += `<line x1="${L}" x2="${W - 8}" y1="${y(165)}" y2="${y(165)}" stroke="#ff1744" stroke-dasharray="4 3"/><text x="${W - 10}" y="${y(165) - 4}" text-anchor="end" fill="#ff1744">Hazardous 165</text>`;
  const al = d.metrics.alert_level;
  g += `<line x1="${L}" x2="${W - 8}" y1="${y(al)}" y2="${y(al)}" stroke="#ff9100" stroke-dasharray="2 4"/><text x="${W - 10}" y="${y(al) - 4}" text-anchor="end" fill="#ff9100">Alert ${al}</text>`;
  g += `<path d="${line(obs, 0)}" fill="none" stroke="#e6edf3" stroke-width="2"/>`;
  g += `<path d="${line([obs.at(-1)].concat(fc), obs.length - 1)}" fill="none" stroke="#00e676" stroke-width="2.2" stroke-dasharray="6 4"/>`;
  g += `<text x="${L}" y="${H - 5}">${fmtDay(obs[0].date)}</text><text x="${x(obs.length - 1)}" y="${H - 5}" text-anchor="middle">${fmtDay(obs.at(-1).date)}</text><text x="${W - 8}" y="${H - 5}" text-anchor="end">${fmtDay(fc.at(-1).date)}</text>`;
  $("trend").innerHTML = g;
}

function renderQuality(d) {
  const q = d.data_quality, [n1, n2] = q.networks;
  const conf = q.flatline_confirmed[0];
  const aqiOnly = n2.flatline_runs.filter((r) => !(conf && r.sensor_id === conf.sensor_id && r.start === conf.start));
  const rows = [
    ["fixed", `<b>Two clocks.</b> ${esc(q.timezone_note)}`],
    ["fixed", `<b>Two units.</b> ${n2.name} reports AQI; converted to PM2.5 with US EPA breakpoints before averaging. After conversion the networks agree within ${q.conversion.mean_abs_diff_ug} µg/m³ on average (${(q.conversion.aqi_exact_match_rate * 100).toFixed(1)}% exact AQI match).`],
    ["fixed", `<b>−999 sentinels.</b> ${n1.sentinels} in ${n1.name} and ${n2.sentinels} in ${n2.name}, set to missing before any average. They never fall on the same area-day, so all ${q.filled_from_other_network} were filled from the other network's reading.`],
    ["warn", conf ? `<b>Stuck sensor.</b> ${conf.sensor_id} read ${conf.stuck_value} (AQI ${conf.aqi_network_stuck_value}) from ${conf.start} to ${conf.end} in both networks: a hardware fault. ${q.interpolated.length} days linearly interpolated from the valid days around them.` : "No stuck sensor detected."],
    ["kept", `<b>Look-alike runs.</b> ${aqiOnly.length} other 3-day repeats appear only in the AQI network (${aqiOnly.map((r) => r.sensor_id + " " + r.start.slice(5)).join(", ")}). Whole-number AQI rounding explains them; the PM2.5 network varies on those days, so its readings are kept.`],
    ["fixed", `<b>Result.</b> ${q.final.rows} area-days, ${q.final.sensors} sensors, ${q.final.missing_after_cleaning} missing values, ${q.final.hazardous_sensor_days} hazardous area-days observed.`],
  ];
  $("dq").innerHTML = rows.map(([t, h]) => `<li><span class="tag ${t}">${t === "warn" ? "fault fixed" : t === "kept" ? "checked" : "fixed"}</span><span>${h}</span></li>`).join("");
}

function renderModel(d) {
  const m = d.model, t = m.test.ridge_one_step, b = m.baselines;
  const row = (name, x, me) => `<tr class="${me ? "me" : ""}"><td>${name}</td><td>${x.mae.toFixed(1)}</td><td>${x.hazardous_caught}/${x.hazardous_days}</td><td>${x.false_alarms}</td><td>${(x.accuracy * 100).toFixed(1)}%</td></tr>`;
  const w = m.weights;
  const sweep = m.alarm.selection_table.filter((s) => s.alarm_at >= 120).map((s) =>
    `<tr class="${s.alarm_at === m.alarm.threshold ? "me" : ""}"><td>≥ ${s.alarm_at}</td><td>${s.caught}/${s.hazardous_days}</td><td>${s.false_alarms}</td><td>${s.f1.toFixed(3)}</td></tr>`).join("");
  $("model").innerHTML = `
    <p class="hint">${esc(m.chosen.model)}, ${m.chosen.feature_list.length} lag features shifted one day, α = ${m.chosen.alpha}. Trained on ${m.split.train_targets.join(" to ")}, tested once on ${m.split.test_targets.join(" to ")} (no shuffling).</p>
    <table class="mt"><thead><tr><th>October test</th><th>MAE</th><th>Hazard caught</th><th>False alarms</th><th>Accuracy</th></tr></thead><tbody>
      ${row("Ridge (ours), 165 rule", t, true)}${row(`Ridge + watch ≥ ${m.alarm.threshold} (advisory)`, m.alarm.test_october_recursive)}${row("7-day average", b.rolling_mean_7d)}${row("Yesterday's value", b.persistence_lag1)}
      ${row("Gradient boosting", b.gradient_boosting_all_features)}${row("Always “not hazardous”", b.always_not_hazardous)}
    </tbody></table>
    <p class="note">Accuracy looks high for every row because hazardous days are rare; the lazy rule scores ${(b.always_not_hazardous.accuracy * 100).toFixed(1)}% while catching nothing. Spikes have no warning in the data, so no model here catches them.</p>
    <p class="note">Tomorrow ≈ ${w.roll28.toFixed(2)} × 28-day mean + ${w.roll14.toFixed(2)} × 14-day mean + ${w.intercept.toFixed(1)} µg/m³ (small weights on shorter lags).</p>
    <table class="mt"><thead><tr><th>Watch if forecast (Sep test)</th><th>Hazard caught</th><th>False alarms</th><th>F1</th></tr></thead><tbody>${sweep}</tbody></table>
    <p class="note">predictions.csv uses the official SPEC rule (<b>≥ 165</b>). The early-warning watch (<b>≥ ${m.alarm.threshold} µg/m³</b>, best F1 on September backtests) is advisory only, shown here and in the assistant. October check: caught ${m.alarm.test_october_recursive.hazardous_caught}/${m.alarm.test_october_recursive.hazardous_days} hazardous days with ${m.alarm.test_october_recursive.false_alarms} false alarms (the plain 165 rule caught ${m.alarm.test_october_recursive_at_165.hazardous_caught}).</p>`;
}

function renderDocs(d) {
  $("docs").innerHTML = d.documents.map((doc) => {
    let st = `<span class="st">${esc(doc.status)} · ${esc(doc.published_date)}</span>`;
    if (doc.status === "superseded") st = `<span class="st bad">Superseded by ${esc(doc.superseded_by)}: never used for answers</span>`;
    if (doc.hidden_content_removed.length) st += `<span class="st bad">Hidden instruction removed at ingestion</span>`;
    if (doc.quarantined_chunks.length) st += `<span class="st bad">${doc.quarantined_chunks.length} passage quarantined</span>`;
    return `<li><b>${esc(doc.doc_id)}</b><span>${esc(doc.title)}${st}</span></li>`;
  }).join("");
}

/* ---------------- chat ---------------- */
function renderSuggestions() {
  $("suggest").innerHTML = SUGGESTIONS.map((s) => `<button type="button">${esc(s)}</button>`).join("");
  $("suggest").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("q").value = b.textContent; send(); }));
}

function formatAnswer(text) {
  const out = [];
  let list = null;
  text.split("\n").forEach((line) => {
    const html = esc(line).replace(/\[(DOC-\d{2})\]/g, (_, id) => docChip(id));
    if (line.startsWith("- ")) {
      if (!list) { list = []; out.push(list); }
      list.push(html.slice(2));
    } else {
      list = null;
      out.push(`<p>${html}</p>`);
    }
  });
  return out.map((x) => (Array.isArray(x) ? `<ul>${x.map((li) => `<li>${li}</li>`).join("")}</ul>` : x)).join("");
}

function addMsg(cls, html) {
  const div = document.createElement("div");
  div.className = "msg " + cls;
  div.innerHTML = html;
  $("log").appendChild(div);
  $("log").scrollTop = $("log").scrollHeight;
  return div;
}

async function send() {
  const q = $("q").value.trim();
  if (!q) return;
  addMsg("user", esc(q));
  $("q").value = "";
  $("send").disabled = true;
  const pending = addMsg("bot", "<p class='hint'>Checking documents and forecast…</p>");
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
    if (!r.ok) throw new Error("The server returned " + r.status);
    const { response, details } = await r.json();
    const badge = response.forecast_called
      ? `<span class="badge on">Forecast tool called</span>`
      : `<span class="badge off">No forecast call</span>`;
    const llmNote = details.llm && details.llm.endsWith("accepted")
      ? `<span class="badge off" title="Rephrased by an LLM, then checked against the evidence">Rephrased (${esc(details.llm.split(":")[0])}, validated)</span>` : "";
    const docMeta = Object.fromEntries(state.data.documents.map((x) => [x.doc_id, x]));
    const sources = response.sources.length
      ? response.sources.map((id) => {
          const m = docMeta[id] || {};
          return `<details class="src"><summary>${docChip(id)}</summary><div class="src-body">${esc(m.title || id)}<br>` +
                 `${esc(m.status || "")} · published ${esc(m.published_date || "?")} · ${esc(m.authority || "")}</div></details>`;
        }).join(" ")
      : `<span class="hint">No document sources</span>`;
    const meta = `<div class="meta"><span>${details.language === "ru" ? "Roman Urdu" : "English"}</span>` +
      `<span>tool calls: ${details.tool_calls ?? 0}</span><span>${esc(details.llm || "grounded")}</span>` +
      `<span>forecast_called: ${response.forecast_called}</span></div>`;
    pending.innerHTML = formatAnswer(response.answer) +
      `<div class="badges">${badge}${llmNote}${sources}<button type="button" class="json-toggle">Show JSON</button></div>${meta}
       <pre class="json" hidden>${esc(JSON.stringify(response, null, 2))}</pre>`;
    pending.dataset.forecastCalled = String(response.forecast_called);
    pending.dataset.language = details.language;
    const btn = pending.querySelector(".json-toggle"), pre = pending.querySelector("pre");
    btn.addEventListener("click", () => { pre.hidden = !pre.hidden; btn.textContent = pre.hidden ? "Show JSON" : "Hide JSON"; });
  } catch (e) {
    pending.innerHTML = `<p>Could not reach the assistant: ${esc(e.message)}. Check that the server is running, then ask again.</p>`;
  } finally {
    $("send").disabled = false;
  }
}

/* ---------------- voice input (Web Speech API) ---------------- */
function setupVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic"), status = $("mic-status");
  if (!SR) {
    mic.disabled = true;
    mic.title = "Voice input needs Chrome, Edge or Safari";
    status.textContent = "Voice input is not supported in this browser. Type your question instead.";
    return;
  }
  let rec = null, listening = false;
  mic.addEventListener("click", () => {
    if (listening && rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = $("voice-lang").value;
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    const base = $("q").value.trim() ? $("q").value.trim() + " " : "";
    rec.onstart = () => { listening = true; mic.setAttribute("aria-pressed", "true"); status.textContent = "Listening… speak your question."; };
    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      $("q").value = base + text;
      if (e.results[e.results.length - 1].isFinal) status.textContent = "Got it. Edit if needed, then press Ask.";
    };
    rec.onerror = (e) => {
      status.textContent = e.error === "not-allowed" ? "Microphone permission was denied. Allow it in the browser and try again."
        : e.error === "no-speech" ? "No speech heard. Press the microphone and try again."
        : e.error === "network" ? "Speech service unreachable (the browser's recognizer needs internet). Type instead."
        : "Voice input error: " + e.error;
    };
    rec.onend = () => { listening = false; mic.setAttribute("aria-pressed", "false"); };
    try { rec.start(); } catch (err) { status.textContent = "Could not start voice input: " + err.message; }
  });
}

$("ask-form").addEventListener("submit", (e) => { e.preventDefault(); send(); });
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
setupVoice();
load().catch((e) => { $("hero-line").textContent = "Could not load data: " + e.message + ". Run python run_pipeline.py, then reload."; });
