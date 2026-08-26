// FLIP piece-move animation helper.
//
// The board renderers destroy and rebuild all 64 <button> nodes on every
// state change, so we can't simply CSS-transition an existing DOM node.
// Instead, we use the classic FLIP trick:
//
//   1. First — capture the position of the source square before rendering.
//   2. Last  — call the caller's render function; the piece SVG is now at
//              the destination square.
//   3. Invert — apply `transform: translate(dx, dy)` to the destination
//              square's SVG so it visually sits back at the source position.
//   4. Play  — on the next paint, clear the transform. The CSS transition
//              on `.square > svg` (see app.css) animates it to zero, i.e.
//              slides it to its natural destination position.
//
// The CSS transition is guarded by `prefers-reduced-motion: reduce`, so
// motion-sensitive users automatically get the pre-animation teleport.
"use strict";

(function () {
  function rectAt(boardEl, square) {
    return boardEl.querySelector(`[data-square="${square}"]`)?.getBoundingClientRect() || null;
  }

  function svgIn(boardEl, square) {
    return boardEl.querySelector(`[data-square="${square}"] > svg`) || null;
  }

  function playFlip(boardEl, moves) {
    // `moves` is [{from, to}]. Compute all deltas, apply invert, then release.
    const deltas = [];
    for (const { from, to } of moves) {
      const fromRect = rectAt(boardEl, from);
      const toRect = rectAt(boardEl, to);
      if (!fromRect || !toRect) continue;
      const svg = svgIn(boardEl, to);
      if (!svg) continue;
      const dx = fromRect.left - toRect.left;
      const dy = fromRect.top - toRect.top;
      deltas.push({ svg, dx, dy });
    }
    if (!deltas.length) return;
    // Set invert transform without a transition — the piece appears at source.
    for (const { svg, dx, dy } of deltas) {
      svg.style.transition = "none";
      svg.style.transform = `translate(${dx}px, ${dy}px)`;
    }
    // Force the browser to apply the invert before we release it. Reading
    // getBoundingClientRect flushes the layout, so the next tick sees the
    // pre-animation state committed.
    boardEl.getBoundingClientRect();
    // Clear the styles on the next frame so the CSS transition kicks in.
    requestAnimationFrame(() => {
      for (const { svg } of deltas) {
        svg.style.transition = "";
        svg.style.transform = "";
      }
    });
  }

  // Public API: animate a single move.
  window.animateMove = function (boardEl, from, to, renderFn) {
    if (!boardEl || !from || !to || typeof renderFn !== "function") {
      if (typeof renderFn === "function") renderFn();
      return;
    }
    const fromRect = rectAt(boardEl, from);
    renderFn();
    if (!fromRect) return;
    playFlip(boardEl, [{ from, to }]);
  };

  // Public API: animate two simultaneous moves (e.g. castling).
  window.animatePair = function (boardEl, moves, renderFn) {
    if (!boardEl || !Array.isArray(moves) || typeof renderFn !== "function") {
      if (typeof renderFn === "function") renderFn();
      return;
    }
    // Rects have to be captured BEFORE render for all moves.
    const captured = moves.map(({ from, to }) => ({
      from,
      to,
      fromRect: rectAt(boardEl, from),
    }));
    renderFn();
    const usable = captured.filter((m) => m.fromRect);
    if (!usable.length) return;
    playFlip(
      boardEl,
      usable.map(({ from, to }) => ({ from, to })),
    );
  };
})();
