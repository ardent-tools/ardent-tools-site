// site.js — the site's always-loaded enhancement script.
// External file only: CSP `script-src 'self'` allows own-origin files,
// bans inline <script> outright (ci/csp-enforce.sh fails the build on
// any inline script content).
//
// Job: find every `.term-screen[data-cast]`, replace its `.term-fallback`
// excerpt with a live asciinema-player instance, initialized on click.
// Every panel starts paused; nothing autoplays.

(function () {
  "use strict";

  function initPanel(el) {
    if (el.dataset.initialized === "true") return;
    el.dataset.initialized = "true";

    var src = el.dataset.cast;

    var opts = {
      cols: parseInt(el.dataset.cols || "80", 10),
      rows: parseInt(el.dataset.rows || "24", 10),
      fit: "width",
      controls: true,
      preload: false,
      autoplay: false,
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
      // The live AsciinemaPlayer mounted by initPanel() is its own
      // separately-interactive widget now; the pre-initialization shell's
      // "Play recording" button semantics no longer describe this
      // element and must not linger (WCAG 4.1.2 name/role/value).
      el.removeAttribute("role");
      el.removeAttribute("aria-label");
      el.removeAttribute("tabindex");
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
    panels.forEach(armClickToInit);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", main);
  } else {
    main();
  }
})();
