// service-worker.js — arrière-plan MV3.
// Pour l'instant : rien de persistant (l'état de session RTSP vit dans
// popup.js, remis à zéro à chaque ouverture). À enrichir si un futur
// enregistrement long doit survivre à la fermeture de la popup — ce
// service worker garderait alors le session_id et l'état d'enregistrement
// dans chrome.storage.session plutôt que dans la mémoire de la popup.

chrome.runtime.onInstalled.addListener(() => {
  console.log("[BIC Detector] extension installée");
});
