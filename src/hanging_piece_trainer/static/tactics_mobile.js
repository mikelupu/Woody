"use strict";

const SLUG = document.body.dataset.slug || null;
const PREVIEW_BATCH = document.body.dataset.previewBatch || null;
const BACK_URL = document.body.dataset.backUrl || "/tactics/packages";
const IS_PREVIEW_BATCH = PREVIEW_BATCH !== null;
const API_BASE = IS_PREVIEW_BATCH
  ? "/api/v1/tactics/preview"
  : `/api/v1/tactics/${encodeURIComponent(SLUG)}`;

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
  hintsUsed: 0,
  pieceHint: false,
  pieceHintSquare: null,
  playedSan: [],
  startingFullmove: 1,
  startingTurn: "white",
  // Review-mode navigation (populated on completion). fenSequence[0] is the
  // starting position; fenSequence[i] is the FEN after solution move i.
  fenSequence: [],
  expectedUci: [],
  viewIndex: 0,
};

const batchState = { total: 0, index: 0 };

const screenEl = document.querySelector("#screen");
const boardEl = document.querySelector("#board");
const statusEl = document.querySelector("#board-status");

const turnLabelEl = document.querySelector("#turn-label");
const turnDotEl = document.querySelector("#turn-dot");
const hintChipsEl = document.querySelector("#hint-chips");

const detailsEl = document.querySelector("#details");
const closeDetailsBtn = document.querySelector("#close-details");
const detailSideEl = document.querySelector("#detail-side");
const detailSideDotEl = document.querySelector("#detail-side-dot");
const detailRatingChip = document.querySelector("#detail-rating-chip");
const detailRatingEl = document.querySelector("#detail-rating");
const detailLichessEl = document.querySelector("#detail-lichess");
const detailOpeningRow = document.querySelector("#detail-opening-row");
const detailOpeningName = document.querySelector("#detail-opening-name");
const themeChipsEl = document.querySelector("#theme-chips");
const movesTableEl = document.querySelector("#moves-table");
const navFirstBtn = document.querySelector("#nav-first");
const navPrevBtn = document.querySelector("#nav-prev");
const navNextBtn = document.querySelector("#nav-next");
const navLastBtn = document.querySelector("#nav-last");

const prevBtn = document.querySelector("#prev-btn");
const hintBtn = document.querySelector("#hint-btn");
const hintLabelEl = document.querySelector("#hint-label");
const showAnswerBtn = document.querySelector("#show-answer");
const showAnswerLabel = document.querySelector("#show-answer-label");
const nextBtn = document.querySelector("#next-btn");

const puzzlePosEl = document.querySelector("#puzzle-position");
const puzzleTotalEl = document.querySelector("#puzzle-total");
const batchPosEl = document.querySelector("#batch-position");
const batchTotalEl = document.querySelector("#batch-total");

const celebrateEl = document.querySelector("#celebrate");
const celebrateNextBtn = document.querySelector("#celebrate-next");
const celebrateDismissBtn = document.querySelector("#celebrate-dismiss");
const celebrateStars = document.querySelector("#celebrate-stars");
const celebratePoints = document.querySelector("#celebrate-points");
const celebrateSolved = document.querySelector("#celebrate-solved");
const celebrateEarned = document.querySelector("#celebrate-earned");
const celebratePossibleEl = document.querySelector("#celebrate-possible");
const celebrateAccuracy = document.querySelector("#celebrate-accuracy");

const promotionDialog = document.querySelector("#promotion-dialog");
const promotionCancel = document.querySelector("#promotion-cancel");

// ---------- FEN + orientation ----------

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
  const white = state.puzzle?.side_to_move !== "black";
  const files = white ? [..."abcdefgh"] : [..."hgfedcba"];
  const ranks = white ? [..."87654321"] : [..."12345678"];
  return ranks.flatMap((rank) => files.map((file) => `${file}${rank}`));
}

function isLightSquare(square) {
  const file = "abcdefgh".indexOf(square[0]);
  const rank = Number(square[1]) - 1;
  return (file + rank) % 2 === 1;
}

function ownColor(symbol) {
  if (!symbol) return null;
  return symbol === symbol.toUpperCase() ? "white" : "black";
}

