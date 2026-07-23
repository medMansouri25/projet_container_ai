/* history.js — onglets Scans BIC + Dossiers de passage + recherche/filtre */

const errorAlert = document.getElementById("error-alert");

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function fmtDate(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  return dt.toLocaleDateString("fr-FR") + " " +
         dt.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function normalize(s) {
  return (s || "").toLowerCase().replace(/\s+/g, "");
}

/* ── Onglets ── */
const tabs = {
  scans:    { btn: document.getElementById("btn-scans"),    panel: document.getElementById("tab-scans") },
  dossiers: { btn: document.getElementById("btn-dossiers"), panel: document.getElementById("tab-dossiers") },
};

function switchTab(name) {
  Object.entries(tabs).forEach(([k, { btn, panel }]) => {
    const active = k === name;
    btn.setAttribute("aria-selected", String(active));
    panel.hidden = !active;
  });
}

document.getElementById("btn-scans").addEventListener("click",    () => switchTab("scans"));
document.getElementById("btn-dossiers").addEventListener("click", () => switchTab("dossiers"));

/* ══════════════════════════════════════
   SCANS BIC
   ══════════════════════════════════════ */
let allScans = [];

async function loadScans() {
  try {
    const r = await fetch(`${await apiBase()}/api/history`);
    const data = await r.json();
    allScans = data.scans || [];
    applyFilterScans();
    wireEditDelete();
  } catch (err) {
    errorAlert.textContent = "Chargement impossible : " + err.message;
    errorAlert.hidden = false;
  }
}

function applyFilterScans() {
  const q = normalize(document.getElementById("search-scans").value);
  const filtered = q ? allScans.filter(s => {
    const info = lookupBIC(s.bic);
    return normalize(s.bic).includes(q) ||
           (info && normalize(info.company).includes(q)) ||
           (info && normalize(info.country).includes(q));
  }) : allScans;

  document.getElementById("badge-scans").textContent = allScans.length;
  document.getElementById("clear-scans").hidden = !q;

  const countEl = document.getElementById("count-scans");
  countEl.textContent = q ? `${filtered.length} / ${allScans.length} résultat(s)` : "";

  const emptyEl    = document.getElementById("empty-scans");
  const noResultEl = document.getElementById("no-result-scans");
  const table      = document.getElementById("table-scans");

  if (!allScans.length) {
    emptyEl.hidden = false; noResultEl.hidden = true; table.hidden = true; return;
  }
  emptyEl.hidden = true;
  if (!filtered.length) {
    noResultEl.hidden = false; table.hidden = true; return;
  }
  noResultEl.hidden = true;
  table.hidden = false;
  renderScanRows(filtered);
}

function renderScanRows(scans) {
  document.getElementById("tbody-scans").innerHTML = scans.map(s => `
    <tr id="row-${s.id}">
      <td>${s.image_url ? `<img class="thumb" src="${esc(s.image_url)}" alt="scan">` : "—"}</td>
      <td>
        <div class="edit-form">
          <input class="bic-input" id="bic-${s.id}" value="${esc(s.bic)}" maxlength="11" readonly>
          <button type="button" class="btn btn-small btn-save" id="save-${s.id}" hidden>
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            Enregistrer
          </button>
        </div>
        ${bicInfoHTML(s.bic)}
      </td>
      <td>${s.valid
        ? '<span class="badge badge-ok">valide</span>'
        : '<span class="badge badge-warn">à vérifier</span>'}</td>
      <td>${fmtDate(s.created_at)}</td>
      <td class="actions">
        <button type="button" class="btn btn-small btn-secondary" data-edit="${s.id}" title="Modifier">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
        </button>
        <button type="button" class="btn btn-small btn-danger" data-delete="${s.id}" data-bic="${esc(s.bic)}" title="Supprimer">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    </tr>`).join("");
  wireEditDelete();
}

function wireEditDelete() {
  document.getElementById("tbody-scans").querySelectorAll("[data-edit]").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.edit;
      const input = document.getElementById(`bic-${id}`);
      input.readOnly = false;
      input.classList.add("editing");
      input.focus();
      document.getElementById(`save-${id}`).hidden = false;
    });
  });
  document.getElementById("tbody-scans").querySelectorAll(".btn-save").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.id.replace("save-", "");
      const bic = document.getElementById(`bic-${id}`).value;
      await fetch(`${await apiBase()}/api/scans/${id}/update`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bic }),
      });
      window.location.reload();
    });
  });
  document.getElementById("tbody-scans").querySelectorAll("[data-delete]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Supprimer le scan ${btn.dataset.bic} ?`)) return;
      await fetch(`${await apiBase()}/api/scans/${btn.dataset.delete}/delete`, { method: "POST" });
      window.location.reload();
    });
  });
}

