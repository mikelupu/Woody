"use strict";

const glyphs = {
  P: "♟", N: "♞", B: "♝", R: "♜", Q: "♛", K: "♚",
  p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
};
const pieceNames = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };

const state = {
  puzzle: null,
  pieces: new Map(),
  scope: "side_to_move",
  hanging: new Set(),
  locked: false,
  startedAt: 0,
};

const board = document.querySelector("#board");
const status = document.querySelector("#board-status");
const submit = document.querySelector("#submit");
const next = document.querySelector("#next");

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

function eligible(symbol) {
  if (!symbol || symbol.toLowerCase() === "k") return false;
  const color = symbol === symbol.toUpperCase() ? "white" : "black";
  const effective = state.scope === "side_to_move" ? state.puzzle.side_to_move : state.scope;
  return effective === "both" || effective === color;
}

function orderedSquares() {
  const white = state.puzzle.side_to_move === "white";
  const files = white ? [..."abcdefgh"] : [..."hgfedcba"];
  const ranks = white ? [..."87654321"] : [..."12345678"];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

function labelFor(square, symbol) {
  if (!symbol) return `${square}, empty`;
  const color = symbol === symbol.toUpperCase() ? "White" : "Black";
  const marks = [];
  if (state.hanging.has(square)) marks.push("selected hanging");
  return `${square}, ${color} ${pieceNames[symbol.toLowerCase()]}${marks.length ? `, ${marks.join(", ")}` : ""}`;
}

function renderBoard() {
  board.replaceChildren();
  const squares = orderedSquares();
  squares.forEach((square, index) => {
    const symbol = state.pieces.get(square);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `square ${(Number(square[1]) + "abcdefgh".indexOf(square[0])) % 2 ? "light" : "dark"}`;
    if (state.hanging.has(square)) button.classList.add("hanging");
    if (symbol) button.classList.add(symbol === symbol.toUpperCase() ? "piece-white" : "piece-black");
    button.dataset.square = square;
    if (index >= 56) button.dataset.file = square[0];
    if (index % 8 === 0) button.dataset.rank = square[1];
    button.textContent = glyphs[symbol] || "";
    button.setAttribute("role", "gridcell");
    button.setAttribute("aria-label", labelFor(square, symbol));
    button.disabled = state.locked || !eligible(symbol);
    button.addEventListener("click", () => toggleSquare(square));
    button.addEventListener("keydown", navigateBoard);
    board.append(button);
  });
}

function navigateBoard(event) {
  const deltas = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 8, ArrowUp: -8 };
  if (!(event.key in deltas)) return;
  event.preventDefault();
  const controls = [...board.querySelectorAll(".square")];
  const target = controls[controls.indexOf(event.currentTarget) + deltas[event.key]];
  if (target) target.focus();
}

function toggleSquare(square) {
  if (state.hanging.has(square)) state.hanging.delete(square);
  else state.hanging.add(square);
  renderBoard();
}