function isOwnPiece(square) {
  const symbol = state.pieces.get(square);
  if (!symbol) return false;
  return ownColor(symbol) === state.puzzle?.side_to_move;
}

function targetInfoFor(toSquare) {
  if (!state.selected) return null;
  const list = state.legalTargets[state.selected] || [];
  const matches = list.filter((entry) => entry.to === toSquare);
  return matches.length ? matches : null;
}

// ---------- board render ----------

function renderBoard() {
  boardEl.replaceChildren();
  const squares = orientationSquares();
  squares.forEach((square, index) => {
    const symbol = state.pieces.get(square);
    const button = document.createElement("button");
    button.type = "button";
    button.className = `sq ${isLightSquare(square) ? "light" : "dark"}`;
    button.dataset.square = square;
    if (index >= 56) button.dataset.file = square[0];
    if (index % 8 === 0) button.dataset.rank = square[1];
    button.setAttribute("role", "gridcell");
    if (symbol) button.innerHTML = pieceSvg(symbol);
    if (state.selected === square) button.classList.add("selected");
    if (state.selected && targetInfoFor(square) !== null) {
      button.classList.add("legal");
      if (symbol) {
        button.classList.add("capture");
        const ring = document.createElement("span");
        ring.className = "ring";
        button.append(ring);
      }
    }
    if (state.lastMove && (state.lastMove.from === square || state.lastMove.to === square)) {
      button.classList.add("last");
    }
    if (state.pieceHintSquare === square) button.classList.add("piece-hint");
    button.disabled = state.locked;
    button.addEventListener("click", () => handleSquareClick(square));
    boardEl.append(button);
  });
}

function flashWrong(from, to) {
  for (const square of [from, to]) {
    const el = boardEl.querySelector(`[data-square="${square}"]`);
    if (!el) continue;
    el.classList.add("wrong-flash");
    setTimeout(() => el.classList.remove("wrong-flash"), 400);
  }
}

// ---------- interaction ----------

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

