"use strict";

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
    grid.replaceChildren(...packages.map(renderTile));
  } catch (err) {
    grid.replaceChildren();
    const fail = document.createElement("p");
    fail.className = "muted";
    fail.textContent = "Could not load packages.";
    grid.append(fail);
    console.error(err);
  }
}

function renderTile(pkg) {
  const tile = document.createElement("article");
  tile.className = "package-tile";
  if (pkg.kind === "system") tile.classList.add("package-tile-system");
  tile.dataset.slug = pkg.slug;

  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.textContent = pkg.title;
  const badge = document.createElement("span");
  const badgeKind = pkg.kind === "system" ? "system" : pkg.kind === "user" ? "user" : "curated";
  badge.className = `badge badge-${badgeKind}`;
  badge.textContent = badgeKind === "system"
    ? "System"
    : badgeKind === "user"
      ? "You built this"
      : "Curated";
  header.append(title, badge);
  tile.append(header);

  if (pkg.description) {
    const desc = document.createElement("p");
    desc.className = "desc";
    desc.textContent = pkg.description;
    tile.append(desc);
  }

  if (pkg.kind === "system" && pkg.slug === "bookmarked") {
    const info = document.createElement("dl");
    info.className = "pkg-progress";
    const stack = document.createElement("div");
    stack.style.display = "grid";
    stack.style.gap = ".2rem";
    stack.innerHTML = `
      <div><dt>Puzzles</dt><dd>${pkg.count ?? 0}</dd></div>
    `;
    info.append(stack);
    tile.append(info);

    const actions = document.createElement("div");
    actions.className = "pkg-actions";
    const open = document.createElement("a");
    open.href = "/tactics/bookmarks";
    open.className = "play-btn";
    open.textContent = "Open ▸";
    actions.append(open);
    tile.append(actions);
    return tile;
  }

  const progress = pkg.progress ?? {};
  const perCycle = Math.max(1, progress.batches_per_cycle ?? 1);
  const done = Math.min(perCycle, progress.batches_completed_in_cycle ?? 0);
  const dl = document.createElement("dl");
  dl.className = "pkg-progress";
  dl.append(makeRing(done, perCycle));
  const meta = document.createElement("div");
  meta.style.display = "grid";
  meta.style.gap = ".2rem";
  meta.innerHTML = `
    <div><dt>Cycle</dt><dd>${progress.cycle ?? 0}</dd></div>
    <div><dt>Puzzles</dt><dd>${pkg.count ?? "?"}</dd></div>
  `;
  dl.append(meta);
  tile.append(dl);

  const actions = document.createElement("div");
  actions.className = "pkg-actions";

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
    del.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path fill="currentColor" d="M6 7h12v13H6zM9 4h6l1 1h4v2H4V5h4z"/></svg>';
    del.addEventListener("click", () => onDelete(pkg));
    actions.append(del);
  }

  const play = document.createElement("a");
  play.href = `/tactics/${encodeURIComponent(pkg.slug)}`;
  play.className = "play-btn";
  play.textContent = "Play ▸";
  actions.append(play);

  tile.append(actions);
  return tile;
}

function makeRing(done, total) {
  const container = document.createElement("div");
  container.className = "progress-ring";
  const R = 18;
  const C = 2 * Math.PI * R;
  const pct = Math.max(0, Math.min(1, done / total));
  container.innerHTML = `
    <svg viewBox="0 0 44 44" width="44" height="44" aria-hidden="true">
      <circle class="track" cx="22" cy="22" r="${R}"></circle>
      <circle class="fill" cx="22" cy="22" r="${R}"
              stroke-dasharray="${C.toFixed(2)}"
              stroke-dashoffset="${(C * (1 - pct)).toFixed(2)}"
              stroke-linecap="round"></circle>
    </svg>
    <span class="num">${done}/${total}</span>
  `;
  return container;
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
