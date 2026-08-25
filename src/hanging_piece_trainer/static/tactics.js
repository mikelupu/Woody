"use strict";

const pieceNames = { p: "pawn", n: "knight", b: "bishop", r: "rook", q: "queen", k: "king" };
const pieceSvg = (symbol) => (window.PIECES && symbol ? window.PIECES[symbol] || "" : "");
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
  review: null,  // { fens, san, uci, index, startingFullmove, startingTurn }
};

const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#board-status");
const nextBtn = document.querySelector("#next");
const promotionDialog = document.querySelector("#promotion-dialog");
const promotionCancel = document.querySelector("#promotion-cancel");
const settingsDialog = document.querySelector("#settings-dialog");
const settingsOpenBtn = document.querySelector("#settings-open");
const showRatingInput = document.querySelector("#setting-show-rating");
const showMaxPointsInput = document.querySelector("#setting-show-max-points");
const showAnswerBtn = document.querySelector("#show-answer");
const reviewBar = document.querySelector("#review-bar");
const reviewStartBtn = document.querySelector("#review-start");
const reviewPrevBtn = document.querySelector("#review-prev");
const reviewNextBtn = document.querySelector("#review-next");
const reviewEndBtn = document.querySelector("#review-end");
const reviewIndicator = document.querySelector("#review-indicator");

const SETTINGS_KEYS = { showRating: "tactics.showRating", showMaxPoints: "tactics.showMaxPoints" };
const settings = {
  showRating: localStorage.getItem(SETTINGS_KEYS.showRating) === "true",
  showMaxPoints: localStorage.getItem(SETTINGS_KEYS.showMaxPoints) !== "false",
};

function formatMoveSequence(sanMoves, startingFullmove, startingTurn) {
  const parts = [];
  let moveNumber = startingFullmove;
  let index = 0;
  // If black is to move first, print "N... move" then start a new full move.
  if (startingTurn === "black" && sanMoves.length) {
    parts.push(`${moveNumber}… ${sanMoves[index]}`);
    index += 1;
    moveNumber += 1;
  }
  while (index < sanMoves.length) {
    const whiteMove = sanMoves[index];
    const blackMove = sanMoves[index + 1];
    parts.push(blackMove ? `${moveNumber}. ${whiteMove} ${blackMove}` : `${moveNumber}. ${whiteMove}`);
    index += 2;
    moveNumber += 1;
  }
  return parts.join("  ");
}

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
  const points = data.puzzle_points ?? 0;
  const fullPoints = state.puzzle?.batch?.full_points ?? 0;
  const feedback = document.querySelector("#feedback");
  feedback.hidden = false;
  feedback.className = `feedback ${points === fullPoints ? "good" : points > 0 ? "warn" : "bad"}`;
  const wrongLabel = state.wrongMoves === 0
    ? "No mistakes."
    : `${state.wrongMoves} mistake${state.wrongMoves === 1 ? "" : "s"}.`;
  document.querySelector("#feedback-heading").textContent =
    points === fullPoints
      ? `Clean solve. +${points} pts.`
      : points > 0
        ? `Half credit. +${points} / ${fullPoints} pts.`
        : `No points this puzzle. (${wrongLabel})`;
  const san = data.expected_moves_san?.length
    ? formatMoveSequence(
        data.expected_moves_san,
        data.starting_fullmove ?? 1,
        data.starting_turn ?? "white",
      )
    : (data.expected_moves ?? []).join(" ");
  const solutionEl = document.querySelector("#feedback-summary");
  solutionEl.textContent = "";
  const label = document.createElement("strong");
  label.textContent = "Solution: ";
  const body = document.createElement("span");
  body.className = "move-sequence";
  body.textContent = san;
  solutionEl.append(label, body);
  const batch = data.batch ?? {};
  document.querySelector("#feedback-detail").textContent =
    `Batch ${batch.index + 1} progress: ${batch.points_earned} / ${batch.points_possible}`;
  statusEl.textContent = "Puzzle complete.";
  updateBatch(batch);
  // Reveal rating in the aside now that the puzzle is over, regardless of setting.
  const ratingRow = document.querySelector("#rating-row");
  if (ratingRow) ratingRow.hidden = false;
  showAnswerBtn.disabled = true;
  // Also reveal the rating badge in state.puzzle so review indicator can be seeded.
  if (state.puzzle && data.rating != null) state.puzzle.rating = data.rating;
  enterReview(data);
  nextBtn.disabled = false;
  nextBtn.focus();
  if (data.batch_completed && data.batch_result) {
    showBatchDialog(data.batch_result);
  }
}