function resetPuzzle(puzzle) {
  state.puzzle = puzzle;
  state.pieces = parseFen(puzzle.presented_fen);
  state.scope = "side_to_move";
  state.hanging.clear();
  state.locked = false;
  state.startedAt = performance.now();
  document.querySelectorAll("[data-scope]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.scope === state.scope)));
  document.querySelector("#position-meta").textContent = `${puzzle.side_to_move === "white" ? "White" : "Black"} to move · Rating ${puzzle.rating ?? "—"}`;
  const identity = document.querySelector("#puzzle-identity");
  identity.textContent = puzzle.source_url?.startsWith("https://lichess.org/")
    ? `Lichess puzzle ID ${puzzle.puzzle_id}`
    : `Puzzle ID ${puzzle.puzzle_id}`;
  document.querySelector("#feedback").hidden = true;
  submit.disabled = false;
  next.disabled = true;
  status.textContent = "Select every hanging piece, then check your answer.";
  renderBoard();
}

async function loadPuzzle() {
  submit.disabled = true;
  next.disabled = true;
  status.textContent = "Loading position…";
  try {
    const previous = state.puzzle?.puzzle_id;
    const url = `/api/v1/puzzles/next${previous ? `?previous_id=${encodeURIComponent(previous)}` : ""}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(await errorMessage(response));
    resetPuzzle(await response.json());
  } catch (error) {
    status.textContent = `Could not load a puzzle: ${error.message}`;
  }
}

function setScope(scope) {
  state.scope = scope;
  document.querySelectorAll("[data-scope]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.scope === scope)));
  for (const selected of [...state.hanging]) {
    if (!eligible(state.pieces.get(selected))) state.hanging.delete(selected);
  }
  renderBoard();
}

async function checkAnswer() {
  submit.disabled = true;
  status.textContent = "Saving and checking your answer…";
  const payload = {
    attempt_id: crypto.randomUUID(),
    presentation_id: state.puzzle.presentation_id,
    scope: state.scope,
    hanging: [...state.hanging].sort(),
    completion_ms: Math.max(0, Math.round(performance.now() - state.startedAt)),
  };
  try {
    const response = await fetch("/api/v1/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error(await errorMessage(response));
    const result = await response.json();
    state.locked = true;
    renderReview(result);
    updateStats(result.statistics);
    await loadHistory();
    next.disabled = false;
  } catch (error) {
    submit.disabled = false;
    status.textContent = `${error.message} Your selections were preserved.`;
  }
}

function renderReview(result) {
  renderBoard();
  const details = [];
  for (const outcome of ["correct", "missed", "incorrect"]) {
    for (const square of result.feedback.hanging[outcome]) {
      board.querySelector(`[data-square="${square}"]`)?.classList.add(outcome);
      const symbol = state.pieces.get(square);
      const color = symbol === symbol.toUpperCase() ? "White" : "Black";
      details.push(`${color} ${pieceNames[symbol.toLowerCase()]} on ${square}: ${outcome === "incorrect" ? "incorrect extra" : outcome}`);
    }
  }
  const feedback = document.querySelector("#feedback");
  feedback.hidden = false;
  feedback.className = `feedback ${result.point_awarded ? "good" : "bad"}`;
  document.querySelector("#feedback-summary").textContent = result.point_awarded ? "Exact hanging set. One point earned." : "No point this time. Review the marked pieces.";
  const list = document.querySelector("#feedback-list");
  list.replaceChildren(...details.map((text) => { const item = document.createElement("li"); item.textContent = text; return item; }));
  status.textContent = "Answer committed. Review the markers or continue.";
  feedback.focus();
}

function updateStats(stats) {
  document.querySelector("#score").textContent = stats.score;
  document.querySelector("#attempts").textContent = stats.attempts;
  document.querySelector("#accuracy").textContent = `${Math.round(stats.accuracy * 100)}%`;
  document.querySelector("#streak").textContent = stats.current_streak;
  document.querySelector("#best-streak").textContent = stats.best_streak;
  document.querySelector("#average-time").textContent = formatDuration(stats.average_completion_ms);
  document.querySelector("#average-duration").textContent = formatDuration(stats.average_completion_ms);
  document.querySelector("#recent-duration").textContent = formatDuration(stats.most_recent_completion_ms);
}

function formatDuration(milliseconds) {
  return milliseconds == null ? "—" : `${(milliseconds / 1000).toFixed(1)}s`;
}

async function loadStats() {
  const response = await fetch("/api/v1/stats");
  if (response.ok) updateStats(await response.json());
}

async function loadHistory() {
  const response = await fetch("/api/v1/attempts?limit=10");
  if (!response.ok) return;
  const { attempts } = await response.json();
  const body = document.querySelector("#history");
  if (!attempts.length) return;
  body.replaceChildren(...attempts.map((attempt) => {
    const row = document.createElement("tr");
    const cells = [attempt.puzzle_id, attempt.scope.replaceAll("_", " "), attempt.point_awarded ? "✓ Point" : "No point", formatDuration(attempt.completion_ms)];
    row.append(...cells.map((text) => { const cell = document.createElement("td"); cell.textContent = text; return cell; }));
    return row;
  }));
}

async function errorMessage(response) {
  try { return (await response.json()).error.message; }
  catch { return `Request failed (${response.status})`; }
}

document.querySelectorAll("[data-scope]").forEach((button) => button.addEventListener("click", () => setScope(button.dataset.scope)));
submit.addEventListener("click", checkAnswer);
next.addEventListener("click", loadPuzzle);
Promise.all([loadPuzzle(), loadStats(), loadHistory()]);
