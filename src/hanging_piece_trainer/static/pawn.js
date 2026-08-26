"use strict";

const pieceNames = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };
const pieceSvg = (symbol) => (window.PIECES && symbol ? window.PIECES[symbol] || "" : "");
const OPPONENT_DELAY_MS = 350;

const state = {
  gameId: null,
  boardFen: null,
  pieces: new Map(),
  legalTargets: {},
  humanColor: "white",
  sideToMove: "white",
  variant: "kingless",
  elo: 1500,
  selected: null,
  lastMove: null,
  locked: true,
  gameOver: false,
};

const settings = {
  variant: "kingless",
  side: "white",
  elo: 1500,
};

const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#board-status");
const startBtn = document.querySelector("#start");
const whiteMaterialEl = document.querySelector("#white-material");
const blackMaterialEl = document.querySelector("#black-material");
const turnIndicatorEl = document.querySelector("#turn-indicator");
const eloBadgeEl = document.querySelector("#elo-badge");
const variantBadgeEl = document.querySelector("#variant-badge");

const configDialog = document.querySelector("#config-dialog");
const configOpenBtn = document.querySelector("#config-open");
const configCancelBtn = document.querySelector("#config-cancel");
const eloSlider = document.querySelector("#elo-slider");
const eloOut = document.querySelector("#elo-out");

const promotionDialog = document.querySelector("#promotion-dialog");
const promotionCancel = document.querySelector("#promotion-cancel");

function parseFen(fen, hideKings) {
  const pieces = new Map();
  fen.split(" ")[0].split("/").forEach((rankText, rankIndex) => {
    let file = 0;
    for (const symbol of rankText) {
      if (/\d/.test(symbol)) file += Number(symbol);
      else {
        if (!(hideKings && symbol.toLowerCase() === "k")) {
          pieces.set(`${"abcdefgh"[file]}${8 - rankIndex}`, symbol);
        }
        file += 1;
      }
    }
  });
  return pieces;
}

