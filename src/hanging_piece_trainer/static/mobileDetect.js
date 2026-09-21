"use strict";

// Redirect phone-width viewports to the dedicated mobile tactics page.
// Loaded synchronously (no `defer`) from templates/tactics.html so it fires
// before the desktop layout is painted. Extracted to an external file so it
// passes the CSP `script-src 'self'` header (inline scripts are blocked).
(function () {
  if (window.matchMedia("(max-width: 640px)").matches
      && !window.location.pathname.endsWith("/mobile")) {
    window.location.replace(
      window.location.pathname + "/mobile" + window.location.search,
    );
  }
})();
