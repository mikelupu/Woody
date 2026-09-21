"use strict";

const listEl = document.querySelector("#bookmark-list");
const countEl = document.querySelector("#bookmark-count");
const filterInput = document.querySelector("#filter-input");
const tagChipsEl = document.querySelector("#tag-chips");
const editDialog = document.querySelector("#edit-dialog");
const editInput = document.querySelector("#edit-tags");
const editCancelBtn = document.querySelector("#edit-cancel");
const editErrorEl = document.querySelector("#edit-error");
const editForm = editDialog?.querySelector("form");

const state = { bookmarks: [], filter: "", editingId: null };

async function loadBookmarks() {
  listEl.textContent = "";
  const loading = document.createElement("p");
  loading.className = "muted";
  loading.textContent = "Loading bookmarks…";
  listEl.append(loading);
  try {
    const response = await fetch("/api/v1/bookmarks");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.bookmarks = data.bookmarks ?? [];
    countEl.textContent = String(state.bookmarks.length);
    renderTagChips();
    renderList();
  } catch (error) {
    listEl.textContent = "";
    const msg = document.createElement("p");
    msg.className = "muted";
    msg.textContent = `Could not load bookmarks: ${error.message}`;
    listEl.append(msg);
  }
}

function renderTagChips() {
  if (!tagChipsEl) return;
  tagChipsEl.textContent = "";
  const seen = new Map();
  for (const b of state.bookmarks) {
    for (const tag of b.tags ?? []) {
      seen.set(tag, (seen.get(tag) ?? 0) + 1);
    }
  }
  const tags = [...seen.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (tags.length === 0) return;
  const all = document.createElement("button");
  all.type = "button";
  all.className = "tag-chip" + (state.filter === "" ? " active" : "");
  all.textContent = "All";
  all.addEventListener("click", () => setFilter(""));
  tagChipsEl.append(all);
  for (const [tag, count] of tags) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "tag-chip" + (state.filter === tag ? " active" : "");
    chip.textContent = `${tag} (${count})`;
    chip.addEventListener("click", () => setFilter(tag));
    tagChipsEl.append(chip);
  }
}

function setFilter(tag) {
  state.filter = tag;
  filterInput.value = tag;
  renderTagChips();
  renderList();
}

function currentMatches() {
  const needle = state.filter.trim().toLowerCase();
  if (!needle) return state.bookmarks;
  return state.bookmarks.filter((b) => (b.tags ?? []).some((t) => t.includes(needle)));
}

function renderList() {
  listEl.textContent = "";
  const rows = currentMatches();
  if (rows.length === 0) {
    const p = document.createElement("p");
    p.className = "muted";
    p.textContent = state.bookmarks.length === 0
      ? "You haven't bookmarked any puzzles yet. Solve a puzzle and press the bookmark icon to add one."
      : "No bookmarks match this tag.";
    listEl.append(p);
    return;
  }
  for (const b of rows) listEl.append(renderCard(b));
}

function renderCard(bookmark) {
  const card = document.createElement("article");
  card.className = "bookmark-card";

  const board = document.createElement("div");
  board.className = "mini-board";
  renderMiniBoard(board, bookmark.puzzle?.presented_fen ?? "");
  card.append(board);

  const body = document.createElement("div");
  body.className = "bookmark-body";

  const title = document.createElement("h3");
  title.className = "bookmark-title";
  title.textContent = bookmark.puzzle?.puzzle_id ?? bookmark.puzzle_id;
  body.append(title);

  const meta = document.createElement("p");
  meta.className = "muted bookmark-meta";
  const parts = [];
  parts.push(bookmark.source_package_title ?? bookmark.source_package);
  const puzzle = bookmark.puzzle ?? {};
  if (puzzle.rating != null) parts.push(`Rating ${puzzle.rating}`);
  if (puzzle.side_to_move) parts.push(`${puzzle.side_to_move === "white" ? "White" : "Black"} to move`);
  meta.textContent = parts.join(" · ");
  body.append(meta);

  const tagRow = document.createElement("div");
  tagRow.className = "tag-row";
  if ((bookmark.tags ?? []).length === 0) {
    const em = document.createElement("span");
    em.className = "muted";
    em.textContent = "no tags";
    tagRow.append(em);
  } else {
    for (const tag of bookmark.tags) {
      const chip = document.createElement("span");
      chip.className = "tag";
      chip.textContent = tag;
      tagRow.append(chip);
    }
  }
  body.append(tagRow);

  const actions = document.createElement("div");
  actions.className = "bookmark-actions";
  const openLink = document.createElement("a");
  openLink.className = "primary-link";
  openLink.href = `/tactics/preview/puzzle/${encodeURIComponent(bookmark.source_package)}/${encodeURIComponent(bookmark.puzzle_id)}`;
  openLink.textContent = "Open ▶";
  actions.append(openLink);

  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.textContent = "Edit tags";
  editBtn.addEventListener("click", () => openEditDialog(bookmark));
  actions.append(editBtn);

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "danger";
  delBtn.textContent = "Remove";
  delBtn.addEventListener("click", () => removeBookmark(bookmark));
  actions.append(delBtn);

  body.append(actions);
  card.append(body);
  return card;
}

