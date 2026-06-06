/* app.js — SEO Command Center live cockpit. Plain DOM + SSE, no build step. */
const $ = (id) => document.getElementById(id);
let totals = { High: 0, Medium: 0, Low: 0, total: 0 };
let checks = [];

function animateValue(id, start, end, duration) {
  const obj = $(id); if (!obj) return;
  let startTimestamp = null;
  const step = (timestamp) => {
    if (!startTimestamp) startTimestamp = timestamp;
    const progress = Math.min((timestamp - startTimestamp) / duration, 1);
    obj.textContent = Math.floor(progress * (end - start) + start);
    if (progress < 1) window.requestAnimationFrame(step);
  };
  window.requestAnimationFrame(step);
}

function updateGauge(score) {
  const g = $("gauge");
  const val = g ? g.querySelector("b") : null;
  if (!g || !val) return;
  val.textContent = score;
  if (score < 40) g.style.borderColor = "var(--red)";
  else if (score < 70) g.style.borderColor = "var(--amber)";
  else g.style.borderColor = "var(--green)";
}

function log(msg) {
  const l = $("log"); if (l.querySelector(".empty")) l.innerHTML = "";
  const d = document.createElement("div"); d.textContent = "› " + msg; l.appendChild(d); l.scrollTop = l.scrollHeight;
}
function label(name) {
  return String(name || "").replaceAll("_", " ");
}
function renderChecklist() {
  const box = $("checklist");
  if (!checks.length) {
    box.innerHTML = `<div class="empty">Waiting for detector checks…</div>`;
    return;
  }
  box.innerHTML = "";
  checks.forEach((item) => {
    const row = document.createElement("div");
    row.className = `check ${item.done ? "done" : ""}`;
    const left = document.createElement("div");
    left.className = "left";
    const tick = document.createElement("span");
    tick.className = "tick";
    tick.textContent = item.done ? "✓" : "";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = label(item.check);
    left.appendChild(tick);
    left.appendChild(name);
    const found = document.createElement("span");
    found.className = "found";
    found.textContent = `${item.found || 0} found`;
    row.appendChild(left);
    row.appendChild(found);
    box.appendChild(row);
  });
}
function setChecks(next) {
  checks = (next || []).map((item) => ({ check: item.check, found: item.found || 0, done: !!item.done }));
  renderChecklist();
}
function updateCheck(data) {
  const existing = checks.find((item) => item.check === data.check);
  if (existing) {
    existing.found = data.found || 0;
    existing.done = true;
  } else {
    checks.push({ check: data.check, found: data.found || 0, done: true });
  }
  renderChecklist();
}
function addIssue(i) {
  const tb = $("tbody"); if (tb.querySelector(".empty")) tb.innerHTML = "";
  const tr = document.createElement("tr");
  const rowClass = `row-${i.severity.toLowerCase()}`;
  tr.className = rowClass;
  tr.innerHTML = `<td><span class="sev ${i.severity.toLowerCase()}">${i.severity}</span></td>
                  <td>${i.type}</td><td>${i.count}</td>`;
  tb.appendChild(tr);
  totals[i.severity] = (totals[i.severity] || 0) + 1; totals.total++;
  animateValue("c-total", parseInt($("c-total").textContent || 0), totals.total, 300);
  animateValue("c-high", parseInt($("c-high").textContent || 0), totals.High, 300);
  animateValue("c-med", parseInt($("c-med").textContent || 0), totals.Medium, 300);
  animateValue("c-low", parseInt($("c-low").textContent || 0), totals.Low, 300);
}
function handle({ event, data }) {
  if (event === "snapshot") {
    if (data.site) { $("meta").textContent = "· " + data.site; $("urls").textContent = (data.urls||0) + " URLs"; }
    setChecks(data.checks || []);
    (data.issues || []).forEach(addIssue);
    if (data.health_score !== undefined) updateGauge(data.health_score);
  } else if (event === "loaded") {
    $("meta").textContent = "· " + data.site; $("urls").textContent = data.urls + " URLs";
    log(`[${new Date().toLocaleTimeString()}] Loaded ${data.urls} URLs from ${data.site}`); $("tbody").innerHTML = "";
    totals = { High:0, Medium:0, Low:0, total:0 };
    setChecks([]);
    updateGauge(0);
  } else if (event === "checks") { setChecks(data.checks || []); }
  else if (event === "progress") {
    updateCheck(data);
    log(`[${new Date().toLocaleTimeString()}] Checked ${label(data.check)}: ${data.found || 0} found`);
  }
  else if (event === "issue") {
    addIssue(data);
    log(`[${new Date().toLocaleTimeString()}] Found ${data.count} × ${data.type}`);
  }
  else if (event === "summary") {
    log(`[${new Date().toLocaleTimeString()}] Audit complete: ${data.total_issues} issue types`);
  }
  else if (event === "score") {
    updateGauge(data.score);
  }
  else if (event === "fixes") {
    const badge = $("fix-badge");
    if (badge) {
        badge.style.display = "inline-flex";
        badge.textContent = `Fixes Ready: ${(data.titles||[]).length + (data.redirect_map||[]).length}`;
    }
    log(`[${new Date().toLocaleTimeString()}] Fixes ready: ${(data.titles||[]).length} titles, ${(data.redirect_map||[]).length} redirects`);
  }
  else if (event === "exported") { $("export").innerHTML = "<b>report.html written ✓</b><br><span style='color:#c8c5be;font-size:12px'>Open or email outputs/report.html to the client.</span>"; }
  else if (event === "saved") {
    log(`[${new Date().toLocaleTimeString()}] report.json saved`);
  }
}
const es = new EventSource("/events");
es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (e) {} };