function updateBatch(batch) {
  if (!batch) return;
  const earnedText = settings.showMaxPoints
    ? `${batch.points_earned} / ${batch.points_possible}`
    : `${batch.points_earned}`;
  document.querySelector("#batch-earned").textContent = earnedText;
  document.querySelector("#batch-position").textContent =
    `${(batch.index ?? 0) + 1} / ${batch.total_batches ?? 20}${batch.cycle ? ` · c${batch.cycle}` : ""}`;
  document.querySelector("#puzzle-position").textContent =
    `${batch.position ?? 1} / ${batch.batch_size ?? 5}`;
  document.querySelector("#puzzle-full-points").textContent =
    settings.showRating && batch.full_points != null ? `${batch.full_points} pts` : "—";
}

function updatePuzzleDetails(data) {
  const puzzleLink = document.querySelector("#puzzle-link");
  const puzzleId = data.puzzle_id ?? "—";
  puzzleLink.textContent = puzzleId;
  puzzleLink.href = data.source_url ?? `https://lichess.org/training/${puzzleId}`;
  document.querySelector("#detail-side").textContent =
    data.side_to_move === "white" ? "White to move" : "Black to move";
  const ratingRow = document.querySelector("#rating-row");
  document.querySelector("#detail-rating").textContent = data.rating ?? "—";
  ratingRow.hidden = !settings.showRating;
}

function showBatchDialog(result) {
  const dialog = document.querySelector("#batch-dialog");
  const scoreText = settings.showMaxPoints
    ? `${result.points_earned} / ${result.points_possible} pts`
    : `${result.points_earned} pts`;
  document.querySelector("#batch-summary").textContent =
    `Batch ${result.index + 1}${result.cycle ? ` (cycle ${result.cycle + 1})` : ""}: ${scoreText}`;
  const list = document.querySelector("#batch-breakdown");
  list.replaceChildren(
    ...(result.per_puzzle_points ?? []).map((points, index) => {
      const li = document.createElement("li");
      const puzzleId = (result.puzzle_ids ?? [])[index] ?? `#${index + 1}`;
      li.textContent = `Puzzle ${index + 1} (${puzzleId}): ${points} pts`;
      return li;
    }),
  );
  dialog.showModal();
}

function applySettingsToDom() {
  const ratingRow = document.querySelector("#rating-row");
  if (ratingRow) ratingRow.hidden = !settings.showRating;
  if (state.puzzle) {
    updatePuzzleDetails(state.puzzle);
    if (state.puzzle.batch) updateBatch(state.puzzle.batch);
  }
}

function openSettings() {
  showRatingInput.checked = settings.showRating;
  showMaxPointsInput.checked = settings.showMaxPoints;
  settingsDialog.showModal();
}

function saveSettings() {
  settings.showRating = showRatingInput.checked;
  settings.showMaxPoints = showMaxPointsInput.checked;
  localStorage.setItem(SETTINGS_KEYS.showRating, String(settings.showRating));
  localStorage.setItem(SETTINGS_KEYS.showMaxPoints, String(settings.showMaxPoints));
  applySettingsToDom();
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
  exitReview();
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
      `${data.side_to_move === "white" ? "White" : "Black"} to move`;
    updatePuzzleDetails(data);
    updateBatch(data.batch);
    state.locked = false;
    showAnswerBtn.disabled = false;
    statusEl.textContent = "Your move — click one of your pieces.";
    renderBoard();
  } catch (error) {
    statusEl.textContent = `Could not load a puzzle: ${error.message}`;
  }
}

async function errorMessage(response) {
  try { return (await response.json()).error.message; }
  catch { return `Request failed (${response.status})`; }
}

function enterReview(data) {
  const fens = data.fen_sequence ?? [];
  if (!fens.length) return;
  state.review = {
    fens,
    san: data.expected_moves_san ?? [],
    uci: data.expected_moves ?? [],
    index: 0,
    startingFullmove: data.starting_fullmove ?? 1,
    startingTurn: data.starting_turn ?? "white",
  };
  reviewBar.hidden = false;
  applyReviewFrame();
}

