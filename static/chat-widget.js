/*
 * Terminmarktplatz – KI-Chat-Assistent (Claude)
 * - Lädt erst nach Cookie-Consent (tm_cookie_consent_v8 = "accepted")
 * - Speichert keine personenbezogenen Daten serverseitig
 * - Max. 10 Nachrichten pro Session (localStorage)
 */
(function () {
  "use strict";

  var CONSENT_KEY = "tm_cookie_consent_v8";
  var HISTORY_KEY = "tm_chat_history_v1";
  var MAX_MESSAGES = 10; // gesamt (Nutzer + Assistent) pro Session
  var API_URL = "/api/chat";

  // Mehrfach-Initialisierung verhindern
  if (window.__tmChatWidgetLoaded) return;
  window.__tmChatWidgetLoaded = true;

  /* ---------- Consent-Gating ---------- */
  function hasConsent() {
    try {
      return localStorage.getItem(CONSENT_KEY) === "accepted";
    } catch (e) {
      return false;
    }
  }

  function waitForConsent() {
    if (hasConsent()) {
      init();
      return;
    }
    // Auf Klick des Accept-Buttons im Cookie-Banner reagieren
    document.addEventListener("click", function onClick(ev) {
      var t = ev.target;
      if (t && (t.id === "cookie-accept" || (t.closest && t.closest("#cookie-accept")))) {
        // kurz warten, bis der Consent-Status geschrieben wurde
        setTimeout(function () {
          if (hasConsent()) {
            document.removeEventListener("click", onClick);
            init();
          }
        }, 150);
      }
    });
  }

  /* ---------- History (localStorage) ---------- */
  function loadHistory() {
    try {
      var raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  function saveHistory(history) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_MESSAGES)));
    } catch (e) {
      /* Speicher voll o. deaktiviert – ignorieren */
    }
  }

  /* ---------- Styles ---------- */
  function injectStyles() {
    if (document.getElementById("tm-chat-styles")) return;
    var css = "" +
      ".tm-chat-btn{position:fixed;right:20px;bottom:20px;z-index:99998;display:inline-flex;align-items:center;gap:8px;" +
      "padding:12px 18px;border:none;border-radius:999px;cursor:pointer;font:600 15px/1 Inter,system-ui,sans-serif;" +
      "color:#fff;background:linear-gradient(135deg,#6f53ff,#4b2fd6);box-shadow:0 8px 24px rgba(79,47,214,.35);transition:transform .15s ease,box-shadow .15s ease;}" +
      ".tm-chat-btn:hover{transform:translateY(-2px);box-shadow:0 12px 30px rgba(79,47,214,.45);}" +
      ".tm-chat-btn svg{width:20px;height:20px;flex:0 0 auto;}" +
      ".tm-chat-btn.tm-hidden{display:none;}" +
      ".tm-chat-panel{position:fixed;right:20px;bottom:20px;z-index:99999;width:360px;max-width:calc(100vw - 32px);" +
      "height:520px;max-height:calc(100vh - 40px);display:none;flex-direction:column;overflow:hidden;border-radius:18px;" +
      "background:#14121f;color:#f2f0ff;box-shadow:0 20px 60px rgba(10,6,30,.55);border:1px solid rgba(122,92,255,.25);}" +
      ".tm-chat-panel.tm-open{display:flex;}" +
      ".tm-chat-head{display:flex;align-items:center;gap:10px;padding:14px 16px;background:linear-gradient(135deg,#6f53ff,#4b2fd6);}" +
      ".tm-chat-head .tm-dot{width:9px;height:9px;border-radius:50%;background:#48e6a0;box-shadow:0 0 0 3px rgba(72,230,160,.25);}" +
      ".tm-chat-head h3{margin:0;font:700 15px/1.2 Inter,system-ui,sans-serif;color:#fff;flex:1;}" +
      ".tm-chat-head .tm-sub{display:block;font:400 11px/1.3 Inter,system-ui,sans-serif;color:rgba(255,255,255,.8);margin-top:2px;}" +
      ".tm-chat-close{background:transparent;border:none;color:#fff;cursor:pointer;font-size:22px;line-height:1;padding:2px 6px;border-radius:8px;}" +
      ".tm-chat-close:hover{background:rgba(255,255,255,.15);}" +
      ".tm-chat-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;background:#14121f;}" +
      ".tm-msg{max-width:82%;padding:10px 13px;border-radius:14px;font:400 14px/1.45 Inter,system-ui,sans-serif;white-space:pre-wrap;word-wrap:break-word;}" +
      ".tm-msg.tm-user{align-self:flex-end;background:#6f53ff;color:#fff;border-bottom-right-radius:4px;}" +
      ".tm-msg.tm-bot{align-self:flex-start;background:#241f38;color:#ece9ff;border-bottom-left-radius:4px;}" +
      ".tm-msg.tm-error{align-self:flex-start;background:#3a1f2a;color:#ffd7e0;}" +
      ".tm-typing{align-self:flex-start;display:inline-flex;gap:4px;padding:12px 14px;background:#241f38;border-radius:14px;}" +
      ".tm-typing span{width:7px;height:7px;border-radius:50%;background:#9b86ff;opacity:.5;animation:tmBlink 1.2s infinite;}" +
      ".tm-typing span:nth-child(2){animation-delay:.2s;}.tm-typing span:nth-child(3){animation-delay:.4s;}" +
      "@keyframes tmBlink{0%,60%,100%{opacity:.3;}30%{opacity:1;}}" +
      ".tm-chat-foot{padding:10px 12px;border-top:1px solid rgba(122,92,255,.18);background:#14121f;}" +
      ".tm-chat-note{font:400 10.5px/1.3 Inter,system-ui,sans-serif;color:#8f88ad;text-align:center;margin:0 0 8px;}" +
      ".tm-chat-inputrow{display:flex;gap:8px;align-items:flex-end;}" +
      ".tm-chat-input{flex:1;resize:none;max-height:96px;min-height:40px;padding:10px 12px;border-radius:12px;border:1px solid rgba(122,92,255,.3);" +
      "background:#1d1830;color:#f2f0ff;font:400 14px/1.4 Inter,system-ui,sans-serif;outline:none;}" +
      ".tm-chat-input:focus{border-color:#6f53ff;}" +
      ".tm-chat-input:disabled{opacity:.5;}" +
      ".tm-chat-send{flex:0 0 auto;width:42px;height:42px;border:none;border-radius:12px;cursor:pointer;background:#6f53ff;color:#fff;display:inline-flex;align-items:center;justify-content:center;}" +
      ".tm-chat-send:hover{background:#5a40e6;}.tm-chat-send:disabled{opacity:.5;cursor:not-allowed;}" +
      ".tm-chat-limit{text-align:center;font:400 12px/1.4 Inter,system-ui,sans-serif;color:#b7b0d6;}" +
      ".tm-chat-limit a{color:#9b86ff;cursor:pointer;text-decoration:underline;}" +
      "@media (max-width:480px){.tm-chat-panel{right:8px;bottom:8px;width:calc(100vw - 16px);height:calc(100vh - 16px);max-height:none;}}";
    var style = document.createElement("style");
    style.id = "tm-chat-styles";
    style.textContent = css;
    document.head.appendChild(style);
  }

  /* ---------- UI aufbauen ---------- */
  var els = {};

  function buildUI() {
    var btn = document.createElement("button");
    btn.className = "tm-chat-btn";
    btn.type = "button";
    btn.setAttribute("aria-label", "Chat öffnen");
    btn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.5 8.5 8.5 0 0 1-3.8-.9L3 21l1.9-5.7A8.5 8.5 0 1 1 21 11.5z"/></svg>' +
      "<span>Chat öffnen</span>";

    var panel = document.createElement("div");
    panel.className = "tm-chat-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "KI-Assistent von Terminmarktplatz");
    panel.innerHTML =
      '<div class="tm-chat-head">' +
      '<span class="tm-dot" aria-hidden="true"></span>' +
      '<h3>KI-Assistent<span class="tm-sub">Terminmarktplatz.de</span></h3>' +
      '<button class="tm-chat-close" type="button" aria-label="Chat schließen">&times;</button>' +
      "</div>" +
      '<div class="tm-chat-body" id="tm-chat-body"></div>' +
      '<div class="tm-chat-foot">' +
      '<p class="tm-chat-note">KI-Assistent · Antworten können Fehler enthalten · Daten werden nicht gespeichert</p>' +
      '<div class="tm-chat-inputrow">' +
      '<textarea class="tm-chat-input" id="tm-chat-input" rows="1" placeholder="Frag mich etwas…" aria-label="Nachricht"></textarea>' +
      '<button class="tm-chat-send" id="tm-chat-send" type="button" aria-label="Senden">' +
      '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>' +
      "</button>" +
      "</div></div>";

    document.body.appendChild(btn);
    document.body.appendChild(panel);

    els.btn = btn;
    els.panel = panel;
    els.body = panel.querySelector("#tm-chat-body");
    els.input = panel.querySelector("#tm-chat-input");
    els.send = panel.querySelector("#tm-chat-send");
    els.close = panel.querySelector(".tm-chat-close");

    btn.addEventListener("click", openPanel);
    els.close.addEventListener("click", closePanel);
    els.send.addEventListener("click", onSend);
    els.input.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        onSend();
      }
    });
    els.input.addEventListener("input", autoGrow);
  }

  function autoGrow() {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 96) + "px";
  }

  function openPanel() {
    els.panel.classList.add("tm-open");
    els.btn.classList.add("tm-hidden");
    renderHistory();
    setTimeout(function () { els.input.focus(); }, 50);
  }

  function closePanel() {
    els.panel.classList.remove("tm-open");
    els.btn.classList.remove("tm-hidden");
  }

  /* ---------- Rendering ---------- */
  function addBubble(role, text) {
    var div = document.createElement("div");
    div.className = "tm-msg " + (role === "user" ? "tm-user" : role === "error" ? "tm-error" : "tm-bot");
    div.textContent = text; // textContent verhindert HTML-Injection
    els.body.appendChild(div);
    scrollDown();
    return div;
  }

  function scrollDown() {
    els.body.scrollTop = els.body.scrollHeight;
  }

  function renderHistory() {
    els.body.innerHTML = "";
    var history = loadHistory();
    if (history.length === 0) {
      addBubble(
        "bot",
        "Hallo! Ich bin der KI-Assistent von Terminmarktplatz. Ich helfe dir, freie Termine zu finden oder als Anbieter deine Slots einzutragen. Wie kann ich helfen?"
      );
    } else {
      history.forEach(function (m) { addBubble(m.role, m.content); });
    }
    updateLimitState();
  }

  function updateLimitState() {
    var history = loadHistory();
    var limitEl = els.panel.querySelector(".tm-chat-limit");
    if (history.length >= MAX_MESSAGES) {
      els.input.disabled = true;
      els.send.disabled = true;
      els.input.placeholder = "Sitzungslimit erreicht";
      if (!limitEl) {
        limitEl = document.createElement("div");
        limitEl.className = "tm-chat-limit";
        limitEl.innerHTML = 'Das Sitzungslimit ist erreicht. <a id="tm-chat-reset">Neuen Chat starten</a>';
        els.body.appendChild(limitEl);
        limitEl.querySelector("#tm-chat-reset").addEventListener("click", resetChat);
      }
      scrollDown();
    } else {
      els.input.disabled = false;
      els.send.disabled = false;
      els.input.placeholder = "Frag mich etwas…";
      if (limitEl) limitEl.remove();
    }
  }

  function resetChat() {
    try { localStorage.removeItem(HISTORY_KEY); } catch (e) {}
    renderHistory();
    els.input.focus();
  }

  /* ---------- Senden ---------- */
  var sending = false;

  function onSend() {
    if (sending) return;
    var text = (els.input.value || "").trim();
    if (!text) return;

    var history = loadHistory();
    if (history.length >= MAX_MESSAGES) {
      updateLimitState();
      return;
    }

    // Nutzernachricht anzeigen + speichern
    addBubble("user", text);
    history.push({ role: "user", content: text.slice(0, 2000) });
    saveHistory(history);
    els.input.value = "";
    autoGrow();

    sending = true;
    els.send.disabled = true;
    var typing = showTyping();

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: loadHistory() })
    })
      .then(function (r) {
        return r.json().then(function (data) { return { ok: r.ok, data: data }; });
      })
      .then(function (res) {
        removeTyping(typing);
        if (!res.ok || !res.data || !res.data.reply) {
          var msg = (res.data && res.data.error) || "Es gab ein Problem. Bitte versuche es später erneut.";
          addBubble("error", msg);
        } else {
          var reply = res.data.reply;
          addBubble("bot", reply);
          var h = loadHistory();
          h.push({ role: "assistant", content: reply });
          saveHistory(h);
        }
      })
      .catch(function () {
        removeTyping(typing);
        addBubble("error", "Verbindung fehlgeschlagen. Bitte prüfe deine Internetverbindung.");
      })
      .finally(function () {
        sending = false;
        updateLimitState();
        if (!els.send.disabled) els.input.focus();
      });
  }

  function showTyping() {
    var t = document.createElement("div");
    t.className = "tm-typing";
    t.innerHTML = "<span></span><span></span><span></span>";
    els.body.appendChild(t);
    scrollDown();
    return t;
  }

  function removeTyping(t) {
    if (t && t.parentNode) t.parentNode.removeChild(t);
  }

  /* ---------- Init ---------- */
  function init() {
    if (window.__tmChatInit) return;
    window.__tmChatInit = true;
    injectStyles();
    buildUI();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", waitForConsent);
  } else {
    waitForConsent();
  }
})();
