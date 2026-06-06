/* app.js — SEO Command Center live cockpit. Plain DOM + SSE, no build step. */
const $ = (id) => document.getElementById(id);
let totals = { High: 0, Medium: 0, Low: 0, total: 0 };
let checks = [];

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
  tr.innerHTML = `<td><span class="sev ${i.severity.toLowerCase()}">${i.severity}</span></td>
                  <td>${i.type}</td><td>${i.count}</td>`;
  tb.appendChild(tr);
  totals[i.severity] = (totals[i.severity] || 0) + 1; totals.total++;
  $("c-total").textContent = totals.total; $("c-high").textContent = totals.High;
  $("c-med").textContent = totals.Medium; $("c-low").textContent = totals.Low;
}
function handle({ event, data }) {
  if (event === "snapshot") {
    if (data.site) { $("meta").textContent = "· " + data.site; $("urls").textContent = (data.urls||0) + " URLs"; }
    setChecks(data.checks || []);
    (data.issues || []).forEach(addIssue);
  } else if (event === "loaded") {
    $("meta").textContent = "· " + data.site; $("urls").textContent = data.urls + " URLs";
    log(`Loaded ${data.urls} URLs from ${data.site}`); $("tbody").innerHTML = "";
    totals = { High:0, Medium:0, Low:0, total:0 };
    setChecks([]);
  } else if (event === "checks") { setChecks(data.checks || []); }
  else if (event === "progress") { updateCheck(data); log(`Checked ${label(data.check)}: ${data.found || 0} found`); }
  else if (event === "issue") { addIssue(data); log(`Found ${data.count} × ${data.type}`); }
  else if (event === "summary") { log(`Audit complete: ${data.total_issues} issue types`); }
  else if (event === "fixes") { log(`Fixes ready: ${(data.titles||[]).length} titles, ${(data.redirect_map||[]).length} redirects`); }
  else if (event === "exported") { $("export").innerHTML = "<b>report.html written ✓</b><br><span style='color:#c8c5be;font-size:12px'>Open or email outputs/report.html to the client.</span>"; }
  else if (event === "saved") { log("report.json saved"); }
}
const es = new EventSource("/events");
es.onmessage = (m) => { try { handle(JSON.parse(m.data)); } catch (e) {} };
