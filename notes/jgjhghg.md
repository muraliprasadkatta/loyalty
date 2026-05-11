{% load static %}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>User • OfferZone</title>
  <link rel="stylesheet" href="{% static 'offers/user_homepage/css/branch_cards.css' %}">


<style>
:root {
  --bg1: #eef4ff;
  --bg2: #f6f8ff;
  --bg3: #ffffff;
  --text: #0f172a;
  --muted: #475569;
  --prim: #4c74ff;

  --hdr: #0b1436;
  --hdr2: #101c45;
  --hdrText: #e8ecff;
  --hdrBorder: rgba(255, 255, 255, 0.10);

  --card: rgba(255, 255, 255, 0.86);
  --card2: rgba(255, 255, 255, 0.70);
  --border: rgba(15, 23, 42, 0.12);

  --shadow: 0 22px 60px rgba(15, 23, 42, 0.12);
  --shadow2: 0 14px 34px rgba(15, 23, 42, 0.10);
  --shadow3: 0 10px 22px rgba(15, 23, 42, 0.08);

  --hlTop: rgba(76, 116, 255, 0.18);

  --lightCard: #ffffff;
  --lightCard2: #fbfcff;
  --lightBorder: rgba(15, 23, 42, 0.10);
  --lightText: #0f172a;
  --lightMuted: #475569;

  --ok: rgba(34, 197, 94, 0.60);
  --bad: rgba(239, 68, 68, 0.45);
}

/* =========================
   BASE
========================= */

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  padding: 0;
  width: 100%;
  max-width: 100%;
}

body {
  min-height: 100vh;
  color: var(--text);
  font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;

  background:
    radial-gradient(900px 520px at 18% 8%, rgba(76, 116, 255, 0.14), transparent 55%),
    radial-gradient(900px 520px at 82% 18%, rgba(99, 102, 241, 0.12), transparent 60%),
    radial-gradient(900px 520px at 50% 92%, rgba(34, 197, 94, 0.10), transparent 60%),
    linear-gradient(180deg, var(--bg1) 0%, var(--bg2) 45%, var(--bg3) 100%);
}

body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  opacity: 0.35;
  background:
    radial-gradient(circle at 20% 10%, rgba(255, 255, 255, 0.45), transparent 45%),
    radial-gradient(circle at 80% 30%, rgba(255, 255, 255, 0.35), transparent 55%);
}

a {
  color: var(--prim);
  text-decoration: none;
}

a:hover {
  opacity: 0.92;
}

/* =========================
   HEADER
========================= */

header {
  position: sticky;
  top: 0;
  z-index: 30;

  display: flex;
  align-items: center;
  justify-content: space-between;

  padding: 14px 18px;
  background: linear-gradient(180deg, var(--hdr) 0%, var(--hdr2) 100%);
  border-bottom: 1px solid var(--hdrBorder);
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.20);
}

header .brand {
  color: var(--hdrText);
  font-weight: 800;
  letter-spacing: 0.3px;
}

header .right {
  display: flex;
  align-items: center;
  gap: 12px;
}

header .right a {
  color: rgba(232, 236, 255, 0.92);
}

.scan-hero__art {
  position: absolute;
  inset: 0;
  z-index: 0;

  width: 100%;
  height: 100%;

  transform: none;
  opacity: 0.38;
  pointer-events: none;
  overflow: hidden;
}

.scan-hero__art img {
  display: block;
  width: 100%;
  height: 100%;

  object-fit: cover;
  object-position: center;
}



.scan-hero__inner {
  position: relative;
  z-index: 2;
  text-align: center;
  user-select: none;
  cursor: pointer;
}


/* =========================
   BUTTONS
========================= */

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;

  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(76, 116, 255, 0.18);

  color: #ffffff;
  background: var(--prim);
  font-weight: 700;
  cursor: pointer;

  box-shadow: 0 12px 22px rgba(76, 116, 255, 0.18);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 16px 30px rgba(76, 116, 255, 0.22);
}

.btn:active {
  transform: translateY(0);
  box-shadow: 0 10px 18px rgba(76, 116, 255, 0.18);
}

