/*
 * Terminmarktplatz – Google Analytics NUR nach Einwilligung (§ 25 TDDDG, Art. 6 Abs. 1 lit. a DSGVO)
 * - Lädt GA4 erst, wenn im Cookie-Banner bzw. in den Cookie-Einstellungen zugestimmt wurde
 *   (localStorage "tm_cookie_consent_v8" === "accepted").
 * - Ohne Zustimmung wird keinerlei Verbindung zu Google aufgebaut.
 */
(function () {
  "use strict";
  var CONSENT_KEY = "tm_cookie_consent_v8";
  var GA_ID = "G-508763756";

  function hasConsent() {
    try { return localStorage.getItem(CONSENT_KEY) === "accepted"; } catch (e) { return false; }
  }

  function load() {
    if (window.__tmGaLoaded) return;
    if (document.querySelector('script[src*="googletagmanager.com/gtag/js"]')) { window.__tmGaLoaded = true; return; }
    window.__tmGaLoaded = true;
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_ID;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID);
  }

  window.tmLoadAnalyticsIfConsented = function () { if (hasConsent()) load(); };

  if (hasConsent()) { load(); return; }

  // Zustimmung im Banner ("Akzeptieren") oder in den Cookie-Einstellungen ("Speichern")
  document.addEventListener("click", function onClick(ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (t.closest("#cookie-accept") || t.closest("#save-cookies")) {
      setTimeout(function () {
        if (hasConsent()) { document.removeEventListener("click", onClick); load(); }
      }, 150);
    }
  });
})();
