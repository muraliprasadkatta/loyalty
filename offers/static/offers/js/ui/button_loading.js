// offers/static/offers/js/ui/button_loading.js
(function (window) {
  "use strict";

  const OZButtons = window.OZButtons || {};

  function isElement(el) {
    return el && typeof el === "object" && el.nodeType === 1;
  }

  function setAriaBusy(btn, isLoading) {
    if (!isElement(btn)) return;
    btn.setAttribute("aria-busy", isLoading ? "true" : "false");
  }

  function lockWidth(btn) {
    if (!isElement(btn)) return;
    if (btn.dataset.ozWidthLocked === "1") return;

    const width = btn.offsetWidth;
    if (width > 0) {
      btn.style.width = width + "px";
      btn.dataset.ozWidthLocked = "1";
    }
  }

  function unlockWidth(btn) {
    if (!isElement(btn)) return;
    if (btn.dataset.ozWidthLocked !== "1") return;

    btn.style.width = "";
    delete btn.dataset.ozWidthLocked;
  }

  function setDisabled(btn, shouldDisable) {
    if (!isElement(btn)) return;
    btn.disabled = !!shouldDisable;
  }

  function setLoading(btn, isLoading, options) {
    if (!isElement(btn)) return;

    const opts = options || {};
    const disable = opts.disable !== false;     // default true
    const keepWidth = opts.keepWidth === true;  // default false

    if (isLoading) {
      if (keepWidth) lockWidth(btn);
      btn.classList.add("oz-btn-loading");
      if (disable) setDisabled(btn, true);
      setAriaBusy(btn, true);
      return;
    }

    btn.classList.remove("oz-btn-loading");
    if (disable) setDisabled(btn, false);
    setAriaBusy(btn, false);
    if (keepWidth) unlockWidth(btn);
  }

  function start(btn, options) {
    setLoading(btn, true, options);
  }

  function stop(btn, options) {
    setLoading(btn, false, options);
  }

  function withLoading(btn, promiseLike, options) {
    start(btn, options);

    return Promise.resolve(promiseLike)
      .finally(function () {
        stop(btn, options);
      });
  }

  OZButtons.setLoading = setLoading;
  OZButtons.start = start;
  OZButtons.stop = stop;
  OZButtons.withLoading = withLoading;

  window.OZButtons = OZButtons;
})(window);