function pickPromotion() {
  return new Promise((resolve) => {
    let resolved = null;
    const onClick = (event) => {
      const button = event.target.closest("button[type=submit]");
      if (!button) return;
      resolved = button.value;
    };
    const onCancel = () => { resolved = null; promotionDialog.close(); };
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

async function attemptMove(from, to, matches) {
  let promotion = null;
  const promotionOptions = matches.map((entry) => entry.promotion).filter((v) => v !== null);
  if (promotionOptions.length) {
    promotion = await pickPromotion();
    if (promotion === null) return;
  }
  const uci = `${from}${to}${promotion ?? ""}`;
  state.locked = true;
  showStatus("Checking your move…");
  try {
    const response = await fetch(`${API_BASE}/moves`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, uci }),
    });
    const data = await response.json();
    if (!response.ok) {
      showStatus(data.error?.message ?? "Move rejected.");
      state.locked = false;
      renderBoard();
      return;
    }
    if (!data.correct) {
      state.wrongMoves = data.wrong_moves;
      flashWrong(from, to);
      state.locked = false;
      showStatus(data.reason === "illegal" ? "That move isn't legal here." : "Not the solution — try again.");
      renderBoard();
      return;
    }
    state.playedSan.push(data.user_san);
    applyMoveOnBoard(from, to, promotion);
    state.selected = null;
    state.lastMove = { from, to };
    renderBoard();
    if (data.opponent_move) {
      showStatus("Correct! Opponent replies…");
      await sleep(OPPONENT_DELAY_MS);
      const oppFrom = data.opponent_move.slice(0, 2);
      const oppTo = data.opponent_move.slice(2, 4);
      applyUciOnBoard(data.opponent_move);
      state.lastMove = { from: oppFrom, to: oppTo };
      state.playedSan.push(data.opponent_san);
    }
    state.pieces = parseFen(data.presented_fen);
    state.legalTargets = data.legal_targets ?? {};
    state.locked = data.completed;
    if (data.completed) completePuzzle(data);
    else clearStatus();
    renderBoard();
  } catch (error) {
    showStatus(`Network error: ${error.message}`);
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

// ---------- puzzle lifecycle ----------

async function loadPuzzle() {
  resetPuzzleState();
  nextBtn.disabled = true;
  prevBtn.disabled = true;
  hintBtn.disabled = true;
  showAnswerBtn.disabled = true;
  showAnswerBtn.classList.remove("active");
  showAnswerLabel.textContent = "Show answer";
  screenEl.classList.remove("details-open");
  showStatus("Loading puzzle…");
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
      response = await fetch(`${API_BASE}/batch/${encodeURIComponent(PREVIEW_BATCH)}/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index: batchState.index }),
      });
    } else {
      const previous = state.previousPuzzleId;
      const url = `${API_BASE}/puzzles/next${previous ? `?previous_id=${encodeURIComponent(previous)}` : ""}`;
      response = await fetch(url);
    }
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    state.puzzle = data;
    state.pieces = parseFen(data.presented_fen);
    state.sessionId = data.session_id;
    state.legalTargets = data.legal_targets ?? {};
    state.startingFullmove = data.starting_fullmove ?? 1;
    state.startingTurn = data.starting_turn ?? data.side_to_move ?? "white";
    state.locked = false;
    showAnswerBtn.disabled = false;
    hintBtn.disabled = !(data.themes || []).length && !IS_PREVIEW_BATCH ? true : IS_PREVIEW_BATCH;
    // Preview batch has no hint endpoint — keep hint disabled there.
    if (IS_PREVIEW_BATCH) hintBtn.disabled = true;
    updateTopBar(data.batch);
    renderTurnStrip();
    renderHintChips();
    renderThemeChips();
    renderOpening();
    populateDetailsChips(data);
    updateHintButton();
    renderMovesTable([], null);
    clearStatus();
    renderBoard();
  } catch (error) {
    showStatus(`Could not load a puzzle: ${error.message}`);
  }
}

function resetPuzzleState() {
  state.pieces = new Map();
  state.legalTargets = {};
  state.selected = null;
  state.lastMove = null;
  state.locked = true;
  state.completed = false;
  state.wrongMoves = 0;
  state.hintsUsed = 0;
  state.pieceHint = false;
  state.pieceHintSquare = null;
  state.playedSan = [];
  state.fenSequence = [];
  state.expectedUci = [];
  state.viewIndex = 0;
  updateNavButtons();
}

function completePuzzle(data) {
  state.completed = true;
  state.locked = true;
  if (state.puzzle && data.rating != null) state.puzzle.rating = data.rating;
  state.previousPuzzleId = state.puzzle?.puzzle_id ?? state.previousPuzzleId;
  populateDetailsChips({ ...state.puzzle, ...data });
  const solutionSan = data.expected_moves_san ?? [];
  state.fenSequence = data.fen_sequence ?? [];
  state.expectedUci = data.expected_moves ?? [];
  // Land on the final position so the user sees the completed solution first.
  state.viewIndex = Math.max(0, state.fenSequence.length - 1);
  syncBoardToView();
  renderMovesTable(solutionSan, state.viewIndex);
  updateNavButtons();
  clearPieceHint();
  updateHintButton();
  showAnswerBtn.disabled = false;
  showAnswerBtn.classList.add("active");
  showAnswerLabel.textContent = "Hide answer";
  screenEl.classList.add("details-open");
  nextBtn.disabled = false;
  clearStatus();
  if (IS_PREVIEW_BATCH && batchState.index >= batchState.total - 1) {
    nextBtn.textContent = "Done";
  }
  if (!IS_PREVIEW_BATCH && data.batch) updateTopBar(data.batch);
  if (!IS_PREVIEW_BATCH && data.batch_completed && data.batch_result) {
    showCelebration(data.batch_result);
  }
}

// ---------- solution navigation (post-completion) ----------

function jumpToIndex(target) {
  if (!state.completed || !state.fenSequence.length) return;
  const clamped = Math.max(0, Math.min(state.fenSequence.length - 1, target | 0));
  if (clamped === state.viewIndex) return;
  state.viewIndex = clamped;
  syncBoardToView();
  const solutionSan = state.puzzle && state.expectedUci.length
    ? extractSanFromRender()
    : [];
  // Re-render the moves table only if we can — but the simpler path is to
  // toggle the active class on existing cells.
  markActivePlyCell(clamped);
  updateNavButtons();
  void solutionSan;
}

function extractSanFromRender() {
  // Read SAN back from the table cells so we don't have to store a separate copy.
  return [...movesTableEl.querySelectorAll("td.ply:not(.placeholder)")]
    .map((td) => td.textContent);
}

function markActivePlyCell(viewIndex) {
  movesTableEl.querySelectorAll("td.ply.active").forEach((td) => td.classList.remove("active"));
  // View index 0 is the starting position (no ply highlighted); ply index i
  // corresponds to viewIndex i in fenSequence.
  if (viewIndex <= 0) return;
  const cell = movesTableEl.querySelector(`td.ply[data-ply="${viewIndex}"]`);
  if (cell) {
    cell.classList.add("active");
    cell.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
}

function syncBoardToView() {
  const fen = state.fenSequence[state.viewIndex];
  if (!fen) return;
  state.pieces = parseFen(fen);
  state.selected = null;
  // Highlight the move that landed us here (from previous frame).
  if (state.viewIndex > 0) {
    const uci = state.expectedUci[state.viewIndex - 1];
    if (uci) state.lastMove = { from: uci.slice(0, 2), to: uci.slice(2, 4) };
    else state.lastMove = null;
  } else {
    state.lastMove = null;
  }
  renderBoard();
}

function updateNavButtons() {
  const active = state.completed && state.fenSequence.length > 1;
  const canPrev = active && state.viewIndex > 0;
  const canNext = active && state.viewIndex < state.fenSequence.length - 1;
  navFirstBtn.disabled = !canPrev;
  navPrevBtn.disabled = !canPrev;
  navNextBtn.disabled = !canNext;
  navLastBtn.disabled = !canNext;
}

async function revealAnswer() {
  if (!state.sessionId || state.completed) return;
  showAnswerBtn.disabled = true;
  showStatus("Revealing the solution…");
  try {
    const response = await fetch(`${API_BASE}/reveal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    const data = await response.json();
    if (!response.ok) {
      showStatus(data.error?.message ?? "Could not reveal.");
      showAnswerBtn.disabled = false;
      return;
    }
    state.locked = true;
    completePuzzle(data);
  } catch (error) {
    showStatus(`Network error: ${error.message}`);
    showAnswerBtn.disabled = false;
  }
}

async function requestHint() {
  if (!state.sessionId || state.completed || IS_PREVIEW_BATCH) return;
  hintBtn.disabled = true;
  try {
    const type = state.hintsUsed < (state.puzzle?.themes || []).length ? "theme" : "piece";
    const response = await fetch(`${API_BASE}/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, type }),
    });
    const data = await response.json();
    if (!response.ok) {
      showStatus(data.error?.message ?? "Could not fetch hint.");
      updateHintButton();
      return;
    }
    state.hintsUsed = data.hints_used;
    state.pieceHint = data.piece_hint;
    state.pieceHintSquare = data.piece_square || null;
    renderHintChips();
    renderThemeChips();
    if (state.pieceHint) renderBoard();  // repaint to apply .piece-hint
  } catch (error) {
    showStatus(`Hint error: ${error.message}`);
  } finally {
    updateHintButton();
  }
}

function clearPieceHint() {
  state.pieceHintSquare = null;
  boardEl.querySelectorAll(".sq.piece-hint").forEach((el) => el.classList.remove("piece-hint"));
}

// ---------- UI updates ----------

function updateHintButton() {
  const themes = state.puzzle?.themes || [];
  const themesLeft = themes.length - state.hintsUsed;
  if (state.completed || IS_PREVIEW_BATCH) {
    hintBtn.disabled = true;
    hintLabelEl.textContent = "Hint";
    return;
  }
  if (themesLeft > 0) {
    hintBtn.disabled = false;
    hintLabelEl.textContent = `Hint · ${themesLeft}`;
  } else if (!state.pieceHint) {
    hintBtn.disabled = false;
    hintLabelEl.textContent = "Show piece";
  } else {
    hintBtn.disabled = true;
    hintLabelEl.textContent = "No hints";
  }
}

function renderTurnStrip() {
  if (!state.puzzle) return;
  const white = state.puzzle.side_to_move !== "black";
  turnLabelEl.textContent = white ? "White to move" : "Black to move";
  turnDotEl.classList.toggle("b", !white);
}

function renderHintChips() {
  hintChipsEl.replaceChildren();
  const themes = state.puzzle?.themes || [];
  const revealed = Math.min(state.hintsUsed, themes.length);
  for (let i = 0; i < revealed; i += 1) {
    const chip = document.createElement("span");
    chip.className = "hint-chip";
    chip.innerHTML =
      '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M9 21h6v-1H9v1Zm3-19a7 7 0 0 0-4 12.7V17a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2.3A7 7 0 0 0 12 2Z"/></svg>' +
      `<span>${escapeHtml(themes[i])}</span>`;
    hintChipsEl.append(chip);
  }
}

function renderThemeChips() {
  themeChipsEl.replaceChildren();
  const themes = state.puzzle?.themes || [];
  themes.forEach((theme, index) => {
    const chip = document.createElement("span");
    chip.className = "chip theme" + (index < state.hintsUsed ? " used" : "");
    chip.textContent = theme;
    themeChipsEl.append(chip);
  });
}

function renderOpening() {
  const opening = state.puzzle?.opening;
  if (opening) {
    detailOpeningName.textContent = opening;
    detailOpeningRow.hidden = false;
  } else {
    detailOpeningRow.hidden = true;
  }
}

function populateDetailsChips(data) {
  const white = data.side_to_move !== "black";
  detailSideEl.textContent = white ? "White to move" : "Black to move";
  detailSideDotEl.classList.toggle("b", !white);
  if (data.rating != null) {
    detailRatingEl.textContent = data.rating;
    detailRatingChip.hidden = false;
  } else {
    detailRatingChip.hidden = true;
  }
  const puzzleId = data.puzzle_id ?? state.puzzle?.puzzle_id ?? null;
  if (puzzleId) {
    detailLichessEl.hidden = false;
    detailLichessEl.textContent = `lichess/${puzzleId} ↗`;
    detailLichessEl.href = data.source_url ?? state.puzzle?.source_url
      ?? `https://lichess.org/training/${puzzleId}`;
  } else {
    detailLichessEl.hidden = true;
  }
}

function renderMovesTable(sanMoves, activeViewIndex) {
  movesTableEl.replaceChildren();
  if (!sanMoves.length) return;
  // `sanMoves` are 0-indexed; `data-ply` uses the fen_sequence index (1-based
  // because index 0 is the starting position).
  let sanIndex = 0;
  let fullmove = state.startingFullmove;
  if (state.startingTurn === "black") {
    const row = document.createElement("tr");
    row.append(
      makeCell("num", `${fullmove}.`),
      makePlaceholder(),
      makePlyCell(sanMoves[sanIndex], sanIndex + 1, activeViewIndex),
    );
    movesTableEl.append(row);
    sanIndex += 1;
    fullmove += 1;
  }
  while (sanIndex < sanMoves.length) {
    const row = document.createElement("tr");
    row.append(
      makeCell("num", `${fullmove}.`),
      makePlyCell(sanMoves[sanIndex], sanIndex + 1, activeViewIndex),
    );
    if (sanIndex + 1 < sanMoves.length) {
      row.append(makePlyCell(sanMoves[sanIndex + 1], sanIndex + 2, activeViewIndex));
    } else {
      row.append(makePlaceholder("—"));
    }
    movesTableEl.append(row);
    sanIndex += 2;
    fullmove += 1;
  }
}

function makeCell(cls, text) {
  const td = document.createElement("td");
  td.className = cls;
  td.textContent = text;
  return td;
}

function makePlyCell(text, plyViewIndex, activeViewIndex) {
  const td = document.createElement("td");
  td.className = "ply" + (plyViewIndex === activeViewIndex ? " active" : "");
  td.dataset.ply = String(plyViewIndex);
  td.textContent = text;
  return td;
}

function makePlaceholder(text = "…") {
  const td = document.createElement("td");
  td.className = "ply placeholder";
  td.textContent = text;
  return td;
}

function updateTopBar(batch) {
  if (IS_PREVIEW_BATCH) {
    puzzlePosEl.textContent = String(batchState.index + 1);
    puzzleTotalEl.textContent = String(batchState.total);
    batchPosEl.textContent = "1";
    batchTotalEl.textContent = "1";
    return;
  }
  if (!batch) return;
  puzzlePosEl.textContent = String(batch.position ?? 1);
  puzzleTotalEl.textContent = String(batch.batch_size ?? 5);
  batchPosEl.textContent = String((batch.index ?? 0) + 1);
  batchTotalEl.textContent = String(batch.total_batches ?? 20);
}

// ---------- details panel ----------

function openDetails() {
  screenEl.classList.add("details-open");
  showAnswerBtn.classList.add("active");
  showAnswerLabel.textContent = "Hide answer";
}
function closeDetails() {
  screenEl.classList.remove("details-open");
  showAnswerBtn.classList.remove("active");
  showAnswerLabel.textContent = "Show answer";
}
function toggleDetails() {
  if (screenEl.classList.contains("details-open")) closeDetails();
  else openDetails();
}

// ---------- celebration ----------

function computeStars(pct) {
  if (pct >= 100) return "★★★★★";
  if (pct >= 80) return "★★★★☆";
  if (pct >= 60) return "★★★☆☆";
  if (pct >= 40) return "★★☆☆☆";
  if (pct > 0) return "★☆☆☆☆";
  return "☆☆☆☆☆";
}

function showCelebration(result) {
  const per = result.per_puzzle_points ?? [];
  const solved = per.filter((p) => p > 0).length;
  const total = per.length || 5;
  const earned = result.points_earned ?? 0;
  const possible = result.points_possible ?? 0;
  const pct = possible ? Math.round((earned / possible) * 100) : 0;
  celebrateStars.textContent = computeStars(pct);
  celebratePoints.textContent = String(earned);
  celebrateSolved.textContent = `${solved}/${total}`;
  celebrateEarned.textContent = String(earned);
  celebratePossibleEl.textContent = String(possible);
  celebrateAccuracy.textContent = `${pct}%`;
  celebrateEl.classList.add("show");
}
function hideCelebration() { celebrateEl.classList.remove("show"); }

// ---------- next / prev ----------

function onNextClick() {
  hideCelebration();
  if (IS_PREVIEW_BATCH) {
    batchState.index += 1;
    if (batchState.index >= batchState.total) {
      window.location.href = "/tactics/packages/new";
      return;
    }
  }
  loadPuzzle();
}

// ---------- status text ----------

function showStatus(text) { statusEl.textContent = text; statusEl.hidden = false; }
function clearStatus() { statusEl.textContent = ""; statusEl.hidden = true; }

// ---------- misc helpers ----------

function sleep(ms) { return new Promise((resolve) => setTimeout(resolve, ms)); }
async function errorMessage(response) {
  try { return (await response.json()).error.message; }
  catch { return `Request failed (${response.status})`; }
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]
  ));
}