/* Recherche scans */
const searchScans = document.getElementById("search-scans");
searchScans.addEventListener("input", applyFilterScans);
document.getElementById("clear-scans").addEventListener("click", () => {
  searchScans.value = "";
  applyFilterScans();
  searchScans.focus();
});

/* ══════════════════════════════════════
   DOSSIERS DE PASSAGE
   ══════════════════════════════════════ */
let allDossiers  = [];
let activeField  = "all"; // "all" | "bic" | "immat"

const STATUT_BADGE = {
  en_attente: '<span class="badge badge-warn">En attente</span>',
  valide:     '<span class="badge badge-ok">Validé</span>',
  abandonne:  '<span class="badge badge-info">Abandonné</span>',
};

async function loadDossiers() {
  try {
    const r = await fetch(`${await apiBase()}/api/dossiers?include_entities=1`);
    const data = await r.json();
    allDossiers = data.dossiers || [];
    applyFilterDossiers();
  } catch (err) {
    errorAlert.textContent = "Chargement dossiers impossible : " + err.message;
    errorAlert.hidden = false;
  }
}

function applyFilterDossiers() {
  const q = normalize(document.getElementById("search-dossiers").value);

  const filtered = q ? allDossiers.filter(d => {
    const info    = lookupBIC(d.code_iso);
    const inBic   = normalize(d.code_iso).includes(q) ||
                    (info && normalize(info.company).includes(q)) ||
                    (info && normalize(info.country).includes(q));
    const inImmat = normalize(d.immatriculation).includes(q);
    if (activeField === "bic")   return inBic;
    if (activeField === "immat") return inImmat;
    return inBic || inImmat;
  }) : allDossiers;

  document.getElementById("badge-dossiers").textContent = allDossiers.length;
  document.getElementById("clear-dossiers").hidden = !q;

  const countEl = document.getElementById("count-dossiers");
  countEl.textContent = q ? `${filtered.length} / ${allDossiers.length} résultat(s)` : "";

  const emptyEl    = document.getElementById("empty-dossiers");
  const noResultEl = document.getElementById("no-result-dossiers");
  const table      = document.getElementById("table-dossiers");

  if (!allDossiers.length) {
    emptyEl.hidden = false; noResultEl.hidden = true; table.hidden = true; return;
  }
  emptyEl.hidden = true;
  if (!filtered.length) {
    noResultEl.hidden = false; table.hidden = true; return;
  }
  noResultEl.hidden = true;
  table.hidden = false;
  renderDossierRows(filtered);
}

function renderDossierRows(dossiers) {
  document.getElementById("tbody-dossiers").innerHTML = dossiers.map(d => {
    const bic   = d.code_iso
      ? `<code class="bic">${esc(d.code_iso)}</code>${bicInfoHTML(d.code_iso)}`
      : '<span class="muted">—</span>';
    const immat = d.immatriculation
      ? `<code dir="ltr" style="unicode-bidi:bidi-override">${esc(d.immatriculation)}</code>`
      : '<span class="muted">—</span>';
    const completerBtn = d.statut === "en_attente"
      ? `<a href="capture.html?dossier_id=${d.id}" class="btn btn-small btn-primary" title="Compléter ce dossier">
           <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
           Compléter
         </a>`
      : "";
    return `
    <tr>
      <td><code>#${d.id}</code></td>
      <td>${STATUT_BADGE[d.statut] || esc(d.statut)}</td>
      <td>${bic}</td>
      <td>${immat}</td>
      <td>${fmtDate(d.created_at)}</td>
      <td class="actions">${completerBtn}</td>
    </tr>`;
  }).join("");
}

/* Recherche dossiers */
const searchDossiers = document.getElementById("search-dossiers");
searchDossiers.addEventListener("input", applyFilterDossiers);
document.getElementById("clear-dossiers").addEventListener("click", () => {
  searchDossiers.value = "";
  applyFilterDossiers();
  searchDossiers.focus();
});

/* Pills de filtre */
document.querySelectorAll(".filter-pills .pill").forEach(pill => {
  pill.addEventListener("click", () => {
    document.querySelectorAll(".filter-pills .pill").forEach(p => p.classList.remove("pill-active"));
    pill.classList.add("pill-active");
    activeField = pill.dataset.field;
    applyFilterDossiers();
  });
});

/* ── Init ── */
const urlTab = new URLSearchParams(window.location.search).get("tab");
if (urlTab === "dossiers") switchTab("dossiers");

loadScans();
loadDossiers();
