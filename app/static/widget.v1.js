(function () {
  "use strict";

  // Prevent multiple initializations of the same bundle
  if (window.__FLYRANK_WIDGET_LOADED__) return;
  window.__FLYRANK_WIDGET_LOADED__ = true;

  function getScriptParams() {
    let currentScript = document.currentScript;
    if (!currentScript) {
      const scripts = document.getElementsByTagName("script");
      currentScript = scripts[scripts.length - 1];
    }

    let scriptUrl = "";
    let widgetId = window.__FLYRANK_DEFAULT_WIDGET_ID__ || null;

    if (currentScript) {
      scriptUrl = currentScript.src || "";
      if (currentScript.getAttribute("data-widget-id")) {
        widgetId = currentScript.getAttribute("data-widget-id");
      }
    }

    if (!widgetId && scriptUrl) {
      try {
        const urlObj = new URL(scriptUrl, window.location.href);
        widgetId = urlObj.searchParams.get("id");
      } catch (e) {
        // fallback regex
        const match = scriptUrl.match(/[?&]id=([^&#]+)/);
        if (match) widgetId = decodeURIComponent(match[1]);
      }
    }

    let baseUrl = "http://localhost:8000";
    if (scriptUrl) {
      try {
        const urlObj = new URL(scriptUrl, window.location.href);
        baseUrl = urlObj.origin;
      } catch (e) {}
    }

    return { widgetId, baseUrl };
  }

  function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  function renderWidget(config, baseUrl) {
    const themeColor = (config.display_theme && config.display_theme.primary_color) || "#4F46E5";
    const position = (config.display_theme && config.display_theme.position) || "bottom-right";
    const isPopover = config.type === "cta_popover";

    // Target or create mount point
    let mount = document.querySelector(`[data-flyrank-widget="${config.id}"]`);
    if (!mount) {
      mount = document.createElement("div");
      mount.id = `flyrank-widget-${config.id}`;
      document.body.appendChild(mount);
    }

    // Scoped CSS
    const styles = `
      .fl-widget-container {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        box-sizing: border-box;
      }
      .fl-widget-container * { box-sizing: border-box; }
      .fl-card {
        background: #ffffff;
        color: #111827;
        border: 1px solid #E5E7EB;
        border-radius: 12px;
        padding: 24px;
        max-width: 380px;
        width: 100%;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      }
      .fl-popover-wrapper {
        position: fixed;
        ${position.includes("bottom") ? "bottom: 24px;" : "top: 24px;"}
        ${position.includes("right") ? "right: 24px;" : "left: 24px;"}
        z-index: 999999;
      }
      .fl-bubble-btn {
        background: ${themeColor};
        color: #ffffff;
        border: none;
        border-radius: 50px;
        padding: 12px 20px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        box-shadow: 0 4px 14px rgba(0,0,0,0.25);
        display: flex;
        align-items: center;
        gap: 8px;
        transition: transform 0.15s ease;
      }
      .fl-bubble-btn:hover { transform: scale(1.04); }
      .fl-popover-content {
        display: none;
        margin-bottom: 12px;
      }
      .fl-popover-content.open { display: block; animation: flFadeIn 0.2s ease-out; }
      @keyframes flFadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
      .fl-title { font-size: 18px; font-weight: 700; margin: 0 0 6px 0; color: #111827; }
      .fl-desc { font-size: 13px; color: #4B5563; margin: 0 0 18px 0; line-height: 1.4; }
      .fl-group { margin-bottom: 14px; text-align: left; }
      .fl-label { display: block; font-size: 12px; font-weight: 600; margin-bottom: 4px; color: #374151; }
      .fl-input, .fl-textarea {
        width: 100%;
        padding: 8px 12px;
        border: 1px solid #D1D5DB;
        border-radius: 6px;
        font-size: 14px;
        color: #111827;
        background: #F9FAFB;
        outline: none;
        transition: border-color 0.2s;
      }
      .fl-input:focus, .fl-textarea:focus { border-color: ${themeColor}; background: #ffffff; }
      .fl-btn-submit {
        width: 100%;
        background: ${themeColor};
        color: #ffffff;
        font-weight: 600;
        font-size: 14px;
        padding: 10px 16px;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        transition: opacity 0.2s;
      }
      .fl-btn-submit:disabled { opacity: 0.6; cursor: not-allowed; }
      .fl-status { margin-top: 12px; font-size: 13px; padding: 10px; border-radius: 6px; display: none; }
      .fl-status.success { background: #DEF7EC; color: #03543F; display: block; }
      .fl-status.error { background: #FDE8E8; color: #9B1C1C; display: block; }
      /* Honeypot field: invisible to humans, attracts spam bots */
      .fl-hp { display: none !important; position: absolute; left: -9999px; }
    `;

    const styleEl = document.createElement("style");
    styleEl.textContent = styles;
    document.head.appendChild(styleEl);

    // Build form inputs
    const fieldsHtml = config.fields.map(f => {
      const isTextarea = f.type === "textarea";
      return `
        <div class="fl-group">
          <label class="fl-label">${f.label}${f.required ? ' *' : ''}</label>
          ${isTextarea
            ? `<textarea class="fl-textarea" name="${f.name}" placeholder="${f.placeholder || ''}" ${f.required ? 'required' : ''} rows="3"></textarea>`
            : `<input class="fl-input" type="${f.type}" name="${f.name}" placeholder="${f.placeholder || ''}" ${f.required ? 'required' : ''} />`
          }
        </div>
      `;
    }).join("");

    const cardHtml = `
      <div class="fl-card">
        <h3 class="fl-title">${config.title}</h3>
        ${config.description ? `<p class="fl-desc">${config.description}</p>` : ''}
        <form class="fl-form">
          <!-- Honeypot anti-spam trap field -->
          <input type="text" name="_hp" class="fl-hp" tabindex="-1" autocomplete="off" />
          ${fieldsHtml}
          <button type="submit" class="fl-btn-submit">${config.button_text || 'Submit'}</button>
          <div class="fl-status"></div>
        </form>
      </div>
    `;

    let rootContainer = document.createElement("div");
    rootContainer.className = "fl-widget-container";

    if (isPopover) {
      rootContainer.className += " fl-popover-wrapper";
      rootContainer.innerHTML = `
        <div class="fl-popover-content">${cardHtml}</div>
        <button class="fl-bubble-btn" type="button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span>${config.button_text || 'Contact Us'}</span>
        </button>
      `;
      mount.appendChild(rootContainer);

      const triggerBtn = rootContainer.querySelector(".fl-bubble-btn");
      const popoverContent = rootContainer.querySelector(".fl-popover-content");
      triggerBtn.addEventListener("click", () => {
        popoverContent.classList.toggle("open");
      });
    } else {
      rootContainer.innerHTML = cardHtml;
      mount.appendChild(rootContainer);
    }

    // Attach form submission handler
    const form = rootContainer.querySelector(".fl-form");
    const statusDiv = rootContainer.querySelector(".fl-status");
    const submitBtn = rootContainer.querySelector(".fl-btn-submit");

    form.addEventListener("submit", async function (e) {
      e.preventDefault();
      statusDiv.className = "fl-status";
      statusDiv.textContent = "";

      const formData = new FormData(form);
      const payloadData = {};
      let honeypotValue = "";

      formData.forEach((value, key) => {
        if (key === "_hp") {
          honeypotValue = value;
        } else {
          payloadData[key] = value;
        }
      });

      submitBtn.disabled = true;
      submitBtn.textContent = "Sending...";

      const idempotencyKey = uuidv4();
      const submissionUrl = config.submission_url || `${baseUrl}/submissions`;

      try {
        const resp = await fetch(submissionUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey
          },
          body: JSON.stringify({
            widget_id: config.id,
            data: payloadData,
            _hp: honeypotValue
          })
        });

        const result = await resp.json().catch(() => ({}));

        if (resp.ok) {
          statusDiv.className = "fl-status success";
          statusDiv.textContent = result.message || "Thank you! Your submission has been received.";
          form.reset();
        } else {
          statusDiv.className = "fl-status error";
          statusDiv.textContent = (result.detail && result.detail.message) || result.message || `Error (${resp.status}): Failed to submit.`;
        }
      } catch (err) {
        statusDiv.className = "fl-status error";
        statusDiv.textContent = "Network error. Please try again.";
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = config.button_text || 'Submit';
      }
    });
  }

  // Initialization sequence
  async function init() {
    const { widgetId, baseUrl } = getScriptParams();
    if (!widgetId) {
      console.warn("[FlyRank Widget] Missing widget ID. Specify via ?id=... or data-widget-id.");
      return;
    }

    try {
      const configUrl = `${baseUrl}/widgets/${encodeURIComponent(widgetId)}/config`;
      const res = await fetch(configUrl, { cache: "default" });
      if (!res.ok) {
        console.error(`[FlyRank Widget] Failed to load config for ${widgetId}: HTTP ${res.status}`);
        return;
      }
      const config = await res.json();
      renderWidget(config, baseUrl);
    } catch (err) {
      console.error("[FlyRank Widget] Error initializing widget:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
