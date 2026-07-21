// site.js — the only script this site ships (plus the vendored player).
// External file only: CSP `script-src 'self'` allows own-origin files,
// bans inline <script> outright (ci/csp-enforce.sh fails the build on
// any inline script content).
//
// Job: find every `.term-screen[data-cast]`, replace its `.term-fallback`
// excerpt with a live asciinema-player instance. Home hero autoplays once
// (settles on the final frame, no loop); every other panel initializes
// paused at its poster frame and starts on click. Reduced-motion visitors
// never get autoplay anywhere, home included.

(function () {
  "use strict";

  var reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  function initPanel(el) {
    if (el.dataset.initialized === "true") return;
    el.dataset.initialized = "true";

    var src = el.dataset.cast;
    var isHero = el.dataset.hero === "true";
    var autoplay = isHero && !reducedMotion;

    var opts = {
      cols: parseInt(el.dataset.cols || "80", 10),
      rows: parseInt(el.dataset.rows || "24", 10),
      fit: "width",
      controls: true,
      preload: false,
      autoplay: autoplay,
      loop: false,
      idleTimeLimit: 2,
    };

    if (el.dataset.poster) {
      opts.poster = el.dataset.poster;
    }

    // Clear the no-JS <pre> excerpt fallback; the player replaces it.
    el.textContent = "";
    window.AsciinemaPlayer.create(src, el, opts);
  }

  function armClickToInit(el) {
    function onActivate() {
      initPanel(el);
      el.removeEventListener("click", onActivate);
      el.removeEventListener("keydown", onKeydown);
    }
    function onKeydown(ev) {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        onActivate();
      }
    }
    el.tabIndex = 0;
    el.setAttribute("role", "button");
    el.setAttribute(
      "aria-label",
      "Play recording: " + (el.dataset.label || "terminal session")
    );
    el.addEventListener("click", onActivate);
    el.addEventListener("keydown", onKeydown);
  }

  function main() {
    if (typeof window.AsciinemaPlayer === "undefined") return;

    var panels = document.querySelectorAll(".term-screen[data-cast]");
    var heroInitialized = false;

    panels.forEach(function (el) {
      var isHero = el.dataset.hero === "true";

      // Lazy discipline: at most one live player per page load. The
      // home hero (if present) initializes immediately; every other
      // panel — including a second hero-flagged one, which should not
      // happen — waits for a click.
      if (isHero && !heroInitialized) {
        heroInitialized = true;
        initPanel(el);
      } else {
        armClickToInit(el);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", main);
  } else {
    main();
  }
})();