function orientationSquares() {
  const white = state.humanColor === "white";
  const files = white ? [..."abcdefgh"] : [..."hgfedcba"];
  const ranks = white ? [..."87654321"] : [..."12345678"];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

function ownColor(symbol) {
  if (!symbol) return null;
  return symbol === symbol.toUpperCase() ? "white" : "black";
}

function isOwnPiece(square) {
  const symbol = state.pieces.get(square);
  if (!symbol) return false;
  return ownColor(symbol) === state.humanColor;
}

function labelFor(square, symbol) {
  if (!symbol) return `${square}, empty`;
  const color = symbol === symbol.toUpperCase() ? "White" : "Black";
  return `${square}, ${color} ${pieceNames[symbol.toLowerCase()]}`;
}

function targetInfoFor(toSquare) {
  if (!state.selected) return null;
  const list = state.legalTargets[state.selected] || [];
  const matches = list.filter((entry) => entry.to === toSquare);
  return matches.length ? matches : null;
}

function renderBoard() {
  boardEl.replaceChildren();
  const squares = orientationSquares();
  squares.forEach((square, index) => {
    const symbol = state.pieces.get(square);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `square ${(Number(square[1]) + "abcdefgh".indexOf(square[0])) % 2 ? "light" : "dark"}`;
    button.dataset.square = square;
    if (index >= 56) button.dataset.file = square[0];
    if (index % 8 === 0) button.dataset.rank = square[1];
    button.innerHTML = pieceSvg(symbol);
    button.setAttribute("role", "gridcell");
    button.setAttribute("aria-label", labelFor(square, symbol));
    if (state.selected === square) button.classList.add("selected");
    if (state.selected && targetInfoFor(square) !== null) {
      button.classList.add("legal");
      if (symbol) button.classList.add("capture");
    }
    if (state.lastMove && (state.lastMove.from === square || state.lastMove.to === square)) {
      button.classList.add("last-move");
    }
    button.disabled = state.locked || state.gameOver;
    button.addEventListener("click", () => handleSquareClick(square));
    boardEl.append(button);
  });
}

async function handleSquareClick(square) {
  if (state.locked || state.gameOver) return;
  if (state.sideToMove !== state.humanColor) return;
  if (state.selected) {
    const matches = targetInfoFor(square);
    if (matches) {
      await attemptMove(state.selected, square, matches);
      return;
    }
    if (isOwnPiece(square)) {
      state.selected = square;
      renderBoard();
      return;
    }
    state.selected = null;
    renderBoard();
    return;
  }
  if (isOwnPiece(square)) {
    state.selected = square;
    renderBoard();
  }
}

async function attemptMove(from, to, matches) {
  let promotion = null;
  const needsPromotion = matches.some((entry) => entry.promotion !== null);
  if (needsPromotion) {
    promotion = await pickPromotion();
    if (promotion === null) return;
  }
  const uci = `${from}${to}${promotion ?? ""}`;
  state.locked = true;
  statusEl.textContent = "Checking your move…";
  try {
    const response = await fetch("/api/v1/pawn/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: state.gameId, uci }),
    });
    const data = await response.json();
    if (!response.ok) {
      statusEl.textContent = data.error?.message ?? "Move rejected.";
      state.locked = false;
      renderBoard();
      return;
    }
    if (!data.correct) {
      flashWrong(from, to);
      state.locked = false;
      statusEl.textContent = "That move isn't legal.";
      renderBoard();
      return;
    }
    // Apply user move visually
    applyMoveOnBoard(from, to, promotion);
    state.selected = null;
    state.lastMove = { from, to };
    window.animateMove(boardEl, from, to, renderBoard);
    // Opponent reply (if any)
    if (data.engine_move) {
      statusEl.textContent = "Stockfish is replying…";
      await sleep(OPPONENT_DELAY_MS);
      const engFrom = data.engine_move.slice(0, 2);
      const engTo = data.engine_move.slice(2, 4);
      applyUciOnBoard(data.engine_move);
      state.lastMove = { from: engFrom, to: engTo };
      window.animateMove(boardEl, engFrom, engTo, renderBoard);
    }
    // Reconcile with server state (authoritative)
    applySnapshot(data);
    if (state.gameOver) {
      showOutcome(data);
    } else {
      statusEl.textContent = "Your move.";
    }
    renderBoard();
  } catch (error) {
    statusEl.textContent = `Network error: ${error.message}`;
    state.locked = false;
    renderBoard();
  }
}

function applyMoveOnBoard(from, to, promotion) {
  const piece = state.pieces.get(from);
  if (!piece) return;
  state.pieces.delete(from);
  if (promotion) {
    const isWhitePiece = piece === piece.toUpperCase();
    state.pieces.set(to, isWhitePiece ? promotion.toUpperCase() : promotion);
  } else {
    state.pieces.set(to, piece);
  }
}

function applyUciOnBoard(uci) {
  const from = uci.slice(0, 2);
  const to = uci.slice(2, 4);
  const promotion = uci.length > 4 ? uci.slice(4) : null;
  applyMoveOnBoard(from, to, promotion);
}

function applySnapshot(data) {
  state.boardFen = data.board_fen;
  state.pieces = parseFen(data.board_fen, state.variant === "kingless");
  state.legalTargets = data.legal_targets ?? {};
  state.sideToMove = data.side_to_move;
  state.gameOver = data.game_over;
  state.locked = data.game_over || data.side_to_move !== state.humanColor;
  whiteMaterialEl.textContent = data.white_material;
  blackMaterialEl.textContent = data.black_material;
  turnIndicatorEl.textContent =
    data.game_over ? "—" : (data.side_to_move === state.humanColor ? "You" : "Stockfish");
}

