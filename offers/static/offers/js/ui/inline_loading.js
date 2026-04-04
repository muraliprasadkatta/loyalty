// 'offers/js/ui/inline_loading.js'
(function (window) {
  "use strict";

  const OZInlineLoading = window.OZInlineLoading || {};

  function isElement(el) {
    return !!(el && el.nodeType === 1);
  }

  function getContentEl(root) {
    return isElement(root) ? root.querySelector(".oz-inline-loading__content") : null;
  }

  function getLoadingEl(root) {
    return isElement(root) ? root.querySelector(".oz-inline-loading__state") : null;
  }

  function setLoading(root, isLoading) {
    if (!isElement(root)) return;

    const contentEl = getContentEl(root);
    const loadingEl = getLoadingEl(root);
    const on = !!isLoading;

    root.classList.toggle("oz-is-inline-loading", on);
    root.setAttribute("aria-busy", on ? "true" : "false");

    if (contentEl) {
      contentEl.hidden = on;
    }

    if (loadingEl) {
      loadingEl.hidden = !on;
    }

    if ("disabled" in root) {
      root.disabled = on;
    }
  }

  function start(root) {
    setLoading(root, true);
  }

  function stop(root) {
    setLoading(root, false);
  }

  function setText(root, text) {
    if (!isElement(root)) return;

    const textEl = root.querySelector(".oz-inline-loading__text");
    if (!textEl) return;

    textEl.textContent = (text && String(text).trim()) || "Loading...";
  }

  OZInlineLoading.setLoading = setLoading;
  OZInlineLoading.start = start;
  OZInlineLoading.stop = stop;
  OZInlineLoading.setText = setText;

  window.OZInlineLoading = OZInlineLoading;
})(window);