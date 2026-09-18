// status.js — état de connexion partagé (🟢/🟡/🔴/⚠️), un seul format
// pour tous les écrans de l'extension.

const LABELS = {
  disconnected: "Déconnectée",
  connecting: "Connexion…",
  connected: "Connectée",
  error: "Erreur",
};

export function setStatus(dotEl, textEl, state, message) {
  dotEl.dataset.state = state;
  textEl.textContent = message || LABELS[state] || state;
}