function showOutcome(data) {
  let text;
  if (data.result === "draw") text = "Draw";
  else if (data.result === `${state.humanColor}_wins`) text = "You win!";
  else text = "Stockfish wins.";
  statusEl.textContent = `${text} — ${data.result_reason ?? ""}. Click Start to play again.`;
  startBtn.textContent = "Play again";
  startBtn.disabled = false;
}

function flashWrong(from, to) {
  for (const square of [from, to]) {
    const el = boardEl.querySelector(`[data-square="${square}"]`);
    if (!el) continue;
    el.classList.add("wrong-flash");
    setTimeout(() => el.classList.remove("wrong-flash"), 400);
  }
}

function pickPromotion() {
  return new Promise((resolve) => {
    let resolved = null;
    const onClick = (event) => {
      const button = event.target.closest("button[type=submit]");
      if (!button) return;
      resolved = button.value;
    };
    const onCancel = () => {
      resolved = null;
      promotionDialog.close();
    };
    const onClose = () => {
      promotionDialog.removeEventListener("click", onClick);
      promotionCancel.removeEventListener("click", onCancel);
      promotionDialog.removeEventListener("close", onClose);
      resolve(resolved);
    };
    promotionDialog.addEventListener("click", onClick);
    promotionCancel.addEventListener("click", onCancel);
    promotionDialog.addEventListener("close", onClose);
    promotionDialog.showModal();
  });
}

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }

async function startNewGame() {
  state.selected = null;
  state.lastMove = null;
  state.gameOver = false;
  state.locked = true;
  statusEl.textContent = "Starting new game…";
  startBtn.disabled = true;
  try {
    const response = await fetch("/api/v1/pawn/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        variant: settings.variant,
        elo: settings.elo,
        side: settings.side,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      statusEl.textContent = data.error?.message ?? "Could not start the game.";
      startBtn.disabled = false;
      return;
    }
    state.gameId = data.game_id;
    state.variant = data.variant;
    state.elo = data.elo;
    state.humanColor = data.human_color;
    applySnapshot(data);
    eloBadgeEl.textContent = data.elo;
    variantBadgeEl.textContent = data.variant === "kingless" ? "Kingless" : "With kings";
    startBtn.textContent = "Restart";
    startBtn.disabled = false;
    statusEl.textContent =
      state.sideToMove === state.humanColor
        ? "Your move. Click a pawn to see legal targets."
        : "Stockfish moved first. Your move next.";
    if (data.engine_move) {
      state.lastMove = {
        from: data.engine_move.slice(0, 2),
        to: data.engine_move.slice(2, 4),
      };
    }
    renderBoard();
  } catch (error) {
    statusEl.textContent = `Network error: ${error.message}`;
    startBtn.disabled = false;
  }
}

// ─── Settings dialog ──────────────────────────────────────────────

function openConfig() {
  document.querySelector(`input[name="variant"][value="${settings.variant}"]`).checked = true;
  document.querySelector(`input[name="side"][value="${settings.side}"]`).checked = true;
  eloSlider.value = String(settings.elo);
  eloOut.textContent = settings.elo;
  configDialog.showModal();
}

function saveConfig() {
  const variant = document.querySelector('input[name="variant"]:checked').value;
  const side = document.querySelector('input[name="side"]:checked').value;
  const elo = Number(eloSlider.value);
  settings.variant = variant;
  settings.side = side;
  settings.elo = elo;
  eloBadgeEl.textContent = elo;
  variantBadgeEl.textContent = variant === "kingless" ? "Kingless" : "With kings";
}

configOpenBtn.addEventListener("click", openConfig);
configCancelBtn.addEventListener("click", () => configDialog.close("cancel"));
configDialog.addEventListener("close", () => {
  if (configDialog.returnValue === "save") saveConfig();
});
eloSlider.addEventListener("input", () => { eloOut.textContent = eloSlider.value; });

startBtn.addEventListener("click", startNewGame);
renderBoard();
