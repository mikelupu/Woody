"use strict";

const HEADERS = { "Content-Type": "application/json" };
const TIMER_TICK_MS = 100;

const els = {
  splash: document.querySelector("#index-splash"),
  splashTitle: document.querySelector("#splash-title"),
  splashDetail: document.querySelector("#splash-detail"),
  splashProgressWrap: document.querySelector("#splash-progress-wrap"),
  splashProgressFill: document.querySelector("#splash-progress-fill"),
  splashProgressText: document.querySelector("#splash-progress-text"),
  splashBuild: document.querySelector("#splash-build"),
  builder: document.querySelector("#builder"),
  filters: document.querySelector("#filters"),
  searchBtn: document.querySelector("#search-btn"),
  searchDialog: document.querySelector("#search-dialog"),
  searchTimerValue: document.querySelector("#search-timer-value"),
  searchCancel: document.querySelector("#search-cancel"),
  matchCount: document.querySelector("#match-count"),
  matchSummary: document.querySelector("#match-summary"),
  resultsTable: document.querySelector("#results-table"),
  resultsTbody: document.querySelector("#results-tbody"),
  pagination: document.querySelector("#pagination"),
  pagePrev: document.querySelector("#page-prev"),
  pageNext: document.querySelector("#page-next"),
  pageLabel: document.querySelector("#page-label"),
  pageSize: document.querySelector("#page-size"),
  saveForm: document.querySelector("#save-form"),
  saveBtn: document.querySelector("#pkg-save"),
  saveStatus: document.querySelector("#save-status"),
  pkgTitle: document.querySelector("#pkg-title"),
  pkgSlug: document.querySelector("#pkg-slug"),
  pkgDescription: document.querySelector("#pkg-description"),
  pkgCount: document.querySelector("#pkg-count"),
  pkgSeed: document.querySelector("#pkg-seed"),
  themesDialog: document.querySelector("#themes-dialog"),
  themesList: document.querySelector("#themes-list"),
  showThemes: document.querySelector("#show-themes"),
  openingTagsDialog: document.querySelector("#opening-tags-dialog"),
  openingTagsList: document.querySelector("#opening-tags-list"),
  openingTagsFilter: document.querySelector("#opening-tags-filter"),
  openingTagsStatus: document.querySelector("#opening-tags-status"),
  showOpeningTags: document.querySelector("#show-opening-tags"),
  filterOpening: document.querySelector("#filter-opening"),
};

let lastPreview = null;
let statusPollTimer = null;
let themeList = [];
let openingTagList = null;   // null = not yet loaded; array = loaded
let searchController = null;
let searchTimerHandle = null;
let filtersDirty = false;
let allRows = [];
let pageSize = 20;
let pageIndex = 0;

async function init() {
  await refreshIndexStatus();
  loadThemes();
  wire();
}

async function loadThemes() {
  try {
    const r = await fetch("/api/v1/tactics/search/themes");
    if (!r.ok) return;
    themeList = (await r.json()).themes ?? [];
    els.themesList.replaceChildren(
      ...themeList.map((t) => {
        const p = document.createElement("p");
        p.textContent = t;
        return p;
      })
    );
  } catch (err) {
    console.warn("theme list unavailable", err);
  }
}

function wire() {
  els.filters.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch();
  });
  els.filters.addEventListener("input", markFiltersDirty);
  els.filters.addEventListener("change", markFiltersDirty);
  els.searchCancel?.addEventListener("click", cancelSearch);
  els.pkgTitle.addEventListener("input", () => {
    if (!els.pkgSlug.dataset.userset) {
      els.pkgSlug.value = slugify(els.pkgTitle.value);
    }
    if (lastPreview && !filtersDirty) updateSaveState(lastPreview);
  });
  els.pkgSlug.addEventListener("input", () => {
    els.pkgSlug.dataset.userset = "1";
    if (lastPreview && !filtersDirty) updateSaveState(lastPreview);
  });
  els.saveBtn.addEventListener("click", onSave);
  els.showThemes.addEventListener("click", () => els.themesDialog.showModal());
  els.showOpeningTags?.addEventListener("click", openOpeningTagsDialog);
  els.openingTagsFilter?.addEventListener("input", renderOpeningTagsList);
  els.splashBuild.addEventListener("click", onBuild);
  els.pagePrev.addEventListener("click", () => {
    if (pageIndex > 0) { pageIndex--; renderPage(); }
  });
  els.pageNext.addEventListener("click", () => {
    if ((pageIndex + 1) * pageSize < allRows.length) { pageIndex++; renderPage(); }
  });
  els.pageSize.addEventListener("change", () => {
    const n = Math.max(1, Math.min(100, Number.parseInt(els.pageSize.value, 10) || 20));
    els.pageSize.value = String(n);
    pageSize = n;
    pageIndex = 0;
    renderPage();
  });
  els.resultsTbody.addEventListener("click", (event) => {
    const btn = event.target.closest(".try-row");
    if (btn && btn.dataset.puzzleId) onTryRow(btn.dataset.puzzleId, btn);
  });
}

