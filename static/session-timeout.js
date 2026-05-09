/**
 * Session-Warnung vor JWT-Ablauf + Inaktivitäts-Logout.
 * Voraussetzung: Cookies HttpOnly; Ablaufzeit über GET /auth/session.
 */
(function () {
  var POLL_MS = 60 * 1000;
  var WARN_BEFORE_MS = 15 * 60 * 1000;
  var IDLE_STANDARD_MS = 8 * 3600 * 1000;
  var IDLE_REMEMBER_MS = 30 * 24 * 3600 * 1000;

  var lastActivity = Date.now();
  var warned = false;
  var modalEl = null;

  ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach(function (ev) {
    document.addEventListener(
      ev,
      function () {
        lastActivity = Date.now();
      },
      { passive: true }
    );
  });

  function ensureModal() {
    if (modalEl) return modalEl;
    modalEl = document.createElement("div");
    modalEl.id = "tm-session-modal";
    modalEl.setAttribute("hidden", "");
    modalEl.innerHTML =
      '<div class="tm-session-modal-backdrop" style="position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:99998;display:flex;align-items:center;justify-content:center;padding:16px;">' +
      '<div role="dialog" aria-modal="true" aria-labelledby="tm-session-modal-title" style="max-width:420px;width:100%;background:#fff;border-radius:16px;padding:20px;box-shadow:0 25px 50px rgba(0,0,0,.2);color:#0f172a;">' +
      '<h2 id="tm-session-modal-title" style="margin:0 0 12px;font-size:1.15rem;">Sitzung läuft ab</h2>' +
      '<p style="margin:0 0 18px;line-height:1.45;">Deine Sitzung läuft in 15 Minuten ab. Möchtest du angemeldet bleiben?</p>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end;">' +
      '<button type="button" id="tm-session-logout" style="padding:10px 14px;border-radius:10px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;color:#0f172a;">Ausloggen</button>' +
      '<button type="button" id="tm-session-extend" style="padding:10px 14px;border-radius:10px;border:none;background:linear-gradient(135deg,#6f53ff,#38bdf8);color:#fff;cursor:pointer;font-weight:700;">Ja, angemeldet bleiben</button>' +
      "</div></div></div>";
    document.body.appendChild(modalEl);
    modalEl.querySelector("#tm-session-extend").addEventListener("click", extendSession);
    modalEl.querySelector("#tm-session-logout").addEventListener("click", doLogout);
    return modalEl;
  }

  function showModal() {
    var m = ensureModal();
    m.removeAttribute("hidden");
  }

  function hideModal() {
    var m = document.getElementById("tm-session-modal");
    if (m) m.setAttribute("hidden", "");
  }

  function redirectExpired() {
    window.location.href = "/login.html?session_expired=1";
  }

  async function extendSession() {
    try {
      var r = await fetch("/auth/refresh", { method: "POST", credentials: "include" });
      if (!r.ok) {
        redirectExpired();
        return;
      }
      warned = false;
      hideModal();
    } catch (_e) {
      redirectExpired();
    }
  }

  async function doLogout() {
    try {
      await fetch("/auth/logout", { method: "POST", credentials: "include" });
    } catch (_e) {}
    window.location.href = "/login.html?tab=login";
  }

  async function checkSession() {
    var sess;
    try {
      var r = await fetch("/auth/session", { credentials: "include" });
      sess = await r.json().catch(function () {
        return {};
      });
    } catch (_e) {
      return;
    }

    if (!sess.authenticated) return;

    var remember = !!sess.remember_me;
    var idleMs = remember ? IDLE_REMEMBER_MS : IDLE_STANDARD_MS;
    if (Date.now() - lastActivity > idleMs) {
      redirectExpired();
      return;
    }

    var expMs = (sess.session_expires_at || 0) * 1000;
    var left = expMs - Date.now();
    if (left <= 0) {
      redirectExpired();
      return;
    }
    if (left <= WARN_BEFORE_MS) {
      if (!warned) {
        warned = true;
        showModal();
      }
    } else if (left > WARN_BEFORE_MS + POLL_MS * 2) {
      warned = false;
      hideModal();
    }
  }

  setInterval(checkSession, POLL_MS);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", checkSession);
  } else {
    checkSession();
  }
})();
