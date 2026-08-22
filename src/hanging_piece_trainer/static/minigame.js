"use strict";

const glyphs = {
  N: "♘", B: "♗", R: "♖", Q: "♕",
  n: "♞", b: "♝", r: "♜", q: "♛",
};
const pieceNames = { n: "knight", b: "bishop", r: "rook", q: "queen" };
const values = { n: 3, b: 3, r: 5, q: 9 };
const startingPairs = ["RQ", "RN", "NB", "BQ", "NQ"];
const spawnKinds = ["N", "B", "R", "Q"];
const FILES = "abcdefgh";
const BLACK_MOVE_DELAY_MS = 450;
const BEST_KEY = "minigame_best";

const state = {
  pieces: new Map(),
  turn: "w",
  scores: { w: 0, b: 0 },
  selected: null,
  legalTargets: [],
  active: false,
  startedAt: 0,
  durationMs: 120000,
  timerId: null,
  aiTimeoutId: null,
};

const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#board-status");
const timerEl = document.querySelector("#timer");
const scoreWhiteEl = document.querySelector("#score-white");
const scoreBlackEl = document.querySelector("#score-black");
const bestScoreEl = document.querySelector("#best-score");
const startBtn = document.querySelector("#start");
const durationEl = document.querySelector("#duration");
const configDialog = document.querySelector("#config-dialog");
const configOpenBtn = document.querySelector("#config-open");
const configCancelBtn = document.querySelector("#config-cancel");
let durationBeforeEdit = durationEl.value;

function isWhite(symbol) { return symbol === symbol.toUpperCase(); }
function sameColor(a, b) { return isWhite(a) === isWhite(b); }

function coord(square) {
  return [FILES.indexOf(square[0]), Number(square[1]) - 1];
}
function square(file, rank) {
  return `${FILES[file]}${rank + 1}`;
}

function legalMoves(pieces, from, symbol) {
  const [f, r] = coord(from);
  const kind = symbol.toLowerCase();
  const moves = [];
  const slide = (df, dr) => {
    for (let i = 1; i < 8; i += 1) {
      const nf = f + df * i;
      const nr = r + dr * i;
      if (nf < 0 || nf > 7 || nr < 0 || nr > 7) return;
      const target = square(nf, nr);
      const other = pieces.get(target);
      if (!other) { moves.push(target); continue; }
      if (!sameColor(symbol, other)) moves.push(target);
      return;
    }
  };
  const jump = (df, dr) => {
    const nf = f + df;
    const nr = r + dr;
    if (nf < 0 || nf > 7 || nr < 0 || nr > 7) return;
    const target = square(nf, nr);
    const other = pieces.get(target);
    if (!other || !sameColor(symbol, other)) moves.push(target);
  };
  if (kind === "n") {
    for (const [df, dr] of [[1, 2], [2, 1], [-1, 2], [-2, 1], [1, -2], [2, -1], [-1, -2], [-2, -1]]) jump(df, dr);
    return moves;
  }
  const rook = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const bishop = [[1, 1], [1, -1], [-1, 1], [-1, -1]];
  const dirs = kind === "r" ? rook : kind === "b" ? bishop : [...rook, ...bishop];
  for (const [df, dr] of dirs) slide(df, dr);
  return moves;
}

function allLegalMoves(pieces, color) {
  const white = color === "w";
  const out = [];
  for (const [from, symbol] of pieces) {
    if (isWhite(symbol) !== white) continue;
    for (const to of legalMoves(pieces, from, symbol)) {
      const captured = pieces.get(to);
      out.push({ from, to, value: captured ? values[captured.toLowerCase()] : 0 });
    }
  }
  return out;
}

function randomEmptySquare(pieces, ranks) {
  const options = [];
  for (const f of FILES) for (const r of ranks) {
    const sq = `${f}${r}`;
    if (!pieces.has(sq)) options.push(sq);
  }
  return options.length ? options[Math.floor(Math.random() * options.length)] : null;
}

function pick(list) { return list[Math.floor(Math.random() * list.length)]; }

function initGame() {
  clearInterval(state.timerId);
  clearTimeout(state.aiTimeoutId);
  state.pieces = new Map();
  state.turn = "w";
  state.scores = { w: 0, b: 0 };
  state.selected = null;
  state.legalTargets = [];
  state.durationMs = Number(durationEl.value) * 1000;

  const whitePair = [...pick(startingPairs)];
  const blackPair = [...pick(startingPairs)];
  const whiteRanks = ["1", "2", "3"];
  const blackRanks = ["6", "7", "8"];
  for (const kind of whitePair) {
    const sq = randomEmptySquare(state.pieces, whiteRanks);
    if (sq) state.pieces.set(sq, kind);
  }
  for (const kind of blackPair) {
    const sq = randomEmptySquare(state.pieces, blackRanks);
    if (sq) state.pieces.set(sq, kind.toLowerCase());
  }

  state.active = true;
  state.startedAt = performance.now();
  state.timerId = setInterval(tick, 100);
  startBtn.textContent = "Restart";
  statusEl.textContent = "Your move. Click a white piece to see legal targets.";
  render();
  updateScore();
  tick();
}

function tick() {
  const remaining = Math.max(0, state.durationMs - (performance.now() - state.startedAt));
  const secs = Math.ceil(remaining / 1000);
  timerEl.textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  timerEl.classList.toggle("timer-warn", remaining <= 15000 && state.active);
  if (remaining <= 0 && state.active) endGame();
}