function markFiltersDirty() {
  if (!lastPreview) return;
  if (filtersDirty) return;
  filtersDirty = true;
  els.matchCount.classList.add("stale");
  els.resultsTable.classList.add("stale");
  els.saveBtn.disabled = true;
  els.saveStatus.textContent = "Filters changed — click Search to refresh.";
}

async function openOpeningTagsDialog() {
  els.openingTagsDialog.showModal();
  if (openingTagList === null) {
    await loadOpeningTags();
  }
  renderOpeningTagsList();
}

async function loadOpeningTags() {
  els.openingTagsStatus.textContent = "Loading tags from the local index…";
  try {
    const r = await fetch("/api/v1/tactics/search/opening-tags");
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      els.openingTagsStatus.textContent =
        err?.error?.message ?? "Opening tags unavailable.";
      openingTagList = [];
      return;
    }
    openingTagList = (await r.json()).opening_tags ?? [];
    els.openingTagsStatus.textContent = openingTagList.length
      ? `${openingTagList.length.toLocaleString()} tags in the local index. Click one to fill the filter.`
      : "No opening tags in the local index.";
  } catch (err) {
    console.warn("opening tag list unavailable", err);
    openingTagList = [];
    els.openingTagsStatus.textContent = "Could not load opening tags.";
  }
}

function renderOpeningTagsList() {
  if (openingTagList === null) return;
  const needle = els.openingTagsFilter?.value.trim().toLowerCase() ?? "";
  const matched = needle
    ? openingTagList.filter((tag) => tag.toLowerCase().includes(needle))
    : openingTagList;
  els.openingTagsList.replaceChildren(
    ...matched.slice(0, 500).map((tag) => {
      const p = document.createElement("p");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "linky";
      btn.textContent = tag;
      btn.addEventListener("click", () => selectOpeningTag(tag));
      p.append(btn);
      return p;
    })
  );
  if (matched.length > 500) {
    const more = document.createElement("p");
    more.className = "muted";
    more.textContent = `…and ${(matched.length - 500).toLocaleString()} more. Narrow the filter.`;
    els.openingTagsList.append(more);
  }
}

function selectOpeningTag(tag) {
  if (els.filterOpening) {
    els.filterOpening.value = tag;
    els.filterOpening.dispatchEvent(new Event("input", { bubbles: true }));
  }
  els.openingTagsDialog.close();
}

function slugify(value) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
}

function readQuery() {
  const q = {
    required_themes: strList("#filter-required"),
    any_of_themes: strList("#filter-anyof"),
    excluded_themes: strList("#filter-excluded"),
    rating_min: intOrNull("#filter-rating-min"),
    rating_max: intOrNull("#filter-rating-max"),
    rating_deviation_max: intOrNull("#filter-rating-dev"),
    popularity_min: intOrNull("#filter-popularity"),
    nb_plays_min: intOrNull("#filter-plays"),
    phase: strOrNull("#filter-phase"),
    solution_plies_min: intOrNull("#filter-plies-min"),
    solution_plies_max: intOrNull("#filter-plies-max"),
    mate_in: intOrNull("#filter-mate-in"),
    opening_tag: strOrNull("#filter-opening"),
  };
  return q;
}

function strList(sel) {
  const value = document.querySelector(sel)?.value ?? "";
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}
function intOrNull(sel) {
  const raw = document.querySelector(sel)?.value ?? "";
  if (raw === "") return null;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}
function strOrNull(sel) {
  const raw = document.querySelector(sel)?.value ?? "";
  return raw === "" ? null : raw;
}