.btn.outline {
  color: var(--hdrText);
  background: rgba(255, 255, 255, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: none;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

/* =========================
   LAYOUT
========================= */

.wrap {
  width: 100%;
  max-width: none;
  margin: 0 0 72px;
  padding: 0 clamp(8px, 3.5vw, 24px);
}

/* =========================
   BASE CARD
========================= */

.card {
  position: relative;
  padding: clamp(12px, 4vw, 18px);
  border-radius: clamp(18px, 5vw, 20px);
  overflow: hidden;

  background: linear-gradient(180deg, var(--card) 0%, var(--card2) 100%);
  border: 1px solid rgba(15, 23, 42, 0.12);
  box-shadow: var(--shadow);

  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.card > * {
  position: relative;
  z-index: 1;
}

.card::before {
  content: "";
  position: absolute;
  left: 14px;
  right: 14px;
  top: 10px;
  height: 4px;
  border-radius: 999px;
  opacity: 0.9;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    rgba(76, 116, 255, 0),
    var(--hlTop),
    rgba(76, 116, 255, 0)
  );
}

.card::after {
  content: "";
  position: absolute;
  inset: -40px -40px auto -40px;
  height: 140px;
  pointer-events: none;
  background: radial-gradient(
    closest-side at 35% 40%,
    rgba(76, 116, 255, 0.12),
    transparent 70%
  );
}

/* =========================
   MESSAGE
========================= */

.msg {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 14px;

  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(15, 23, 42, 0.12);
  box-shadow: var(--shadow3);
}

/* =========================
   WELCOME / HERO CARD
========================= */

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.hero h1 {
  margin: 0;
  font-size: clamp(20px, 6vw, 22px);
  line-height: 1.12;
  overflow-wrap: anywhere;
}

.welcome-card {
  width: 100%;
  min-width: 0;
  margin-top: 0;

}

.welcome-copy {
  flex: 1 1 0;
  min-width: 0;
  max-width: 100%;
}

.welcome-copy p {
  max-width: 100%;
  overflow-wrap: anywhere;
}

/* User home hidden items */
.geo-wrap {
  display: none !important;
}

.card.hero > a.btn {
  display: none !important;
}

/* =========================
   LOCATION SECTION FIXES
   Used inside welcome card
========================= */

.oz-location-inline,
.oz-location-top,
.oz-location-copy,
.oz-location-meta,
.oz-location-message,
.oz-location-btn {
  max-width: 100%;
  min-width: 0;
}

.oz-location-sub,
.oz-location-message,
.oz-location-btn {
  overflow-wrap: anywhere;
}

/* =========================
   TAP TO SCAN HERO
========================= */
.scan-hero-shell {
  position: sticky;
  top: var(--oz-header-height, 0px); /* header kindha exact 0 gap */
  z-index: 20;
  margin-top: 0;
  margin-bottom: 10px;
}

.scan-hero-shell > .scan-hero {
  position: relative;
  z-index: 1;
}

.scan-hero {
  width: 100%;
  max-width: 100%;

  height: clamp(170px, 42vw, 205px);
  min-height: clamp(170px, 42vw, 205px);
  padding: 18px;
  border-radius: 22px;
  overflow: hidden;

  display: flex;
  align-items: center;
  justify-content: center;

  color: #ffffff;
  background: linear-gradient(180deg, #2b48ff 0%, #5a86ff 60%, #6aa1ff 100%);
  box-shadow: 0 22px 60px rgba(15, 23, 42, 0.22);

  margin-left: auto;
  margin-right: auto;

  will-change: width, height, padding, border-radius;
  transform: translateZ(0);
  backface-visibility: hidden;

}

/* .scan-hero {
  position: sticky;
  top: var(--oz-header-height, 8px);
  z-index: 9;
} */



.scan-hero__qr {
  position: relative;
  width: var(--scan-qr-size, 88px);
  height: var(--scan-qr-size, 88px);
  margin: var(--scan-qr-margin, 6px auto 10px);
  border-radius: var(--scan-qr-radius, 14px);

  display: grid;
  place-items: center;

  background: rgba(255, 255, 255, 0.14);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.25);
}

.qr-ic {
  width: var(--scan-icon-size, 34px);
  height: var(--scan-icon-size, 34px);
  display: inline-block;
}

.scan-hero__text {
  font-size: 18px;
  font-weight: 900;
  letter-spacing: 0.2px;
  opacity: var(--scan-text-opacity, 1);
}

.scan-hero__sub {
  opacity: var(--scan-sub-opacity, 0.92);
  font-size: 12px;
}



.scan-hero.scan-hero--morphing .scan-hero__inner,
.scan-hero.scan-hero--morphing .oz-inline-loading__content {
  width: 100%;
  height: 100%;
}

.scan-hero.scan-hero--morphing .oz-inline-loading__content {
  display: grid;
  place-items: center;
}

.scan-hero.scan-hero--morphing .scan-hero__text,
.scan-hero.scan-hero--morphing .scan-hero__sub {
  pointer-events: none;
}

.scan-hero.scan-hero--morphing .scan-hero__qr::before {
  opacity: var(--scan-dash-opacity, 1);
}




.scan-hero__qr::before {
  content: "";
  position: absolute;
  inset: 0;
  padding: 10px;
  border-radius: 14px;
  border: 2px dashed rgba(255, 255, 255, 0.35);

  mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
}


.scan-hero__corner {
  position: absolute;
  width: 34px;
  height: 34px;
  border: 4px solid #bfe0ff;
  border-radius: 10px;
  opacity: var(--scan-corners-opacity, 1);
}

.scan-hero__corner.tl {
  top: 18px;
  left: 18px;
  border-right: none;
  border-bottom: none;
}

.scan-hero__corner.tr {
  top: 18px;
  right: 18px;
  border-left: none;
  border-bottom: none;
}

.scan-hero__corner.bl {
  bottom: 18px;
  left: 18px;
  border-right: none;
  border-top: none;
}

.scan-hero__corner.br {
  right: 18px;
  bottom: 18px;
  border-left: none;
  border-top: none;
}

.qr-ic svg {
  width: 100%;
  height: 100%;
  opacity: 0.95;
}

.scan-inline-error {
  color: #7f1d1d;
  background: rgba(239, 68, 68, 0.10);
  border: 1px solid rgba(239, 68, 68, 0.28);
}

.scan-hero .oz-inline-loading__content {
  transform: scale(var(--scan-content-scale, 1));
  transform-origin: center;
}

.scan-hero.scan-hero--morphing .oz-inline-loading__content {
  display: grid;
  place-items: center;
}


.scan-hero-shell,
.scan-hero {
  overflow-anchor: none;
}
/* =========================
   QUICK TILES
========================= */

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.tile {
  position: relative;
  padding: 16px;
  border-radius: 18px;
  overflow: hidden;

  display: flex;
  flex-direction: column;
  gap: 8px;

  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.12);
  box-shadow: var(--shadow2);

  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.tile::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;

  height: 2px;
  opacity: 0.9;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    rgba(76, 116, 255, 0),
    rgba(76, 116, 255, 0.22),
    rgba(76, 116, 255, 0)
  );
}

.tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
}

.tile strong {
  font-size: 16px;
}

.tile small {
  color: var(--muted);
}

/* =========================
   BOTTOM TABS
========================= */

footer.nav {
  position: sticky;
  bottom: 0;

  background: rgba(255, 255, 255, 0.86);
  border-top: 1px solid rgba(15, 23, 42, 0.10);
  box-shadow: 0 -14px 34px rgba(15, 23, 42, 0.10);

  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.tabs {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
}

.tab {
  padding: 10px 8px;
  color: var(--muted);
  text-align: center;
  font-weight: 900;
}

.tab.active {
  color: var(--text);
  border-bottom: 2px solid var(--prim);
}

/* =========================
   RESPONSIVE
========================= */

@media (min-width: 740px) {
  .grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (hover: none) and (pointer: coarse) {
  .wrap {
    padding-left: 10px;
    padding-right: 10px;
  }
}

@media (max-width: 360px) {
  .wrap {
    padding-left: 8px;
    padding-right: 8px;
  }

  .card {
    padding: 12px;
  }

  .oz-location-inline {
    margin-top: 12px;
    padding-top: 12px;
  }

  .oz-location-top {
    gap: 8px;
  }

  .oz-location-icon {
    width: 34px;
    height: 34px;
    border-radius: 13px;
    font-size: 17px;
  }

  .oz-location-title {
    font-size: 13.5px;
  }

  .oz-location-sub {
    font-size: 11px;
  }

  .oz-location-status,
  .oz-location-accuracy {
    min-height: 22px;
    padding: 4px 8px;
    font-size: 10.5px;
  }

  .oz-location-message {
    padding: 9px 10px;
    font-size: 11px;
  }

  .oz-location-btn {
    min-height: 44px;
    padding: 11px 12px;
    font-size: 12.5px;
  }
}
</style>

</head>
<body>

    <header>
    <div class="brand">OfferZone</div>
    <div class="right">
      {% if request.user.is_authenticated %}
        <!-- <a class="btn outline" href="{% url 'offers:user_status' %}" data-requires-network="1">Profile</a> -->
        <a href="{% url 'offers:user_status' %}" data-requires-network="1">Status</a>
      {% else %}
        <a class="btn outline" href="{% url 'offers:user_login' %}?next={% url 'offers:user_home' %}" data-requires-network="1">Login</a>
      {% endif %}
    </div>
  </header>

  <div id="ozInteractionBlocker" hidden aria-hidden="true"></div>

  <main class="wrap">
    {% if messages %}
      {% for m in messages %}
        <div class="msg">{{ m }}</div>
      {% endfor %}
    {% endif %}

    <!-- Tap to Scan + Scan Modal -->
    {% include "user_interface/user_homepage/partials/tap_to_scan_hero.html" %}

    <!-- Welcome -->
  <div class="card hero welcome-card">
    <div class="welcome-copy">
        <h1>
          Welcome
          {% if request.user.is_authenticated %}
            {% if display_name %}, {{ display_name }}
            {% elif request.user.first_name %}, {{ request.user.first_name }}
            {% elif request.user.username %}, {{ request.user.username }}
            {% else %}, {{ request.user.email }}
            {% endif %}
          {% else %}
            to OfferZone
          {% endif %} 👋
        </h1>

        <p style="margin:.3rem 0 0; color:var(--muted); font-weight:700">
          Browse today’s menu, collect visits, and claim offers.
        </p>

        {% include "user_interface/user_homepage/partials/location_prompt.html" %}
      </div>

      <a class="btn" href="#">View Today’s Menu</a>
    </div>

    <!-- Branches -->
    {% include "user_interface/user_homepage/partials/branch_list_cards.html" %}

    <!-- Quick tiles -->
    {% include "user_interface/user_homepage/partials/quick_tiles.html" %}
  </main>

  {% include "user_interface/user_homepage/partials/footer.html" %}

  {% include "ui_states/spinners/page_loader.html" %}

  {% if request.user.is_authenticated %}
    {% include "user_interface/user_name_modal.html" %}
  {% endif %}


<script>
  (() => {
    const shell = document.getElementById("scanHeroShell");
    const scanHero = document.getElementById("tapToScan");
    const header = document.querySelector("header");

    if (!shell || !scanHero) return;

    const MORPH_DISTANCE = 220;      // bigger = slower height compress
    const MIN_HEIGHT = 64;           // final thin banner height
    const HEADER_GAP = 0;            // header ki gap kavali ante 6/8 pettu

    const WIDTH_START_AT = 0.50;     // height half compress ayyaka width start
    const MIN_WIDTH_RATIO = 0.68;    // final width = 68% of original width
    const MIN_WIDTH_PX = 260;        // too small avvakunda safety

    let base = null;
    let ticking = false;
    let lastViewportWidth = window.innerWidth;
    let resizeTimer = null;

    function clamp(value, min, max) {
      return Math.min(Math.max(value, min), max);
    }

    function lerp(start, end, progress) {
      return start + (end - start) * progress;
    }

    function smooth(progress) {
      return progress * progress * (3 - 2 * progress);
    }

    function getHeaderHeight() {
      const headerHeight = header
        ? Math.ceil(header.getBoundingClientRect().height)
        : 58;

      document.documentElement.style.setProperty(
        "--oz-header-height",
        `${headerHeight}px`
      );

      return headerHeight;
    }

    function resetInlineStyles(keepShell = false) {
      scanHero.classList.remove("scan-hero--morphing");

      scanHero.style.height = "";
      scanHero.style.minHeight = "";
      scanHero.style.padding = "";
      scanHero.style.borderRadius = "";

      scanHero.style.width = "";
      scanHero.style.marginLeft = "";
      scanHero.style.marginRight = "";

      if (!keepShell) {
        shell.style.height = "";
        shell.style.minHeight = "";
      }

      scanHero.style.removeProperty("--scan-qr-size");
      scanHero.style.removeProperty("--scan-icon-size");
      scanHero.style.removeProperty("--scan-qr-margin");
      scanHero.style.removeProperty("--scan-qr-radius");
      scanHero.style.removeProperty("--scan-text-opacity");
      scanHero.style.removeProperty("--scan-sub-opacity");
      scanHero.style.removeProperty("--scan-corners-opacity");
      scanHero.style.removeProperty("--scan-dash-opacity");
      scanHero.style.removeProperty("--scan-content-scale");
    }

    function measureBase() {
      resetInlineStyles();

      const headerHeight = getHeaderHeight();
      const shellRect = shell.getBoundingClientRect();
      const scanRect = scanHero.getBoundingClientRect();

      base = {
        pageTop: shellRect.top + window.scrollY,
        left: shellRect.left,
        width: shellRect.width,
        height: scanRect.height || 150,
        headerHeight
      };

      shell.style.height = `${base.height}px`;
      shell.style.minHeight = `${base.height}px`;
    }

    function updateMorph() {
      if (!base) {
        measureBase();
        requestAnimationFrame(updateMorph);
        return;
      }

      const headerHeight = getHeaderHeight();
      const stickyTop = headerHeight + HEADER_GAP;

      const startY = Math.max(0, base.pageTop - stickyTop);
      const endY = startY + MORPH_DISTANCE;

      const rawProgress = clamp(
        (window.scrollY - startY) / (endY - startY),
        0,
        1
      );

      if (rawProgress <= 0) {
        resetInlineStyles(true);

        shell.style.height = `${base.height}px`;
        shell.style.minHeight = `${base.height}px`;

        ticking = false;
        return;
      }

      const progress = rawProgress; // smooth easing remove - scroll direct response

      const currentHeight = lerp(base.height, MIN_HEIGHT, progress).toFixed(2);
      const currentPadding = lerp(18, 8, progress).toFixed(2);
      const currentRadius = lerp(22, 18, progress).toFixed(2);
      const widthProgress = clamp(
        (rawProgress - WIDTH_START_AT) / (1 - WIDTH_START_AT),
        0,
        1
      );

      const minWidth = Math.min(
        base.width,
        Math.max(MIN_WIDTH_PX, base.width * MIN_WIDTH_RATIO)
      );

      const currentWidth = lerp(base.width, minWidth, widthProgress).toFixed(2);

      const qrSize = lerp(88, 42, progress).toFixed(2);
      const iconSize = lerp(34, 24, progress).toFixed(2);
      const contentScale = lerp(1, 0.72, progress).toFixed(3);

      const textOpacity = clamp(1 - rawProgress * 1.15, 0.18, 1);
      const subOpacity = clamp(0.92 - rawProgress * 1.8, 0, 0.92);
      const cornersOpacity = clamp(1 - rawProgress * 0.8, 0.35, 1);
      const dashOpacity = clamp(1 - rawProgress * 1.2, 0, 1);

      scanHero.classList.add("scan-hero--morphing");

      scanHero.style.width = `${currentWidth}px`;
      scanHero.style.height = `${currentHeight}px`;
      scanHero.style.minHeight = `${currentHeight}px`;
      scanHero.style.padding = `${currentPadding}px`;
      scanHero.style.borderRadius = `${currentRadius}px`;

      scanHero.style.marginLeft = "auto";
      scanHero.style.marginRight = "auto";

      scanHero.style.setProperty("--scan-qr-size", `${qrSize}px`);
      scanHero.style.setProperty("--scan-icon-size", `${iconSize}px`);
      scanHero.style.setProperty("--scan-qr-margin", "0 auto 4px");
      scanHero.style.setProperty("--scan-qr-radius", `${lerp(14, 12, progress)}px`);
      scanHero.style.setProperty("--scan-text-opacity", textOpacity);
      scanHero.style.setProperty("--scan-sub-opacity", subOpacity);
      scanHero.style.setProperty("--scan-corners-opacity", cornersOpacity);
      scanHero.style.setProperty("--scan-dash-opacity", dashOpacity);
      scanHero.style.setProperty("--scan-content-scale", contentScale);

      ticking = false;
    }

    function requestUpdate() {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(updateMorph);
    }

    window.addEventListener("scroll", requestUpdate, { passive: true });

    window.addEventListener("resize", () => {
      const newWidth = window.innerWidth;

      /*
        Mobile address bar open/close appudu resize fire avuthundhi.
        Width same unte re-measure cheyyakudadhu.
        Leka pothe first scroll lo scanner full height ki reset avuthundhi.
      */
      if (Math.abs(newWidth - lastViewportWidth) < 8) {
        return;
      }

      lastViewportWidth = newWidth;

      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        base = null;
        requestUpdate();
      }, 120);
    });

    window.addEventListener("load", () => {
      /*
        User already scroll start chesina taruvatha load event vaste
        measureBase() call cheyyakudadhu. Leka pothe scanner normal size ki reset avuthundhi.
      */
      if (window.scrollY <= 2) {
        measureBase();
      }

      requestUpdate();
    });

    measureBase();
    requestUpdate();
  })();
