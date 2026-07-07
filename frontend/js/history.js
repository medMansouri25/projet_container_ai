/* history.js — liste des scans via GET /api/history + actions modifier/supprimer */

const errorAlert = document.getElementById("error-alert");

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

async function load() {
  try {
    const r = await fetch(`${await apiBase()}/api/history`);
    const data = await r.json();
    render(data.scans || []);
  } catch (err) {
    errorAlert.textContent = "Chargement impossible : " + err.message;
    errorAlert.hidden = false;
  }
}

function render(scans) {
  if (!scans.length) {
    document.getElementById("empty").hidden = false;
    return;
  }
  document.getElementById("table").hidden = false;
  const tbody = document.getElementById("tbody");
  tbody.innerHTML = scans.map(s => {
    const date = new Date(s.created_at);
    const dateStr = date.toLocaleDateString("fr-FR") + " " +
      date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
    return `
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
      </td>
      <td>${s.valid ? '<span class="badge badge-ok">valide</span>' : '<span class="badge badge-warn">à vérifier</span>'}</td>
      <td>${s.ocr_confidence ? Math.round(s.ocr_confidence * 100) + "%" : "—"}</td>
      <td>${dateStr}</td>
      <td class="actions">
        <button type="button" class="btn btn-small btn-secondary" data-edit="${s.id}" title="Modifier le code">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>
        </button>
        <button type="button" class="btn btn-small btn-danger" data-delete="${s.id}" data-bic="${esc(s.bic)}" title="Supprimer">
          <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </td>
    </tr>`;
  }).join("");

  tbody.querySelectorAll("[data-edit]").forEach(btn => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.edit;
      const input = document.getElementById(`bic-${id}`);
      input.readOnly = false;
      input.classList.add("editing");
      input.focus();
      document.getElementById(`save-${id}`).hidden = false;
    });
  });

  tbody.querySelectorAll(".btn-save").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.id.replace("save-", "");
      const bic = document.getElementById(`bic-${id}`).value;
      await fetch(`${await apiBase()}/api/scans/${id}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bic }),
      });
      window.location.reload();
    });
  });

  tbody.querySelectorAll("[data-delete]").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Supprimer le scan ${btn.dataset.bic} ?`)) return;
      await fetch(`${await apiBase()}/api/scans/${btn.dataset.delete}/delete`, { method: "POST" });
      window.location.reload();
    });
  });
}

load();