function applyReviewFrame() {
  const r = state.review;
  if (!r) return;
  const fen = r.fens[r.index];
  state.pieces = parseFen(fen);
  state.selected = null;
  state.legalTargets = {};
  // Highlight the last move played to reach the current position.
  if (r.index > 0) {
    const uci = r.uci[r.index - 1] ?? "";
    state.lastMove = uci.length >= 4 ? { from: uci.slice(0, 2), to: uci.slice(2, 4) } : null;
  } else {
    state.lastMove = null;
  }
  renderBoard();
  updateReviewIndicator();
  reviewStartBtn.disabled = r.index === 0;
  reviewPrevBtn.disabled = r.index === 0;
  reviewNextBtn.disabled = r.index >= r.fens.length - 1;
  reviewEndBtn.disabled = r.index >= r.fens.length - 1;
}

function updateReviewIndicator() {
  const r = state.review;
  if (!r) return;
  if (r.index === 0) {
    reviewIndicator.textContent = "Starting position";
    return;
  }
  // Compute a "3. Nf3" or "27… Ne2+" style label for the current move.
  const moveIdx = r.index - 1;
  const isBlackFirst = r.startingTurn === "black";
  let fullmove;
  let isBlackMove;
  if (isBlackFirst) {
    // moveIdx 0 → black at startingFullmove, moveIdx 1 → white at startingFullmove + 1, ...
    fullmove = r.startingFullmove + Math.floor((moveIdx + 1) / 2);
    isBlackMove = moveIdx % 2 === 0;
  } else {
    fullmove = r.startingFullmove + Math.floor(moveIdx / 2);
    isBlackMove = moveIdx % 2 === 1;
  }
  const san = r.san[moveIdx] ?? r.uci[moveIdx];
  const prefix = isBlackMove ? `${fullmove}…` : `${fullmove}.`;
  reviewIndicator.textContent = `${prefix} ${san}  ·  ${r.index} / ${r.fens.length - 1}`;
}

function exitReview() {
  state.review = null;
  reviewBar.hidden = true;
}

async function revealAnswer() {
  if (!state.sessionId || state.completed) return;
  showAnswerBtn.disabled = true;
  statusEl.textContent = "Revealing the solution…";
  try {
    const response = await fetch("/api/v1/tactics/reveal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    const data = await response.json();
    if (!response.ok) {
      statusEl.textContent = data.error?.message ?? "Could not reveal the answer.";
      showAnswerBtn.disabled = false;
      return;
    }
    state.locked = true;
    completePuzzle(data);
  } catch (error) {
    statusEl.textContent = `Network error: ${error.message}`;
    showAnswerBtn.disabled = false;
  }
}

function handleReviewKey(event) {
  if (!state.review) return;
  if (event.key === "ArrowLeft") { event.preventDefault(); stepReview(-1); }
  else if (event.key === "ArrowRight") { event.preventDefault(); stepReview(1); }
  else if (event.key === "Home") { event.preventDefault(); jumpReview(0); }
  else if (event.key === "End") { event.preventDefault(); jumpReview(state.review.fens.length - 1); }
}

function stepReview(delta) {
  const r = state.review;
  if (!r) return;
  jumpReview(Math.max(0, Math.min(r.fens.length - 1, r.index + delta)));
}

function jumpReview(index) {
  const r = state.review;
  if (!r) return;
  r.index = index;
  applyReviewFrame();
}

showAnswerBtn.addEventListener("click", revealAnswer);
reviewStartBtn.addEventListener("click", () => jumpReview(0));
reviewPrevBtn.addEventListener("click", () => stepReview(-1));
reviewNextBtn.addEventListener("click", () => stepReview(1));
reviewEndBtn.addEventListener("click", () => jumpReview(state.review ? state.review.fens.length - 1 : 0));
document.addEventListener("keydown", handleReviewKey);

nextBtn.addEventListener("click", loadPuzzle);
settingsOpenBtn.addEventListener("click", openSettings);
settingsDialog.addEventListener("close", saveSettings);
applySettingsToDom();
loadPuzzle();