</script>

<script>
  (() => {
    const grid = document.getElementById("homeBranchGrid");
    if (!grid) return;

    let isRefreshing = false;

    async function refreshHomeBranchCards() {
      if (isRefreshing) return;

      const refreshUrl = grid.dataset.refreshUrl;
      if (!refreshUrl) return;

      isRefreshing = true;

      try {
        const url = new URL(refreshUrl, window.location.origin);
        url.searchParams.set("offset", "0");
        url.searchParams.set("location", "all");
        url.searchParams.set("_", Date.now().toString());

        const response = await fetch(url.toString(), {
          method: "GET",
          credentials: "same-origin",
          headers: {
            "X-Requested-With": "XMLHttpRequest"
          }
        });

        if (!response.ok) return;

        const data = await response.json();

        if (data && data.ok && typeof data.html === "string") {
          grid.innerHTML = data.html;
        }
      } catch (error) {
        console.warn("Branch cards refresh failed:", error);
      } finally {
        isRefreshing = false;
      }
    }

    window.addEventListener("oz:location-saved", refreshHomeBranchCards);
  })();
</script>


  <script>
    if (window.history && window.history.replaceState) {
      window.history.replaceState(null, '', window.location.href);
    }
  </script>

  <script>
    (function () {
      function shouldHandleNav(el) {
        if (!el) return false;

        const href = el.getAttribute("href");

        if (!href) return false;
        if (href === "#" || href.startsWith("#")) return false;
        if (el.hasAttribute("download")) return false;
        if (el.target && el.target !== "_self") return false;

        return true;
      }

      document.addEventListener("click", function (e) {
        const link = e.target.closest("a");
        if (!shouldHandleNav(link)) return;
        if (!navigator.onLine) return;

        window.OZInteractionBlocker?.show();
        window.OZPageLoader?.show("Loading...");
      }, true);
    })();
  </script>
</body>
</html>