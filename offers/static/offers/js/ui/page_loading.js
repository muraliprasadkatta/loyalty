(function (window) {
  "use strict";

  const OZPageLoader = window.OZPageLoader || {};

  function getRoot() {
    return document.getElementById("ozPageLoader");
  }

  function getTextEl() {
    return document.getElementById("ozPageLoaderText");
  }

  function setText(message) {
    const textEl = getTextEl();
    if (!textEl) return;

    textEl.textContent = (message && String(message).trim()) || "Loading...";
  }

  function show(message) {
    const root = getRoot();
    if (!root) return;

    setText(message);
    root.hidden = false;
    root.setAttribute("aria-busy", "true");
  }

  function hide() {
    const root = getRoot();
    if (!root) return;

    root.hidden = true;
    root.setAttribute("aria-busy", "false");
  }

  function isVisible() {
    const root = getRoot();
    if (!root) return false;
    return !root.hidden;
  }

  function showForRedirect(url, message) {
    if (!url) return;

    show(message || "Opening...");
    window.location.assign(url);
  }

  function replaceForRedirect(url, message) {
    if (!url) return;

    show(message || "Opening...");
    window.location.replace(url);
  }

  function bindLinks(selector, options) {
    const opts = options || {};
    const message = opts.message || "Opening...";

    document.querySelectorAll(selector).forEach(function (el) {
      el.addEventListener("click", function (e) {
        if (
          e.defaultPrevented ||
          el.target === "_blank" ||
          el.hasAttribute("download") ||
          el.getAttribute("href") === "#" ||
          !el.href
        ) {
          return;
        }

        show(message);
      });
    });
  }

  OZPageLoader.show = show;
  OZPageLoader.hide = hide;
  OZPageLoader.setText = setText;
  OZPageLoader.isVisible = isVisible;
  OZPageLoader.showForRedirect = showForRedirect;
  OZPageLoader.replaceForRedirect = replaceForRedirect;
  OZPageLoader.bindLinks = bindLinks;

  window.OZPageLoader = OZPageLoader;
})(window);