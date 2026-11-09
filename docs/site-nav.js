/* Grouped site menu: one dropdown open at a time; closes on outside click or Escape. */
(function () {
  "use strict";
  function groups() { return Array.prototype.slice.call(document.querySelectorAll("nav.sn details")); }
  function boot() {
    groups().forEach(function (d) {
      d.addEventListener("toggle", function () {
        if (d.open) groups().forEach(function (o) { if (o !== d) o.open = false; });
      });
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest || !e.target.closest("nav.sn")) groups().forEach(function (d) { d.open = false; });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") groups().forEach(function (d) { d.open = false; });
    });
  }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", boot) : boot();
})();