// ---------- wire events ----------

showAnswerBtn.addEventListener("click", () => {
  if (state.completed) { toggleDetails(); return; }
  revealAnswer();
});
closeDetailsBtn.addEventListener("click", closeDetails);
hintBtn.addEventListener("click", requestHint);
nextBtn.addEventListener("click", onNextClick);
prevBtn.addEventListener("click", () => { /* review-mode not yet supported on this page */ });
celebrateNextBtn.addEventListener("click", onNextClick);
celebrateDismissBtn.addEventListener("click", hideCelebration);
document.querySelector("#more-btn").addEventListener("click", () => {
  window.location.href = BACK_URL;
});

// Move-navigation buttons + click-to-jump on ply cells.
navFirstBtn.addEventListener("click", () => jumpToIndex(0));
navPrevBtn.addEventListener("click", () => jumpToIndex(state.viewIndex - 1));
navNextBtn.addEventListener("click", () => jumpToIndex(state.viewIndex + 1));
navLastBtn.addEventListener("click", () => jumpToIndex(state.fenSequence.length - 1));
movesTableEl.addEventListener("click", (event) => {
  const cell = event.target.closest("td.ply[data-ply]");
  if (!cell || cell.classList.contains("placeholder")) return;
  jumpToIndex(Number(cell.dataset.ply));
});

loadPuzzle();
