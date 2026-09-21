"use strict";

const SECTIONS = [
  { kind: "system",  label: "Pinned" },
  { kind: "curated", label: "Curated" },
  { kind: "user",    label: "Built by you" },
];

async function loadPackages() {
  const grid = document.querySelector("#package-grid");
  const countEl = document.querySelector("#pack-count");
  try {
    const response = await fetch("/api/v1/tactics/packages");
    if (!response.ok) throw new Error(`packages HTTP ${response.status}`);
    const data = await response.json();
    const packages = data.packages ?? [];
    countEl.textContent = packages.length;
    if (packages.length === 0) {
      grid.replaceChildren();
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No packages installed. Build one to get started.";
      grid.append(empty);
      return;
    }
    grid.replaceChildren(...renderSections(packages));
  } catch (err) {
    grid.replaceChildren();
    const fail = document.createElement("p");
    fail.className = "muted";
    fail.textContent = "Could not load packages.";
    grid.append(fail);
    console.error(err);
  }
}

function renderSections(packages) {
  const groups = new Map(SECTIONS.map((s) => [s.kind, []]));
  for (const pkg of packages) {
    const kind = groups.has(pkg.kind) ? pkg.kind : "curated";
    groups.get(kind).push(pkg);
  }
  const nodes = [];
  for (const { kind, label } of SECTIONS) {
    const items = groups.get(kind);
    if (!items.length) continue;
    const head = document.createElement("h2");
    head.className = "section-head";
    head.textContent = label;
    nodes.push(head);
    const list = document.createElement("div");
    list.className = "package-list";
    for (const pkg of items) list.append(renderRow(pkg));
    nodes.push(list);
  }
  return nodes;
}

function renderRow(pkg) {
  const row = document.createElement("article");
  row.className = "package-row";
  if (pkg.kind === "system") row.classList.add("package-row-system");
  row.dataset.slug = pkg.slug;

  row.append(renderPrimary(pkg));
  row.append(renderProgress(pkg));
  row.append(renderCount(pkg));
  row.append(renderActions(pkg));
  return row;
}

function renderPrimary(pkg) {
  const primary = document.createElement("div");
  primary.className = "pkg-primary";

  const titleRow = document.createElement("div");
  titleRow.className = "pkg-title-row";
  const title = document.createElement("h3");
  title.className = "pkg-title";
  title.textContent = pkg.title;
  titleRow.append(title);

  const badgeKind = pkg.kind === "system" ? "system" : pkg.kind === "user" ? "user" : "curated";
  const badge = document.createElement("span");
  badge.className = `badge badge-${badgeKind}`;
  badge.textContent = badgeKind === "system"
    ? "System"
    : badgeKind === "user"
      ? "You built this"
      : "Curated";
  titleRow.append(badge);
  primary.append(titleRow);

  if (pkg.description) {
    const desc = document.createElement("p");
    desc.className = "pkg-desc";
    desc.textContent = pkg.description;
    primary.append(desc);
  }
  return primary;
}

function renderProgress(pkg) {
  const wrap = document.createElement("div");
  wrap.className = "pkg-progress";

  const label = document.createElement("div");
  label.className = "pkg-progress-label";

  if (pkg.kind === "system") {
    wrap.classList.add("pkg-progress-empty");
    const tag = document.createElement("span");
    tag.textContent = pkg.count ? "Flagged" : "Empty";
    label.append(tag);
  } else {
    const progress = pkg.progress ?? {};
    const perCycle = Math.max(1, progress.batches_per_cycle ?? 1);
    const done = Math.min(perCycle, progress.batches_completed_in_cycle ?? 0);
    const tag = document.createElement("span");
    tag.textContent = "Cycle";
    const value = document.createElement("b");
    value.textContent = `${done} / ${perCycle}`;
    label.append(tag, value);
  }
  wrap.append(label);

  const bar = document.createElement("div");
  bar.className = "pkg-bar";
  const fill = document.createElement("span");
  const pct = pkg.kind === "system"
    ? 0
    : progressPercent(pkg.progress);
  fill.style.width = `${pct}%`;
  bar.append(fill);
  wrap.append(bar);

  return wrap;
}

function progressPercent(progress) {
  if (!progress) return 0;
  const perCycle = Math.max(1, progress.batches_per_cycle ?? 1);
  const done = Math.min(perCycle, progress.batches_completed_in_cycle ?? 0);
  return Math.round((done / perCycle) * 100);
}

function renderCount(pkg) {
  const count = document.createElement("div");
  count.className = "pkg-count";
  const value = document.createElement("b");
  value.textContent = pkg.count ?? 0;
  const label = document.createElement("span");
  label.textContent = "Puzzles";
  count.append(value, label);
  return count;
}

function renderActions(pkg) {
  const actions = document.createElement("div");
  actions.className = "pkg-actions";

  if (pkg.kind === "system" && pkg.slug === "bookmarked") {
    const open = document.createElement("a");
    open.href = "/tactics/bookmarks";
    open.className = "play-btn play-btn-outline";
    open.textContent = "Open →";
    actions.append(open);
    return actions;
  }

  const statsLink = document.createElement("a");
  statsLink.href = `/tactics/${encodeURIComponent(pkg.slug)}/stats`;
  statsLink.className = "stats-link";
  statsLink.textContent = "Stats →";
  actions.append(statsLink);

  if (pkg.kind === "user") {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "delete-btn";
    del.title = "Delete package";
    del.setAttribute("aria-label", `Delete ${pkg.title}`);
    del.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9z"/></svg>';
    del.addEventListener("click", () => onDelete(pkg));
    actions.append(del);
  }

  const play = document.createElement("a");
  play.href = `/tactics/${encodeURIComponent(pkg.slug)}`;
  play.className = "play-btn";
  play.textContent = "Play ▶";
  actions.append(play);
  return actions;
}

async function onDelete(pkg) {
  if (!confirm(`Delete package "${pkg.title}"? Your history stays but the puzzles are gone.`)) {
    return;
  }
  try {
    const response = await fetch(`/api/v1/tactics/packages/${encodeURIComponent(pkg.slug)}`, {
      method: "DELETE",
      headers: { Origin: window.location.origin },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      alert(body?.error?.message ?? "Could not delete.");
      return;
    }
    await loadPackages();
  } catch (err) {
    alert("Delete failed.");
    console.error(err);
  }
}

loadPackages();
