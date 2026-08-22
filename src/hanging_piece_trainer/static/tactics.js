"use strict";

const glyphs = {
  P: "♙", N: "♘", B: "♗", R: "♖", Q: "♕", K: "♔",
  p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
};
const pieceNames = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };
const OPPONENT_DELAY_MS = 500;

const state = {
  puzzle: null,
  pieces: new Map(),
  legalTargets: {},
  sessionId: null,
  selected: null,
  lastMove: null,
  locked: false,
  completed: false,
  wrongMoves: 0,
};

const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#board-status");
const nextBtn = document.querySelector("#next");
const promotionDialog = document.querySelector("#promotion-dialog");
const promotionCancel = document.querySelector("#promotion-cancel");

function parseFen(fen) {
  const pieces = new Map();
  fen.split(" ")[0].split("/").forEach((rankText, rankIndex) => {
    let file = 0;
    for (const symbol of rankText) {
      if (/\d/.test(symbol)) file += Number(symbol);
      else {
        pieces.set(`${"abcdefgh"[file]}${8 - rankIndex}`, symbol);
        file += 1;
      }
    }
  });
  return pieces;
}

function orientationSquares() {
  const white = state.puzzle.side_to_move === "white";
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
  return ownColor(symbol) === state.puzzle.side_to_move;
}

function labelFor(square, symbol) {
  if (!symbol) return `${square}, empty`;
  const color = symbol === symbol.toUpperCase() ? "White" : "Black";
  return `${square}, ${color} ${pieceNames[symbol.toLowerCase()]}`;
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
    button.textContent = symbol ? glyphs[symbol] : "";
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
    button.disabled = state.locked;
    button.addEventListener("click", () => handleSquareClick(square));
    button.addEventListener("keydown", navigateBoard);
    boardEl.append(button);
  });
}

function navigateBoard(event) {
  const deltas = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 8, ArrowUp: -8 };
  if (!(event.key in deltas)) return;
  event.preventDefault();
  const controls = [...boardEl.querySelectorAll(".square")];
  const target = controls[controls.indexOf(event.currentTarget) + deltas[event.key]];
  if (target) target.focus();
}

function targetInfoFor(toSquare) {
  if (!state.selected) return null;
  const list = state.legalTargets[state.selected] || [];
  const matches = list.filter((entry) => entry.to === toSquare);
  return matches.length ? matches : null;
}

async function handleSquareClick(square) {
  if (state.locked || state.completed) return;
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
  const promotionOptions = matches
    .map((entry) => entry.promotion)
    .filter((value) => value !== null);
  if (promotionOptions.length) {
    promotion = await pickPromotion();
    if (promotion === null) return;
  }
  const uci = `${from}${to}${promotion ?? ""}`;
  state.locked = true;
  statusEl.textContent = "Checking your move…";
  try {
    const response = await fetch("/api/v1/tactics/moves", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, uci }),
    });
    const data = await response.json();
    if (!response.ok) {
      statusEl.textContent = data.error?.message ?? "Move rejected.";
      state.locked = false;
      renderBoard();
      return;
    }
    if (!data.correct) {
      state.wrongMoves = data.wrong_moves;
      flashWrong(from, to);
      state.locked = false;
      statusEl.textContent = data.reason === "illegal"
        ? "That move isn't legal here."
        : "Not the solution — try again.";
      renderBoard();
      return;
    }
    applyMoveOnBoard(from, to, promotion);
    state.selected = null;
    state.lastMove = { from, to };
    renderBoard();
    if (data.opponent_move) {
      statusEl.textContent = "Correct! Opponent replies…";
      await sleep(OPPONENT_DELAY_MS);
      applyUciOnBoard(data.opponent_move);
      state.lastMove = {
        from: data.opponent_move.slice(0, 2),
        to: data.opponent_move.slice(2, 4),
      };
      renderBoard();
    }
    state.pieces = parseFen(data.presented_fen);
    state.legalTargets = data.legal_targets ?? {};
    state.locked = data.completed;
    if (data.completed) {
      completePuzzle(data);
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
    const promoted = ownColor(piece) === "white" ? promotion.toUpperCase() : promotion;
    state.pieces.set(to, promoted);
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

function flashWrong(from, to) {
  for (const square of [from, to]) {
    const el = boardEl.querySelector(`[data-square="${square}"]`);
    if (!el) continue;
    el.classList.add("wrong-flash");
    setTimeout(() => el.classList.remove("wrong-flash"), 400);
  }
}

function completePuzzle(data) {
  state.completed = true;
  const feedback = document.querySelector("#feedback");
  feedback.hidden = false;
  feedback.className = `feedback ${data.point_awarded ? "good" : "bad"}`;
  document.querySelector("#feedback-heading").textContent = data.point_awarded
    ? "Solved cleanly. Point earned."
    : `Solved with ${state.wrongMoves} mistake${state.wrongMoves === 1 ? "" : "s"} — no point.`;
  document.querySelector("#feedback-summary").textContent = `Solution: ${(data.expected_moves ?? []).join(" ")}`;
  document.querySelector("#feedback-detail").textContent = `${data.statistics.attempts} solved · streak ${data.statistics.current_streak}`;
  statusEl.textContent = "Puzzle complete.";
  updateStats(data.statistics);
  nextBtn.disabled = false;
  nextBtn.focus();
}

function updateStats(stats) {
  document.querySelector("#score").textContent = stats.score;
  document.querySelector("#attempts").textContent = stats.attempts;
  document.querySelector("#accuracy").textContent = `${Math.round((stats.accuracy || 0) * 100)}%`;
  document.querySelector("#streak").textContent = stats.current_streak;
  document.querySelector("#best-streak").textContent = stats.best_streak;
  document.querySelector("#average-time").textContent = formatDuration(stats.average_completion_ms);
}

function formatDuration(milliseconds) {
  return milliseconds == null ? "—" : `${(milliseconds / 1000).toFixed(1)}s`;
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

async function loadPuzzle() {
  nextBtn.disabled = true;
  state.locked = true;
  state.completed = false;
  state.selected = null;
  state.lastMove = null;
  state.wrongMoves = 0;
  document.querySelector("#feedback").hidden = true;
  statusEl.textContent = "Loading puzzle…";
  try {
    const previous = state.puzzle?.puzzle_id;
    const url = `/api/v1/tactics/puzzles/next${previous ? `?previous_id=${encodeURIComponent(previous)}` : ""}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    state.puzzle = data;
    state.pieces = parseFen(data.presented_fen);
    state.sessionId = data.session_id;
    state.legalTargets = data.legal_targets ?? {};
    document.querySelector("#position-meta").textContent =
      `${data.side_to_move === "white" ? "White" : "Black"} to move · Rating ${data.rating ?? "—"}`;
    document.querySelector("#puzzle-identity").textContent =
      data.source_url?.startsWith("https://lichess.org/")
        ? `Lichess puzzle ${data.puzzle_id}`
        : `Puzzle ${data.puzzle_id}`;
    state.locked = false;
    statusEl.textContent = "Your move — click one of your pieces.";
    renderBoard();
  } catch (error) {
    statusEl.textContent = `Could not load a puzzle: ${error.message}`;
  }
}

async function loadStats() {
  const response = await fetch("/api/v1/tactics/stats");
  if (!response.ok) return;
  const stats = await response.json();
  updateStats(stats);
}

async function errorMessage(response) {
  try { return (await response.json()).error.message; }
  catch { return `Request failed (${response.status})`; }
}

nextBtn.addEventListener("click", loadPuzzle);
Promise.all([loadPuzzle(), loadStats()]);
