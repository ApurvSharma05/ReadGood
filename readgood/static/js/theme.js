// Runs in <head> before first paint so the page never flashes the wrong theme.
(function () {
  var stored = null;
  try { stored = localStorage.getItem("rg-theme"); } catch (e) { /* storage blocked */ }
  var dark = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.setAttribute("data-bs-theme", dark ? "dark" : "light");
})();
