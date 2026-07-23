/* BIC container prefixes — 139 entrées extraites de containertracking.net
   Lookup par préfixe 4 lettres → compagnie, pays, type (Owner/Leasing).
   Source : https://containertracking.net/fr/index.html#directory          */

const BIC_PREFIXES = {
  "AKLU": { company: "Akkon Lines",               country: "Turkey",       type: "Owner"   },
  "AMCU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "ANNU": { company: "CMA CGM (ANL)",             country: "Australia",    type: "Owner"   },
  "APHU": { company: "CMA CGM (APL)",             country: "Singapore",    type: "Owner"   },
  "APLU": { company: "CMA CGM (APL)",             country: "Singapore",    type: "Owner"   },
  "APZU": { company: "CMA CGM (APL)",             country: "Singapore",    type: "Owner"   },
  "ARKU": { company: "Arkas Line",                country: "Turkey",       type: "Owner"   },
  "BEAU": { company: "Beacon Intermodal",         country: "USA",          type: "Leasing" },
  "BMOU": { company: "Beacon Intermodal",         country: "USA",          type: "Leasing" },
  "BURU": { company: "Borchard Lines",            country: "UK",           type: "Owner"   },
  "CAGU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "CAIU": { company: "CAI International",         country: "USA",          type: "Leasing" },
  "CAXU": { company: "CAI International",         country: "USA",          type: "Leasing" },
  "CBHU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "CCLU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "CCRU": { company: "C&C Container",             country: "China",        type: "Leasing" },
  "CCTU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "CGHU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "CGMU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "CHSU": { company: "China United Lines",        country: "China",        type: "Owner"   },
  "CMAU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "CNNU": { company: "Swire Shipping",            country: "Hong Kong",    type: "Owner"   },
  "COSU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "CRSU": { company: "Cronos Containers",         country: "UK",           type: "Leasing" },
  "CRXU": { company: "China Railway CRRC",        country: "China",        type: "Leasing" },
  "CSLU": { company: "COSCO (CSCL)",              country: "China",        type: "Owner"   },
  "CSNU": { company: "COSCO (CSCL)",              country: "China",        type: "Owner"   },
  "CSQU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "CXDU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "CXRU": { company: "COSCO",                     country: "China",        type: "Owner"   },
  "DAYU": { company: "Hapag-Lloyd",               country: "Germany",      type: "Owner"   },
  "DFSU": { company: "Dong Fang Container",       country: "China",        type: "Leasing" },
  "DNAU": { company: "CMA CGM (Delmas)",          country: "France",       type: "Owner"   },
  "DTEU": { company: "Dong Fang Container",       country: "China",        type: "Leasing" },
  "ECMU": { company: "CMA CGM",                   country: "France",       type: "Owner"   },
  "EGHU": { company: "Evergreen",                 country: "Taiwan",       type: "Owner"   },
  "EGSU": { company: "Evergreen",                 country: "Taiwan",       type: "Owner"   },
  "EISU": { company: "Evergreen",                 country: "Taiwan",       type: "Owner"   },
  "EITU": { company: "Evergreen",                 country: "Taiwan",       type: "Owner"   },
  "EMCU": { company: "Evergreen",                 country: "Taiwan",       type: "Owner"   },
  "FANU": { company: "Fesco",                     country: "Russia",       type: "Owner"   },
  "FCIU": { company: "Florens Container",         country: "Hong Kong",    type: "Leasing" },
  "FESU": { company: "Fesco Transport",           country: "Russia",       type: "Owner"   },
  "FFAU": { company: "Florens Container",         country: "Hong Kong",    type: "Leasing" },
  "FLOU": { company: "Florens Container",         country: "Hong Kong",    type: "Leasing" },
  "FSCU": { company: "Florens Container",         country: "Hong Kong",    type: "Leasing" },
  "GATU": { company: "GATX",                      country: "USA",          type: "Leasing" },
  "GESU": { company: "GE SeaCo",                  country: "UK",           type: "Leasing" },
  "GMCU": { company: "Grimaldi Lines",            country: "Italy",        type: "Owner"   },
  "HAEU": { company: "Heung-A Shipping",          country: "South Korea",  type: "Owner"   },
  "HALU": { company: "Heung-A Shipping",          country: "South Korea",  type: "Owner"   },
  "HASU": { company: "Maersk (Hamburg Sud)",      country: "Germany",      type: "Owner"   },
  "HDMU": { company: "HMM",                       country: "South Korea",  type: "Owner"   },
  "HJCU": { company: "Hanjin (Legacy)",           country: "South Korea",  type: "Owner"   },
  "HJSU": { company: "Haijing Shipping",          country: "China",        type: "Owner"   },
  "HLBU": { company: "Hapag-Lloyd",               country: "Germany",      type: "Owner"   },
  "HLCU": { company: "Hapag-Lloyd",               country: "Germany",      type: "Owner"   },
  "HLXU": { company: "Hapag-Lloyd",               country: "Germany",      type: "Owner"   },
  "HMCU": { company: "HMM",                       country: "South Korea",  type: "Owner"   },
  "HMMU": { company: "HMM",                       country: "South Korea",  type: "Owner"   },
  "IAAU": { company: "Interasia Lines",           country: "Thailand",     type: "Owner"   },
  "INBU": { company: "Independent Container Line",country: "UK",           type: "Owner"   },
  "IPXU": { company: "Interasia Lines",           country: "Thailand",     type: "Owner"   },
  "IRSU": { company: "IRISL Group",               country: "Iran",         type: "Owner"   },
  "KKFU": { company: "ONE (K-Line)",              country: "Japan",        type: "Owner"   },
  "KMCU": { company: "KMTC",                      country: "South Korea",  type: "Owner"   },
  "KMTU": { company: "KMTC",                      country: "South Korea",  type: "Owner"   },
  "LSCU": { company: "Log-In Logistica",          country: "Brazil",       type: "Owner"   },
  "MAEU": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "MANU": { company: "Matson",                    country: "USA",          type: "Owner"   },
  "MATU": { company: "Matson",                    country: "USA",          type: "Owner"   },
  "MEDU": { company: "MSC",                       country: "Switzerland",  type: "Owner"   },
  "MOAU": { company: "ONE (MOL)",                 country: "Japan",        type: "Owner"   },
  "MOLU": { company: "ONE (MOL)",                 country: "Japan",        type: "Owner"   },
  "MRKU": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "MRSV": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "MSCU": { company: "MSC",                       country: "Switzerland",  type: "Owner"   },
  "MSDU": { company: "MSC",                       country: "Switzerland",  type: "Owner"   },
  "MSKU": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "MSNU": { company: "MSC",                       country: "Switzerland",  type: "Owner"   },
  "MSWU": { company: "MSC",                       country: "Switzerland",  type: "Owner"   },
  "MVIU": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "MWCU": { company: "MCC Transport (Maersk)",    country: "Singapore",    type: "Owner"   },
  "NSLU": { company: "Bahri (NSCSA)",             country: "Saudi Arabia", type: "Owner"   },
  "NYKU": { company: "ONE (NYK)",                 country: "Japan",        type: "Owner"   },
  "NYSU": { company: "Namsung Shipping",          country: "South Korea",  type: "Owner"   },
  "ONEU": { company: "ONE",                       country: "Singapore",    type: "Owner"   },
  "ONEY": { company: "ONE",                       country: "Singapore",    type: "Owner"   },
  "OOCU": { company: "OOCL",                      country: "Hong Kong",    type: "Owner"   },
  "OOLU": { company: "OOCL",                      country: "Hong Kong",    type: "Owner"   },
  "PALU": { company: "PIL",                       country: "Singapore",    type: "Owner"   },
  "PCIU": { company: "PIL",                       country: "Singapore",    type: "Owner"   },
  "PFCU": { company: "Pacific Forum Line",        country: "New Zealand",  type: "Owner"   },
  "PILU": { company: "PIL",                       country: "Singapore",    type: "Owner"   },
  "PONU": { company: "Maersk",                    country: "Denmark",      type: "Owner"   },
  "PRKU": { company: "Perkins Shipping",          country: "Australia",    type: "Owner"   },
  "REGU": { company: "Regional Container Lines",  country: "Thailand",     type: "Owner"   },
  "SAFU": { company: "Safmarine (Maersk)",        country: "South Africa", type: "Owner"   },
  "SCMU": { company: "SeaCastle",                 country: "USA",          type: "Leasing" },
  "SCZU": { company: "SeaCube Container",         country: "USA",          type: "Leasing" },
  "SEAU": { company: "Maersk (Sealand)",          country: "Denmark",      type: "Owner"   },
  "SEGU": { company: "SeaCastle",                 country: "USA",          type: "Leasing" },
  "SIKU": { company: "Sinokor",                   country: "South Korea",  type: "Owner"   },
  "SITU": { company: "SITC",                      country: "China",        type: "Owner"   },
  "SKLU": { company: "Sinokor",                   country: "South Korea",  type: "Owner"   },
  "SMLM": { company: "SM Line",                   country: "South Korea",  type: "Owner"   },
  "SMLU": { company: "SM Line",                   country: "South Korea",  type: "Owner"   },
  "SNBU": { company: "SeaCastle",                 country: "USA",          type: "Leasing" },
  "SRXU": { company: "SeaCube Container",         country: "USA",          type: "Leasing" },
  "STCU": { company: "SITC",                      country: "China",        type: "Owner"   },
  "SUDU": { company: "Maersk (Hamburg Sud)",      country: "Germany",      type: "Owner"   },
  "SWGU": { company: "Swire Shipping",            country: "Hong Kong",    type: "Owner"   },
  "TCLU": { company: "Triton Container",          country: "Bermuda",      type: "Leasing" },
  "TEMU": { company: "Textainer",                 country: "Bermuda",      type: "Leasing" },
  "TEXU": { company: "Textainer",                 country: "Bermuda",      type: "Leasing" },
  "TGCU": { company: "Tarros Group",              country: "Italy",        type: "Owner"   },
  "TGHU": { company: "Triton Container",          country: "Bermuda",      type: "Leasing" },
  "TLLU": { company: "ONE (MOL)",                 country: "Japan",        type: "Owner"   },
  "TRHU": { company: "Triton Container",          country: "Bermuda",      type: "Leasing" },
  "TRIU": { company: "Triton Container",          country: "Bermuda",      type: "Leasing" },
  "TSLU": { company: "TS Lines",                  country: "Taiwan",       type: "Owner"   },
  "TSSU": { company: "TS Lines",                  country: "Taiwan",       type: "Owner"   },
  "TTAU": { company: "Textainer",                 country: "Bermuda",      type: "Leasing" },
  "TTNU": { company: "Triton Container",          country: "Bermuda",      type: "Leasing" },
  "UACU": { company: "Hapag-Lloyd (UASC)",        country: "UAE",          type: "Owner"   },
  "UESU": { company: "UES International",         country: "Germany",      type: "Leasing" },
  "UETU": { company: "Unifeeder",                 country: "Denmark",      type: "Owner"   },
  "UFCU": { company: "Unifeeder",                 country: "Denmark",      type: "Owner"   },
  "WFHU": { company: "Wan Hai",                   country: "Taiwan",       type: "Owner"   },
  "WHLU": { company: "Wan Hai",                   country: "Taiwan",       type: "Owner"   },
  "WHSU": { company: "Wan Hai",                   country: "Taiwan",       type: "Owner"   },
  "XINU": { company: "X-Press Feeders",           country: "Singapore",    type: "Owner"   },
  "XPFU": { company: "X-Press Feeders",           country: "Singapore",    type: "Owner"   },
  "YMJU": { company: "Yang Ming",                 country: "Taiwan",       type: "Owner"   },
  "YMLU": { company: "Yang Ming",                 country: "Taiwan",       type: "Owner"   },
  "YMMU": { company: "Yang Ming",                 country: "Taiwan",       type: "Owner"   },
  "ZCSU": { company: "ZIM",                       country: "Israel",       type: "Owner"   },
  "ZIMU": { company: "ZIM",                       country: "Israel",       type: "Owner"   },
  "ZSTU": { company: "ZIM",                       country: "Israel",       type: "Owner"   },
};

/* Retourne les infos d'un BIC (lookup sur les 4 premières lettres). */
function lookupBIC(bic) {
  if (!bic || bic.length < 4) return null;
  return BIC_PREFIXES[bic.substring(0, 4).toUpperCase()] || null;
}

/* URL de tracking complet sur containertracking.net */
function trackURL(bic) {
  if (!bic) return null;
  const prefix = bic.substring(0, 4).toLowerCase();
  return `https://containertracking.net/fr/track/${prefix}.html`;
}

/* Rendu HTML compact : badge compagnie + lien tracker */
function bicInfoHTML(bic) {
  const info = lookupBIC(bic);
  if (!info) return "";
  const url  = trackURL(bic);
  const typeClass = info.type === "Leasing" ? "badge-info" : "badge-ok";
  return `
    <div class="bic-meta">
      <span class="bic-company">${esc(info.company)}</span>
      <span class="bic-country">${esc(info.country)}</span>
      <span class="badge ${typeClass} bic-type">${info.type}</span>
      <a href="${url}" target="_blank" rel="noopener noreferrer" class="track-link" title="Tracker ce conteneur">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        Tracker
      </a>
    </div>`;
}