function endGame() {
  state.active = false;
  clearInterval(state.timerId);
  clearTimeout(state.aiTimeoutId);
  state.selected = null;
  state.legalTargets = [];
  const prevBest = Number(localStorage.getItem(BEST_KEY) || 0);
  const best = Math.max(prevBest, state.scores.w);
  localStorage.setItem(BEST_KEY, String(best));
  bestScoreEl.textContent = best;
  const improved = state.scores.w > prevBest;
  statusEl.textContent = improved
    ? `Time up. Final white score ${state.scores.w} — new best!`
    : `Time up. Final white score ${state.scores.w}. Best remains ${best}.`;
  render();
}

function applyMove(from, to) {
  const piece = state.pieces.get(from);
  const captured = state.pieces.get(to);
  state.pieces.delete(from);
  state.pieces.set(to, piece);
  if (captured) {
    const mover = isWhite(piece) ? "w" : "b";
    state.scores[mover] += values[captured.toLowerCase()] || 0;
    spawnPiece(isWhite(captured) ? "w" : "b");
  }
  state.turn = state.turn === "w" ? "b" : "w";
  updateScore();
}

function spawnPiece(color) {
  const sq = randomEmptySquare(state.pieces, "12345678");
  if (!sq) return;
  const kind = pick(spawnKinds);
  state.pieces.set(sq, color === "w" ? kind : kind.toLowerCase());
}

function handleSquareClick(sq) {
  if (!state.active || state.turn !== "w") return;
  const piece = state.pieces.get(sq);
  if (state.selected && state.legalTargets.includes(sq)) {
    applyMove(state.selected, sq);
    state.selected = null;
    state.legalTargets = [];
    render();
    if (state.active) scheduleBlackMove();
    return;
  }
  if (piece && isWhite(piece)) {
    state.selected = sq;
    state.legalTargets = legalMoves(state.pieces, sq, piece);
    if (!state.legalTargets.length) {
      statusEl.textContent = `The ${pieceNames[piece.toLowerCase()]} on ${sq} has no legal moves.`;
    } else {
      statusEl.textContent = "Click a highlighted square to move there.";
    }
    render();
    return;
  }
  state.selected = null;
  state.legalTargets = [];
  render();
}

function scheduleBlackMove() {
  statusEl.textContent = "Black is thinking…";
  state.aiTimeoutId = setTimeout(doBlackMove, BLACK_MOVE_DELAY_MS);
}

function doBlackMove() {
  if (!state.active) return;
  const options = allLegalMoves(state.pieces, "b");
  if (!options.length) {
    spawnPiece("b");
    state.turn = "w";
    statusEl.textContent = "Black had no legal move and spawned a new piece. Your move.";
    render();
    return;
  }
  const best = Math.max(...options.map((o) => o.value));
  const chosen = pick(options.filter((o) => o.value === best));
  const captured = state.pieces.get(chosen.to);
  applyMove(chosen.from, chosen.to);
  const capturedText = captured
    ? ` and captured your ${pieceNames[captured.toLowerCase()]} on ${chosen.to}`
    : "";
  statusEl.textContent = `Black moved ${chosen.from}→${chosen.to}${capturedText}. Your move.`;
  render();
  if (state.active && !allLegalMoves(state.pieces, "w").length) {
    spawnPiece("w");
    statusEl.textContent = "You had no legal move — a new white piece spawned. Continue.";
    render();
  }
}

function render() {
  boardEl.replaceChildren();
  for (let rank = 8; rank >= 1; rank -= 1) {
    for (let fileIdx = 0; fileIdx < 8; fileIdx += 1) {
      const sq = `${FILES[fileIdx]}${rank}`;
      const symbol = state.pieces.get(sq);
      const button = document.createElement("button");
      button.type = "button";
      const light = (rank + fileIdx) % 2 !== 0;
      button.className = `square ${light ? "light" : "dark"}`;
      if (state.selected === sq) button.classList.add("selected");
      if (state.legalTargets.includes(sq)) {
        button.classList.add("legal");
        if (symbol) button.classList.add("capture");
      }
      button.dataset.square = sq;
      button.textContent = symbol ? glyphs[symbol] : "";
      button.setAttribute("role", "gridcell");
      button.setAttribute("aria-label", squareLabel(sq, symbol));
      button.disabled = !state.active;
      button.addEventListener("click", () => handleSquareClick(sq));
      boardEl.append(button);
    }
  }
}

function squareLabel(sq, symbol) {
  if (!symbol) return `${sq}, empty`;
  const color = isWhite(symbol) ? "White" : "Black";
  return `${sq}, ${color} ${pieceNames[symbol.toLowerCase()]}`;
}

function updateScore() {
  scoreWhiteEl.textContent = state.scores.w;
  scoreBlackEl.textContent = state.scores.b;
}

startBtn.addEventListener("click", initGame);

configOpenBtn.addEventListener("click", () => {
  durationBeforeEdit = durationEl.value;
  configDialog.showModal();
});
configCancelBtn.addEventListener("click", () => configDialog.close("cancel"));
configDialog.addEventListener("close", () => {
  if (configDialog.returnValue !== "save") {
    durationEl.value = durationBeforeEdit;
  }
  showConfiguredTime();
});

function showConfiguredTime() {
  if (state.active) return;
  const secs = Number(durationEl.value);
  timerEl.textContent = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
}

bestScoreEl.textContent = Number(localStorage.getItem(BEST_KEY) || 0);
showConfiguredTime();
render();
