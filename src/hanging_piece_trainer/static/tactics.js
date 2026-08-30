"use strict";

const SLUG = document.body?.dataset?.slug ?? "tri-band-tactics";
const PREVIEW_ID = document.body?.dataset?.previewId ?? null;
const PREVIEW_BATCH = document.body?.dataset?.previewBatch ?? null;
const IS_PREVIEW_BATCH = PREVIEW_BATCH !== null;
const IS_PREVIEW = PREVIEW_ID !== null || IS_PREVIEW_BATCH;
const API_BASE = IS_PREVIEW
  ? "/api/v1/tactics/preview"
  : `/api/v1/tactics/${encodeURIComponent(SLUG)}`;

// Batch mode iterates through preview puzzle_ids; single-preview mode plays
// one puzzle only. Batch state is populated on first loadPuzzle() call.
const batchState = { total: 0, index: 0 };

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
const movesPanelEl = document.querySelector("#moves-panel");
let panel = null;

function panelOnJump(fen, { isLive }) {
  if (!fen || !state.puzzle) return;
  state.pieces = parseFen(fen);
  state.selected = null;
  state.legalTargets = isLive && !state.completed ? state.liveLegalTargets ?? {} : {};
  state.lastMove = null;
  state.locked = state.completed || !isLive;
  if (!isLive) statusEl.textContent = "Viewing history — jump to live to continue.";
  else if (!state.completed) statusEl.textContent = "Your move.";
  renderBoard();
}

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
    const response = await fetch(`${API_BASE}/moves`, {
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
    window.animateMove(boardEl, from, to, renderBoard);
    if (panel) panel.push({ uci, san: data.user_san, fen: data.fen_after_user });
    if (data.opponent_move) {
      statusEl.textContent = "Correct! Opponent replies…";
      await sleep(OPPONENT_DELAY_MS);
      const oppFrom = data.opponent_move.slice(0, 2);
      const oppTo = data.opponent_move.slice(2, 4);
      applyUciOnBoard(data.opponent_move);
      state.lastMove = { from: oppFrom, to: oppTo };
      window.animateMove(boardEl, oppFrom, oppTo, renderBoard);
      if (panel) {
        panel.push({
          uci: data.opponent_move,
          san: data.opponent_san,
          fen: data.fen_after_opponent,
        });
      }
    }
    state.pieces = parseFen(data.presented_fen);
    state.legalTargets = data.legal_targets ?? {};
    state.liveLegalTargets = state.legalTargets;
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
  const feedbackDetail = document.querySelector("#feedback-detail");
  if (IS_PREVIEW) {
    feedbackDetail.textContent =
      "Preview complete — save the package to record scores.";
  } else if (data.batch) {
    feedbackDetail.textContent =
      `Batch ${batch.index + 1} progress: ${batch.points_earned} / ${batch.points_possible}`;
  } else {
    feedbackDetail.textContent = "";
  }
  statusEl.textContent = "Puzzle complete.";
  if (!IS_PREVIEW) updateBatch(batch);
  // Reveal rating in the aside now that the puzzle is over, regardless of setting.
  const ratingRow = document.querySelector("#rating-row");
  if (ratingRow) ratingRow.hidden = false;
  showAnswerBtn.disabled = true;
  if (state.puzzle && data.rating != null) state.puzzle.rating = data.rating;
  populatePanelFromCompletion(data);
  nextBtn.disabled = false;
  if (IS_PREVIEW_BATCH && batchState.index >= batchState.total - 1) {
    nextBtn.textContent = "Back to search";
  }
  nextBtn.focus();
  if (!IS_PREVIEW && data.batch_completed && data.batch_result) {
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
  document.querySelector("#feedback").hidden = true;
  statusEl.textContent = "Loading puzzle…";
  try {
    let response;
    if (IS_PREVIEW_BATCH) {
      if (batchState.total === 0) {
        const meta = await fetch(`${API_BASE}/batch/${encodeURIComponent(PREVIEW_BATCH)}`);
        if (!meta.ok) throw new Error(await errorMessage(meta));
        const metaBody = await meta.json();
        batchState.total = metaBody.count;
        batchState.index = 0;
      }
      response = await fetch(
        `${API_BASE}/batch/${encodeURIComponent(PREVIEW_BATCH)}/start`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index: batchState.index }),
        },
      );
    } else if (IS_PREVIEW) {
      response = await fetch(`${API_BASE}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ puzzle_id: PREVIEW_ID }),
      });
    } else {
      const previous = state.puzzle?.puzzle_id;
      const url = `${API_BASE}/puzzles/next${previous ? `?previous_id=${encodeURIComponent(previous)}` : ""}`;
      response = await fetch(url);
    }
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    if (IS_PREVIEW_BATCH) updateBatchCounter();
    state.puzzle = data;
    state.pieces = parseFen(data.presented_fen);
    state.sessionId = data.session_id;
    state.legalTargets = data.legal_targets ?? {};
    state.liveLegalTargets = state.legalTargets;
    document.querySelector("#position-meta").textContent =
      `${data.side_to_move === "white" ? "White" : "Black"} to move`;
    updatePuzzleDetails(data);
    updateBatch(data.batch);
    state.locked = false;
    showAnswerBtn.disabled = false;
    statusEl.textContent = "Your move — click one of your pieces.";
    if (panel) {
      panel.reset({
        startingFen: data.presented_fen,
        startingFullmove: data.starting_fullmove ?? 1,
        startingTurn: data.starting_turn ?? data.side_to_move ?? "white",
      });
    }
    renderBoard();
  } catch (error) {
    statusEl.textContent = `Could not load a puzzle: ${error.message}`;
  }
}

async function errorMessage(response) {
  try { return (await response.json()).error.message; }
  catch { return `Request failed (${response.status})`; }
}

async function revealAnswer() {
  if (!state.sessionId || state.completed) return;
  showAnswerBtn.disabled = true;
  statusEl.textContent = "Revealing the solution…";
  try {
    const response = await fetch(`${API_BASE}/reveal`, {
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

function populatePanelFromCompletion(data) {
  if (!panel) return;
  const sanList = data.expected_moves_san ?? [];
  const uciList = data.expected_moves ?? [];
  const fens = data.fen_sequence ?? [];
  panel.reset({
    startingFen: fens[0] ?? state.puzzle?.presented_fen,
    startingFullmove: data.starting_fullmove ?? state.puzzle?.starting_fullmove ?? 1,
    startingTurn: data.starting_turn ?? state.puzzle?.starting_turn ?? "white",
  });
  for (let i = 0; i < uciList.length; i += 1) {
    panel.push({ uci: uciList[i], san: sanList[i], fen: fens[i + 1] });
  }
}

showAnswerBtn.addEventListener("click", revealAnswer);

function updateBatchCounter() {
  const cell = document.querySelector("#batch-position")?.parentElement?.parentElement;
  const value = document.querySelector("#batch-position");
  const label = cell?.querySelector(".label");
  if (!cell || !value) return;
  cell.removeAttribute("hidden");
  value.textContent = `${batchState.index + 1} / ${batchState.total}`;
  if (label) label.textContent = "Preview";
}

function nextPuzzleInBatch() {
  batchState.index += 1;
  if (batchState.index >= batchState.total) {
    window.location.href = "/tactics/packages/new";
    return;
  }
  loadPuzzle();
}

if (IS_PREVIEW) {
  // Hide the batch-progress stat cells in preview mode. Batch mode re-shows
  // the puzzle-position cell to repurpose it as a "Preview N / Total" counter.
  for (const id of ["batch-earned", "batch-position", "puzzle-position", "puzzle-full-points"]) {
    document.querySelector(`#${id}`)?.parentElement?.parentElement?.setAttribute("hidden", "");
  }
  if (IS_PREVIEW_BATCH) {
    nextBtn.textContent = "Next puzzle";
    nextBtn.addEventListener("click", nextPuzzleInBatch);
  } else {
    nextBtn.textContent = "Back to search";
    nextBtn.addEventListener("click", () => {
      window.location.href = "/tactics/packages/new";
    });
  }
} else {
  nextBtn.addEventListener("click", loadPuzzle);
}
settingsOpenBtn.addEventListener("click", openSettings);
settingsDialog.addEventListener("close", saveSettings);
applySettingsToDom();
if (movesPanelEl && window.MovesPanel) {
  panel = new window.MovesPanel({ container: movesPanelEl, onJump: panelOnJump });
}
loadPuzzle();
