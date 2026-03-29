(function (window) {
  "use strict";

  const OZInteractionBlocker = window.OZInteractionBlocker || {};

  function getEl() {
    return document.getElementById("ozInteractionBlocker");
  }

  function show() {
    const el = getEl();
    if (!el) return;
    el.hidden = false;
  }

  function hide() {
    const el = getEl();
    if (!el) return;
    el.hidden = true;
  }

  function isVisible() {
    const el = getEl();
    if (!el) return false;
    return !el.hidden;
  }

  OZInteractionBlocker.show = show;
  OZInteractionBlocker.hide = hide;
  OZInteractionBlocker.isVisible = isVisible;

  window.OZInteractionBlocker = OZInteractionBlocker;
})(window);