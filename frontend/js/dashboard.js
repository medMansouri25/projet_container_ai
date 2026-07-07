/* dashboard.js — KPIs et graphiques via GET /api/dashboard */

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

async function load() {
  try {
    const r = await fetch(`${await apiBase()}/api/dashboard`);
    const s = await r.json();
    render(s);
  } catch (err) {
    const alert = document.getElementById("error-alert");
    alert.textContent = "Chargement impossible : " + err.message;
    alert.hidden = false;
  }
}

function render(s) {
  document.getElementById("kpi-total").textContent = s.total;
  document.getElementById("kpi-valid").textContent = s.valid_pct + "%";
  document.getElementById("kpi-conf").textContent = s.avg_conf_pct + "%";
  document.getElementById("kpi-today").textContent = s.today_count;

  document.getElementById("bar-chart").innerHTML = s.per_day.map(d => `
    <div class="bar-col" title="${esc(d.label)} : ${d.count} scan(s)">
      <span class="bar-count">${d.count || ""}</span>
      <div class="bar" style="height: ${d.count ? d.pct : 2}%"></div>
      <span class="bar-label">${esc(d.label)}</span>
    </div>`).join("");

  const donut = document.getElementById("donut");
  donut.style.background =
    `conic-gradient(var(--ok) 0 ${s.valid_pct}%, #fbbf24 ${s.valid_pct}% 100%)`;
  document.getElementById("donut-pct").textContent = s.valid_pct + "%";
  document.getElementById("valid-count").textContent = s.valid_count;
  document.getElementById("invalid-count").textContent = s.invalid_count;

  document.getElementById("top-owners").innerHTML = s.top_owners.length
    ? s.top_owners.map(o => `
      <div class="hbar-row">
        <span class="hbar-code">${esc(o.code)}</span>
        <div class="hbar-track"><div class="hbar" style="width: ${o.pct}%"></div></div>
        <span class="hbar-count">${o.count}</span>
      </div>`).join("")
    : '<p class="subtitle">Pas encore de données.</p>';
}

load();