function renderMiniBoard(container, fen) {
  container.textContent = "";
  const pieces = parseFen(fen);
  for (let rank = 8; rank >= 1; rank -= 1) {
    for (let fileIdx = 0; fileIdx < 8; fileIdx += 1) {
      const cell = document.createElement("div");
      const isLight = (fileIdx + rank) % 2 === 1;
      cell.className = `mini-cell ${isLight ? "light" : "dark"}`;
      const square = `${"abcdefgh"[fileIdx]}${rank}`;
      const symbol = pieces.get(square);
      if (symbol && window.PIECES && window.PIECES[symbol]) {
        cell.innerHTML = window.PIECES[symbol];
      }
      container.append(cell);
    }
  }
}

function parseFen(fen) {
  const map = new Map();
  if (!fen) return map;
  const board = fen.split(" ")[0];
  board.split("/").forEach((rankText, rankIndex) => {
    let file = 0;
    for (const symbol of rankText) {
      if (/\d/.test(symbol)) file += Number(symbol);
      else {
        map.set(`${"abcdefgh"[file]}${8 - rankIndex}`, symbol);
        file += 1;
      }
    }
  });
  return map;
}

function openEditDialog(bookmark) {
  state.editingId = bookmark.bookmark_id;
  editInput.value = (bookmark.tags ?? []).join(" ");
  editErrorEl.hidden = true;
  editErrorEl.textContent = "";
  editDialog.showModal();
  editInput.focus();
}

async function submitEdit(event) {
  event.preventDefault();
  if (state.editingId == null) return;
  const tagsText = editInput.value ?? "";
  try {
    const response = await fetch(`/api/v1/bookmarks/${encodeURIComponent(state.editingId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags: tagsText }),
    });
    const data = await response.json();
    if (!response.ok) {
      editErrorEl.textContent = data?.error?.message ?? "Could not save tags.";
      editErrorEl.hidden = false;
      return;
    }
    editDialog.close();
    state.editingId = null;
    await loadBookmarks();
  } catch (error) {
    editErrorEl.textContent = `Network error: ${error.message}`;
    editErrorEl.hidden = false;
  }
}

async function removeBookmark(bookmark) {
  const ok = window.confirm(`Remove bookmark for ${bookmark.puzzle_id}?`);
  if (!ok) return;
  try {
    const response = await fetch(`/api/v1/bookmarks/${encodeURIComponent(bookmark.bookmark_id)}`, {
      method: "DELETE",
    });
    if (!response.ok && response.status !== 204) {
      const data = await response.json().catch(() => ({}));
      window.alert(data?.error?.message ?? "Could not remove bookmark.");
      return;
    }
    await loadBookmarks();
  } catch (error) {
    window.alert(`Network error: ${error.message}`);
  }
}

filterInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  renderTagChips();
  renderList();
});
editForm.addEventListener("submit", submitEdit);
editCancelBtn.addEventListener("click", () => editDialog.close());

loadBookmarks();
