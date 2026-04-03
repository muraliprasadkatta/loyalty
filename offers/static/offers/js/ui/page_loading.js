(function (window, document) {
  "use strict";

  const OZPageLoader = window.OZPageLoader || {};
  const DEFAULT_TEXT = "Loading...";

  function getEl() {
    return document.getElementById("ozPageLoader");
  }

  function getTextEl() {
    return document.getElementById("ozPageLoaderText");
  }

  function setText(text) {
    const textEl = getTextEl();
    if (!textEl) return;

    const value = typeof text === "string" ? text : DEFAULT_TEXT;
    textEl.textContent = value.trim() || DEFAULT_TEXT;
  }

  function show(text) {
    const el = getEl();
    if (!el) return;

    setText(text);
    el.hidden = false;
    el.setAttribute("aria-hidden", "false");
    el.setAttribute("aria-busy", "true");
  }

  function hide() {
    const el = getEl();
    if (!el) return;

    el.hidden = true;
    el.setAttribute("aria-hidden", "true");
    el.setAttribute("aria-busy", "false");
    setText(DEFAULT_TEXT);
  }

  function isVisible() {
    const el = getEl();
    if (!el) return false;
    return !el.hidden;
  }

  OZPageLoader.show = show;
  OZPageLoader.hide = hide;
  OZPageLoader.isVisible = isVisible;
  OZPageLoader.setText = setText;

  window.OZPageLoader = OZPageLoader;

  document.addEventListener("DOMContentLoaded", function () {
    hide();
  });

  window.addEventListener("pageshow", function () {
    hide();
  });
})(window, document);