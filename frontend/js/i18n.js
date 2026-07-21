/* i18n.js — internationalisation fr / ar (avec RTL pour l'arabe).
   Module ESM : expose t()/dirFor() (purs, testables node) et, dans le
   navigateur, applique la langue au DOM + branche le sélecteur.
   Les éléments traduisibles portent data-i18n="clé" (textContent),
   data-i18n-html="clé" (innerHTML) ou data-i18n-ph="clé" (placeholder). */

export const LANGS = ["fr", "ar"];
const RTL = new Set(["ar"]);

export const DICT = {
  fr: {
    "brand": "SmartContainer AI",
    "nav.scan": "Scanner BIC", "nav.capture": "Capture passage",
    "nav.history": "Historique", "nav.dashboard": "Dashboard",

    "cap.title": "Scanner un passage",
    "cap.subtitle": "Détecte le <b>conteneur</b> (code ISO) ou la <b>plaque</b> — depuis une image, une vidéo, ou en direct à la caméra.",
    "cap.step1": "1. Que veux-tu détecter ?",
    "cap.entity.conteneur": "Conteneur (code ISO)",
    "cap.entity.plaque": "Plaque (immatriculation)",
    "cap.step2": "2. Comment ?",
    "cap.import.t": "Importer un fichier",
    "cap.import.d": "une image ou une vidéo depuis l'appareil",
    "cap.realtime.t": "Détection temps réel",
    "cap.realtime.d": "caméra en direct + repère de cadrage",
    "cap.framing": "État du cadrage :",
    "cap.capture": "Capturer cette image",
    "cap.stop": "Arrêter",
    "cap.result.title": "Proposition (à valider)",
    "cap.confirm": "Confirmer", "cap.again": "Recommencer",
    "guide.aucun": "aucun objet", "guide.trop_loin": "trop loin — approchez",
    "guide.bon": "bon cadrage ✓", "guide.trop_pres": "trop près — reculez",
    "badge.valid": "Forme valide", "badge.check": "À vérifier", "badge.recalc": "Recalculé",

    "scan.title": "Scanner un conteneur",
    "scan.subtitle": "Détection du code BIC (ISO 6346) — importez une image ou utilisez la caméra.",
    "scan.drop": "Glissez une image ici", "scan.or": "ou",
    "scan.pick": "Choisir un fichier", "scan.camera": "Ouvrir la caméra",

    "history.title": "Historique des scans",
    "dashboard.title": "Tableau de bord",
  },
  ar: {
    "brand": "SmartContainer AI",
    "nav.scan": "ماسح BIC", "nav.capture": "مسح العبور",
    "nav.history": "السجل", "nav.dashboard": "لوحة القيادة",

    "cap.title": "مسح عملية عبور",
    "cap.subtitle": "يكشف <b>الحاوية</b> (رمز ISO) أو <b>اللوحة</b> — من صورة أو فيديو أو مباشرة عبر الكاميرا.",
    "cap.step1": "١. ماذا تريد أن تكشف؟",
    "cap.entity.conteneur": "حاوية (رمز ISO)",
    "cap.entity.plaque": "لوحة الترقيم",
    "cap.step2": "٢. كيف؟",
    "cap.import.t": "استيراد ملف",
    "cap.import.d": "صورة أو فيديو من الجهاز",
    "cap.realtime.t": "كشف في الوقت الحقيقي",
    "cap.realtime.d": "كاميرا مباشرة + مؤشر التأطير",
    "cap.framing": "حالة التأطير:",
    "cap.capture": "التقاط هذه الصورة",
    "cap.stop": "إيقاف",
    "cap.result.title": "اقتراح (للتحقق)",
    "cap.confirm": "تأكيد", "cap.again": "إعادة",
    "guide.aucun": "لا يوجد كائن", "guide.trop_loin": "بعيد جدًا — اقترب",
    "guide.bon": "تأطير جيد ✓", "guide.trop_pres": "قريب جدًا — تراجع",
    "badge.valid": "شكل صالح", "badge.check": "للتحقق", "badge.recalc": "أُعيد حسابه",

    "scan.title": "مسح حاوية",
    "scan.subtitle": "كشف رمز BIC (ISO 6346) — استورد صورة أو استخدم الكاميرا.",
    "scan.drop": "أفلت صورة هنا", "scan.or": "أو",
    "scan.pick": "اختر ملفًا", "scan.camera": "فتح الكاميرا",

    "history.title": "سجل عمليات المسح",
    "dashboard.title": "لوحة القيادة",
  },
};

const DEFAULT = "fr";

/* Traduction pure : renvoie la chaîne pour (clé, langue), avec repli sur le
   français puis sur la clé elle-même. */
export function t(key, lang = DEFAULT) {
  return (DICT[lang] && DICT[lang][key]) || DICT[DEFAULT][key] || key;
}

/* Sens d'écriture d'une langue : 'rtl' pour l'arabe, 'ltr' sinon. */
export function dirFor(lang) {
  return RTL.has(lang) ? "rtl" : "ltr";
}

/* ── DOM (navigateur uniquement) ── */
function applyLang(lang) {
  if (!LANGS.includes(lang)) lang = DEFAULT;
  const root = document.documentElement;
  root.lang = lang;
  root.dir = dirFor(lang);
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n, lang); });
  document.querySelectorAll("[data-i18n-html]").forEach((e) => { e.innerHTML = t(e.dataset.i18nHtml, lang); });
  document.querySelectorAll("[data-i18n-ph]").forEach((e) => { e.placeholder = t(e.dataset.i18nPh, lang); });
  try { localStorage.setItem("lang", lang); } catch (_) {}
  window.__LANG__ = lang;
  const sel = document.getElementById("lang-select");
  if (sel) sel.value = lang;
}

function initLang() {
  let lang = DEFAULT;
  try { lang = localStorage.getItem("lang") || DEFAULT; } catch (_) {}
  const sel = document.getElementById("lang-select");
  if (sel) sel.addEventListener("change", () => applyLang(sel.value));
  applyLang(lang);
}

if (typeof document !== "undefined") {
  // expose pour les scripts classiques (app.js) et les modules (capture.js)
  window.i18n = { t: (k) => t(k, window.__LANG__ || DEFAULT), applyLang, dirFor };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initLang);
  else initLang();
}