async function runSearch() {
  if (searchController) return;   // already searching
  const query = readQuery();
  searchController = new AbortController();
  openSearchDialog();
  els.searchBtn.disabled = true;
  try {
    const r = await fetch("/api/v1/tactics/search/preview", {
      method: "POST",
      headers: { ...HEADERS, Origin: window.location.origin },
      body: JSON.stringify(query),
      signal: searchController.signal,
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      els.matchCount.textContent = "?";
      els.matchCount.classList.remove("stale");
      els.saveStatus.textContent = err?.error?.message ?? "Preview failed.";
      lastPreview = null;
      filtersDirty = false;
      return;
    }
    const data = await r.json();
    lastPreview = data;
    filtersDirty = false;
    els.matchCount.classList.remove("stale");
    els.resultsTable.classList.remove("stale");
    els.matchCount.textContent = data.count.toLocaleString();
    renderResults(data.rows ?? [], data.count);
    els.saveForm.hidden = false;
    updateSaveState(data);
  } catch (err) {
    if (err?.name === "AbortError") {
      els.saveStatus.textContent = "Search cancelled.";
      return;
    }
    console.error(err);
    els.saveStatus.textContent = "Preview failed (network).";
  } finally {
    closeSearchDialog();
    searchController = null;
    els.searchBtn.disabled = false;
  }
}

function openSearchDialog() {
  const startedAt = performance.now();
  els.searchTimerValue.textContent = "0.0";
  if (typeof els.searchDialog.showModal === "function") {
    els.searchDialog.showModal();
  } else {
    els.searchDialog.setAttribute("open", "");
  }
  if (searchTimerHandle) clearInterval(searchTimerHandle);
  searchTimerHandle = setInterval(() => {
    const elapsed = (performance.now() - startedAt) / 1000;
    els.searchTimerValue.textContent = elapsed.toFixed(1);
  }, TIMER_TICK_MS);
}

function closeSearchDialog() {
  if (searchTimerHandle) {
    clearInterval(searchTimerHandle);
    searchTimerHandle = null;
  }
  if (els.searchDialog.open) els.searchDialog.close();
}

function cancelSearch() {
  if (searchController) searchController.abort();
}

function renderResults(rows, totalCount) {
  allRows = rows;
  pageIndex = 0;
  els.matchSummary.textContent = rows.length
    ? `${totalCount.toLocaleString()} matches (showing first ${rows.length}).`
    : `${totalCount.toLocaleString()} matches.`;
  if (!rows.length) {
    els.resultsTable.hidden = true;
    els.pagination.hidden = true;
    return;
  }
  els.resultsTable.hidden = false;
  els.pagination.hidden = false;
  renderPage();
}

function renderPage() {
  const start = pageIndex * pageSize;
  const slice = allRows.slice(start, start + pageSize);
  els.resultsTbody.replaceChildren(...slice.map(rowToTr));
  const totalPages = Math.max(1, Math.ceil(allRows.length / pageSize));
  els.pageLabel.textContent = `Page ${pageIndex + 1} of ${totalPages}`;
  els.pagePrev.disabled = pageIndex === 0;
  els.pageNext.disabled = pageIndex >= totalPages - 1;
}

function rowToTr(row) {
  const tr = document.createElement("tr");
  const themesText = Array.isArray(row.themes) ? row.themes.join(" ") : (row.themes ?? "");
  const openingText = Array.isArray(row.opening_tags)
    ? row.opening_tags.join(" ")
    : (row.opening_tags ?? "");
  const gameHtml = row.game_url
    ? `<a href="${escapeHtml(row.game_url)}" target="_blank" rel="noopener">↗</a>`
    : "";
  tr.innerHTML =
    `<td><button type="button" class="try-row" data-puzzle-id="${escapeHtml(row.id)}">Try</button></td>` +
    `<td>${escapeHtml(row.id)}</td>` +
    `<td>${row.rating ?? ""}</td>` +
    `<td>${escapeHtml(row.phase ?? "")}</td>` +
    `<td>${row.solution_plies ?? ""}</td>` +
    `<td class="themes">${escapeHtml(themesText)}</td>` +
    `<td>${row.popularity ?? ""}</td>` +
    `<td class="opening-tags">${escapeHtml(openingText)}</td>` +
    `<td>${gameHtml}</td>`;
  return tr;
}

async function onTryRow(puzzleId, button) {
  button.disabled = true;
  try {
    const r = await fetch("/api/v1/tactics/preview/batch", {
      method: "POST",
      headers: { ...HEADERS, Origin: window.location.origin },
      body: JSON.stringify({ puzzle_ids: [puzzleId] }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      els.saveStatus.textContent = body?.error?.message ?? "Could not open puzzle.";
      return;
    }
    window.open(`/tactics/preview/batch/${encodeURIComponent(body.batch_id)}`, "_blank");
  } catch (err) {
    console.error(err);
    els.saveStatus.textContent = "Could not open puzzle (network).";
  } finally {
    button.disabled = false;
  }
}

function updateSaveState(preview) {
  const count = preview?.count ?? 0;
  const target = Number.parseInt(els.pkgCount.value, 10);
  const slug = els.pkgSlug.value.trim();
  const title = els.pkgTitle.value.trim();
  const canSave = count >= 5 && slug.length >= 3 && title.length > 0;
  els.saveBtn.disabled = !canSave;
  if (!canSave) {
    els.saveStatus.textContent = count < 5
      ? "Loosen filters until you have at least 5 matches."
      : "";
  } else if (count < target) {
    els.saveStatus.textContent = `Only ${count} matches; package will contain ${Math.floor(count / 5) * 5}.`;
  } else {
    els.saveStatus.textContent = "Ready to save.";
  }
}

async function onSave() {
  const query = readQuery();
  query.target_count = Number.parseInt(els.pkgCount.value, 10);
  query.seed = Number.parseInt(els.pkgSeed.value, 10);
  const pkg = {
    slug: els.pkgSlug.value.trim(),
    title: els.pkgTitle.value.trim(),
    description: els.pkgDescription.value.trim(),
  };
  els.saveBtn.disabled = true;
  els.saveStatus.textContent = "Saving…";
  try {
    const r = await fetch("/api/v1/tactics/packages", {
      method: "POST",
      headers: { ...HEADERS, Origin: window.location.origin },
      body: JSON.stringify({ query, package: pkg }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      els.saveStatus.textContent = body?.error?.message ?? "Save failed.";
      els.saveBtn.disabled = false;
      return;
    }
    window.location.href = `/tactics/${encodeURIComponent(body.slug)}`;
  } catch (err) {
    console.error(err);
    els.saveStatus.textContent = "Save failed (network).";
    els.saveBtn.disabled = false;
  }
}

async function refreshIndexStatus() {
  try {
    const r = await fetch("/api/v1/tactics/index/status");
    if (!r.ok) throw new Error(`status ${r.status}`);
    const status = await r.json();
    updateSplash(status);
  } catch (err) {
    els.splash.hidden = false;
    els.splashTitle.textContent = "Search unavailable";
    els.splashDetail.textContent = "Could not reach the search index.";
    els.builder.hidden = true;
  }
}

function updateSplash(status) {
  if (status.state === "ready") {
    els.splash.hidden = true;
    els.builder.hidden = false;
    if (statusPollTimer) clearInterval(statusPollTimer);
    statusPollTimer = null;
    return;
  }
  els.builder.hidden = true;
  els.splash.hidden = false;
  if (!status.source_available) {
    els.splashTitle.textContent = "Lichess puzzle dump not found";
    els.splashDetail.innerHTML = `
      Expected file at <code>${escapeHtml(status.source_path ?? "data/source/lichess_db_puzzle.csv.zst")}</code>.
      Download the puzzle dump from
      <a href="https://database.lichess.org/#puzzles" target="_blank" rel="noopener">database.lichess.org</a>
      (about 290 MB, already compressed) and place it at that path. Local dev works
      once the file is present; on Railway, upload it into the persistent volume
      first.
    `;
    els.splashProgressWrap.hidden = true;
    els.splashBuild.hidden = true;
    return;
  }
  if (status.state === "building") {
    els.splashTitle.textContent = "Building search index";
    els.splashDetail.textContent =
      "This runs once — about 4–6 minutes for the full 4M puzzle dump.";
    els.splashProgressWrap.hidden = false;
    els.splashBuild.hidden = true;
    const scanned = status.scanned ?? 0;
    const inserted = status.inserted ?? 0;
    // Total isn't known ahead of time; show inserted rate.
    els.splashProgressFill.style.width = `${Math.min(100, (scanned / 4_500_000) * 100).toFixed(1)}%`;
    els.splashProgressText.textContent = `Scanned ${scanned.toLocaleString()} rows · indexed ${inserted.toLocaleString()}.`;
    if (!statusPollTimer) statusPollTimer = setInterval(refreshIndexStatus, 1500);
    return;
  }
  // missing / empty / corrupt with source available
  els.splashTitle.textContent = "First-time setup";
  els.splashDetail.textContent =
    "The search index hasn't been built yet. Building takes ~5 minutes and only happens once.";
  els.splashProgressWrap.hidden = true;
  els.splashBuild.hidden = false;
}

async function onBuild() {
  els.splashBuild.disabled = true;
  try {
    const r = await fetch("/api/v1/tactics/index/build", {
      method: "POST",
      headers: { ...HEADERS, Origin: window.location.origin },
      body: JSON.stringify({}),
    });
    if (r.status === 202 || r.status === 200) {
      updateSplash({ state: "building", source_available: true, scanned: 0, inserted: 0 });
      return;
    }
    const body = await r.json().catch(() => ({}));
    els.splashDetail.textContent = body?.error?.message ?? "Could not start the build.";
  } catch (err) {
    els.splashDetail.textContent = "Network error starting build.";
  } finally {
    els.splashBuild.disabled = false;
  }
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

init();
