(function (window, document) {
  "use strict";

  const ApiGuard = (window.ApiGuard = window.ApiGuard || {});

  // -----------------------------
  // Get CSRF token
  // -----------------------------
  ApiGuard.getCsrfToken = function () {
    const input = document.querySelector('[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;

    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };

  // -----------------------------
  // Parse JSON safely
  // Handles empty / invalid / HTML responses
  // -----------------------------
  ApiGuard.parseJsonSafe = async function (response) {
    let text = "";

    try {
      text = await response.text();
    } catch (err) {
      return {
        ok: false,
        error_code: "read_response_failed",
        message: "Could not read server response. Please try again.",
      };
    }

    if (!text) return {};

    try {
      return JSON.parse(text);
    } catch (err) {
      return {
        ok: false,
        error_code: "invalid_response",
        message: "Unexpected server response. Please try again.",
        raw_text: text,
      };
    }
  };

  // -----------------------------
  // Present error globally
  // Reuse popup if exists, otherwise fallback toast
  // -----------------------------
  ApiGuard.presentError = function (message, opts) {
    const text = message || "Something went wrong. Please try again.";
    const meta = opts || {};

    // Existing popup function
    if (typeof window.showPopup === "function") {
      try {
        window.showPopup(text, meta);
        return;
      } catch (err) {
        // continue to fallback
      }
    }

    // Existing common popup DOMs
    const popupMsg =
      document.getElementById("scanPopMsg") ||
      document.getElementById("globalErrorText") ||
      document.getElementById("apiErrorText") ||
      document.getElementById("commonErrorText");

    const popupWrap =
      document.getElementById("scanPopup") ||
      document.getElementById("globalError") ||
      document.getElementById("apiGlobalError") ||
      document.getElementById("commonError");

    if (popupMsg) {
      popupMsg.textContent = text;
    }

    if (popupWrap) {
      popupWrap.hidden = false;
      popupWrap.style.display = "";
      popupWrap.classList.add("show");
      popupWrap.setAttribute("aria-hidden", "false");
      return;
    }

    // Fallback toast
    let el = document.getElementById("api-guard-fallback-error");
    if (!el) {
      el = document.createElement("div");
      el.id = "api-guard-fallback-error";
      el.style.position = "fixed";
      el.style.top = "16px";
      el.style.left = "50%";
      el.style.transform = "translateX(-50%)";
      el.style.zIndex = "99999";
      el.style.maxWidth = "min(92vw, 420px)";
      el.style.width = "max-content";
      el.style.padding = "12px 14px";
      el.style.borderRadius = "12px";
      el.style.background = "#ffe8e8";
      el.style.color = "#8b1e1e";
      el.style.border = "1px solid #f3b3b3";
      el.style.boxShadow = "0 10px 26px rgba(0,0,0,.16)";
      el.style.fontSize = "14px";
      el.style.lineHeight = "1.4";
      el.style.fontFamily = "system-ui, Arial, sans-serif";
      el.style.display = "none";
      document.body.appendChild(el);
    }

    el.textContent = text;
    el.style.display = "block";

    clearTimeout(el._hideTimer);
    el._hideTimer = setTimeout(function () {
      el.style.display = "none";
    }, 3200);
  };

  // -----------------------------
  // Optional success presenter
  // -----------------------------
  ApiGuard.presentSuccess = function (message, opts) {
    if (!message) return;

    if (typeof window.showPopup === "function") {
      try {
        window.showPopup(message, Object.assign({ type: "success" }, opts || {}));
        return;
      } catch (err) {
        // ignore
      }
    }
  };

  // -----------------------------
  // Normalize fetch/network errors
  // -----------------------------
  ApiGuard.normalizeError = function (err) {
    if (!navigator.onLine) {
      return {
        ok: false,
        status: 0,
        error_code: "offline",
        message: "No internet connection. Please check your network.",
      };
    }

    if (err && err.name === "AbortError") {
      return {
        ok: false,
        status: 0,
        error_code: "timeout",
        message: "Request timed out. Please try again.",
      };
    }

    return {
      ok: false,
      status: 0,
      error_code: "network_error",
      message: "Network error. Please try again.",
    };
  };

  // -----------------------------
  // Button loading state helper
  // -----------------------------
ApiGuard.setButtonLoading = function (btn, isLoading, loadingText) {
  if (!btn) return;

  if (isLoading) {
    if (!btn.dataset.originalHtml) {
      btn.dataset.originalHtml = btn.innerHTML;
    }
    if (!btn.dataset.originalDisabled) {
      btn.dataset.originalDisabled = btn.disabled ? "1" : "0";
    }

    btn.disabled = true;
    btn.classList.add("is-loading");

    if (loadingText && !btn.querySelector(".oz-btn__content")) {
      btn.textContent = loadingText;
    }
    return;
  }

  btn.classList.remove("is-loading");
  btn.disabled = btn.dataset.originalDisabled === "1";

  if (!btn.querySelector(".oz-btn__content") && btn.dataset.originalHtml) {
    btn.innerHTML = btn.dataset.originalHtml;
  }
};

  // -----------------------------
  // Internal helper: build result
  // -----------------------------
  ApiGuard.buildResult = function (response, data) {
    return Object.assign(
      {
        ok: response.ok,
        status: response.status,
      },
      data || {}
    );
  };

  // -----------------------------
  // Internal helper: apply default error messages
  // -----------------------------
ApiGuard.ensureErrorShape = function (result, response) {
  if (!result || typeof result !== "object") {
    result = {};
  }

  // backend already sent useful error text
  if (!result.message && result.error) {
    result.message = result.error;
  }

  if (!result.error_code) {
    if (response.status === 400) result.error_code = "bad_request";
    else if (response.status === 401) result.error_code = "unauthorized";
    else if (response.status === 403) result.error_code = "forbidden";
    else if (response.status === 404) result.error_code = "not_found";
    else if (response.status === 409) result.error_code = "conflict";
    else if (response.status >= 500) result.error_code = "server_error";
    else result.error_code = "request_failed";
  }

  if (!result.message) {
    if (response.status === 400) {
      result.message = "Invalid request. Please check and try again.";
    } else if (response.status === 401) {
      result.message = "Your session expired. Please log in again.";
    } else if (response.status === 403) {
      result.message = "Access denied or security check failed.";
    } else if (response.status === 404) {
      result.message = "Requested resource was not found.";
    } else if (response.status === 409) {
      result.message = "This action could not be completed right now.";
    } else if (response.status >= 500) {
      result.message = "Server error. Please try again in a moment.";
    } else {
      result.message = "Something went wrong. Please try again.";
    }
  }

  result.ok = false;
  return result;
};

  // -----------------------------
  // Main universal fetch wrapper
  // -----------------------------
  ApiGuard.apiFetch = async function (url, options) {
    options = options || {};

    const method = (options.method || "POST").toUpperCase();
    const isJson = options.isJson !== false;
    const timeoutMs = Number(options.timeoutMs || 15000);
    const suppressGlobalError = !!options.suppressGlobalError;
    const button = options.button || null;
    const loadingText = options.loadingText || "";
    const autoRedirect = options.autoRedirect !== false;

    const controller = new AbortController();
    const timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);

    const headers = Object.assign(
      {
        "X-Requested-With": "XMLHttpRequest",
      },
      options.headers || {}
    );

    if (method !== "GET" && !headers["X-CSRFToken"]) {
      headers["X-CSRFToken"] = ApiGuard.getCsrfToken();
    }

    if (isJson && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    const fetchOptions = Object.assign({}, options, {
      method: method,
      headers: headers,
      credentials: options.credentials || "same-origin",
      signal: controller.signal,
    });

    delete fetchOptions.timeoutMs;
    delete fetchOptions.suppressGlobalError;
    delete fetchOptions.button;
    delete fetchOptions.loadingText;
    delete fetchOptions.isJson;
    delete fetchOptions.autoRedirect;

    try {
      ApiGuard.setButtonLoading(button, true, loadingText);

      const response = await fetch(url, fetchOptions);
      clearTimeout(timer);

      const parsed = await ApiGuard.parseJsonSafe(response);
      let result = ApiGuard.buildResult(response, parsed);

      // Invalid response parsing case
      if (parsed && parsed.error_code === "invalid_response") {
        result.ok = false;
        result.status = response.status;
      }

      if (!response.ok || result.ok === false) {
        result = ApiGuard.ensureErrorShape(result, response);

        if (!suppressGlobalError) {
          ApiGuard.presentError(result.message, result);
        }

        if (autoRedirect && result.redirect_url) {
          setTimeout(function () {
            window.location.href = result.redirect_url;
          }, 300);
        }

        return result;
      }

      return result;
    } catch (err) {
      clearTimeout(timer);

      const result = ApiGuard.normalizeError(err);

      if (!suppressGlobalError) {
        ApiGuard.presentError(result.message, result);
      }

      return result;
    } finally {
      ApiGuard.setButtonLoading(button, false);
    }
  };

  // -----------------------------
  // Optional GET helper
  // -----------------------------
  ApiGuard.get = function (url, options) {
    return ApiGuard.apiFetch(
      url,
      Object.assign({}, options || {}, {
        method: "GET",
      })
    );
  };

  // -----------------------------
  // Optional POST JSON helper
  // -----------------------------
  ApiGuard.postJson = function (url, payload, options) {
    return ApiGuard.apiFetch(
      url,
      Object.assign({}, options || {}, {
        method: "POST",
        body: JSON.stringify(payload || {}),
      })
    );
  };
})(window, document);