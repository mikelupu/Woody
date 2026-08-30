// Shared move-list panel with two-column PGN table + history scrubber.
//
// Each board (tactics, pawn) instantiates one panel with an onJump callback
// that repaints the board to the FEN of the currently-viewed ply. The panel
// owns `history` (starting frame + one entry per played ply) and `viewIndex`
// (which frame is currently displayed). While `viewIndex < history.length - 1`
// the board is "viewing history" — callers should lock interaction; when the
// user returns to the tail the board is "live" again.
//
// Public API:
//   const panel = new window.MovesPanel({ container, onJump });
//   panel.reset({ startingFen, startingFullmove, startingTurn });
//   panel.push({ uci, san, fen });
//   panel.jump(index);  panel.prev();  panel.next();
//   panel.first();      panel.last();
//   panel.isLive();     panel.currentFen();
//
// onJump(fen, { isLive, index }) is fired whenever the viewed frame changes.
"use strict";

(function () {
  class MovesPanel {
    constructor({ container, onJump }) {
      this.container = container;
      this.onJump = typeof onJump === "function" ? onJump : () => {};
      this.history = [];
      this.viewIndex = -1;
      this.startingFullmove = 1;
      this.startingTurn = "white";
      this._buildDom();
    }

    // Discard current history and seed a fresh starting frame.
    reset({ startingFen, startingFullmove = 1, startingTurn = "white" } = {}) {
      if (!startingFen) return;
      this.startingFullmove = Number(startingFullmove) || 1;
      this.startingTurn = startingTurn === "black" ? "black" : "white";
      this.history = [
        {
          ply: 0,
          fen: startingFen,
          uci: null,
          san: null,
          moveNumber: this.startingFullmove,
          side: this.startingTurn,
        },
      ];
      this.viewIndex = 0;
      this._render();
      this.onJump(startingFen, { isLive: true, index: 0 });
    }

    // Append one ply. `fen` must be the FEN AFTER the move.
    push({ uci, san, fen }) {
      if (!this.history.length) return;
      const prev = this.history[this.history.length - 1];
      // Numbering: whichever side was "to move" in the previous frame owns this ply.
      const side = this._sideAfter(prev);
      const moveNumber = this._moveNumberAfter(prev);
      this.history.push({
        ply: this.history.length,
        fen: fen ?? prev.fen,
        uci: uci ?? null,
        san: san ?? uci ?? "?",
        moveNumber,
        side,
      });
      // Auto-advance the view only if we're already live.
      const wasLive = this.viewIndex === this.history.length - 2;
      if (wasLive) this.viewIndex = this.history.length - 1;
      this._render();
      if (wasLive) {
        const frame = this.history[this.viewIndex];
        this.onJump(frame.fen, { isLive: true, index: this.viewIndex });
      }
    }

    jump(index) {
      if (!this.history.length) return;
      const target = Math.max(0, Math.min(this.history.length - 1, Number(index) || 0));
      if (target === this.viewIndex) return;
      this.viewIndex = target;
      this._render();
      const frame = this.history[target];
      this.onJump(frame.fen, { isLive: this.isLive(), index: target });
    }

    prev() { this.jump(this.viewIndex - 1); }
    next() { this.jump(this.viewIndex + 1); }
    first() { this.jump(0); }
    last() { this.jump(this.history.length - 1); }

    isLive() {
      return this.viewIndex === this.history.length - 1;
    }

    currentFen() {
      return this.history[this.viewIndex]?.fen ?? null;
    }

    // ── internals ────────────────────────────────────────────────────

    _sideAfter(prev) {
      // If prev.ply === 0 (starting frame), the side to play is prev.side.
      // If prev.ply > 0, the side after prev is the opposite of prev.side.
      if (prev.ply === 0) return prev.side;
      return prev.side === "white" ? "black" : "white";
    }

    _moveNumberAfter(prev) {
      if (prev.ply === 0) return prev.moveNumber;
      // Whenever a black move is pushed, the fullmove counter increments.
      return prev.side === "black" ? prev.moveNumber + 1 : prev.moveNumber;
    }

    _buildDom() {
      this.container.classList.add("moves-panel");
      this.container.innerHTML = `
        <div class="moves-panel-header">
          <h2>Moves</h2>
          <div class="moves-panel-controls" role="group" aria-label="Move navigation">
            <button type="button" data-action="first" title="Starting position" aria-label="First">⏮</button>
            <button type="button" data-action="prev" title="Previous move" aria-label="Previous">◀</button>
            <button type="button" data-action="next" title="Next move" aria-label="Next">▶</button>
            <button type="button" data-action="last" title="Latest move" aria-label="Last">⏭</button>
          </div>
        </div>
        <div class="moves-panel-scroll" role="region" aria-label="Move list">
          <table class="moves-panel-table">
            <thead><tr><th class="num">#</th><th>White</th><th>Black</th></tr></thead>
            <tbody></tbody>
          </table>
          <p class="moves-panel-empty" hidden>No moves yet.</p>
        </div>
      `;
      this.tbody = this.container.querySelector("tbody");
      this.emptyEl = this.container.querySelector(".moves-panel-empty");
      this.controls = this.container.querySelector(".moves-panel-controls");
      this.scroll = this.container.querySelector(".moves-panel-scroll");
      this.container.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-action]");
        if (btn) {
          this._onAction(btn.dataset.action);
          return;
        }
        const cell = event.target.closest("td[data-ply]");
        if (cell) {
          this.jump(Number(cell.dataset.ply));
        }
      });
      this._render();
    }

    _onAction(action) {
      if (action === "first") this.first();
      else if (action === "prev") this.prev();
      else if (action === "next") this.next();
      else if (action === "last") this.last();
    }

    _render() {
      if (!this.tbody) return;
      // Group plies into rows keyed by moveNumber, one column per side.
      const rows = new Map();
      for (let i = 1; i < this.history.length; i += 1) {
        const frame = this.history[i];
        if (!rows.has(frame.moveNumber)) rows.set(frame.moveNumber, { white: null, black: null });
        rows.get(frame.moveNumber)[frame.side] = frame;
      }
      // If the puzzle starts with black to move, we need to render the first
      // row with an ellipsis in the white column.
      if (this.startingTurn === "black" && this.history.length > 1) {
        const first = rows.get(this.startingFullmove);
        if (first && !first.white) first.white = { placeholder: true };
      }
      const rowFragments = [];
      for (const [moveNumber, cells] of rows) {
        const w = cells.white;
        const b = cells.black;
        const isActive = (frame) => frame && !frame.placeholder && frame.ply === this.viewIndex;
        const cellFor = (frame) => {
          if (!frame) return "<td></td>";
          if (frame.placeholder) return `<td class="placeholder">…</td>`;
          const active = frame.ply === this.viewIndex ? " active" : "";
          return `<td class="ply${active}" data-ply="${frame.ply}">${frame.san || frame.uci || ""}</td>`;
        };
        void isActive;  // (helper used inline above)
        rowFragments.push(`
          <tr>
            <td class="num">${moveNumber}.</td>
            ${cellFor(w)}
            ${cellFor(b)}
          </tr>
        `);
      }
      this.tbody.innerHTML = rowFragments.join("");
      const isEmpty = this.history.length <= 1;
      this.emptyEl.hidden = !isEmpty;
      this.scroll.querySelector("table").hidden = isEmpty;
      // Enable/disable nav buttons.
      const canPrev = this.viewIndex > 0;
      const canNext = this.viewIndex < this.history.length - 1;
      this._setEnabled("first", canPrev);
      this._setEnabled("prev", canPrev);
      this._setEnabled("next", canNext);
      this._setEnabled("last", canNext);
      // Scroll active row into view.
      const active = this.tbody.querySelector("td.ply.active");
      if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
    }

    _setEnabled(action, enabled) {
      const btn = this.controls.querySelector(`[data-action="${action}"]`);
      if (btn) btn.disabled = !enabled;
    }
  }

  window.MovesPanel = MovesPanel;
})();
