"use strict";

const state = { batches: [], statistics: null };

async function load() {
  const response = await fetch("/api/v1/tactics/batches?limit=200");
  if (!response.ok) return;
  const data = await response.json();
  state.batches = (data.batches ?? []).slice().reverse(); // oldest first for the chart
  state.statistics = data.statistics ?? {};
  updateSummary();
  renderChart();
  renderTable();
}

function updateSummary() {
  const s = state.statistics;
  document.querySelector("#total-earned").textContent = s.total_earned ?? 0;
  document.querySelector("#total-batches").textContent = s.batches ?? 0;
  document.querySelector("#average-earned").textContent =
    s.average_earned != null ? Math.round(s.average_earned) : 0;
  document.querySelector("#best-batch").textContent = s.best_batch ?? 0;
}

function renderChart() {
  const svg = document.querySelector("#chart");
  const empty = document.querySelector("#chart-empty");
  const batches = state.batches;
  svg.replaceChildren();
  if (!batches.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  const W = 800;
  const H = 240;
  const padL = 44;
  const padR = 16;
  const padT = 20;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const maxPossible = Math.max(...batches.map((b) => b.points_possible || 1));
  const yMax = Math.max(10, Math.ceil(maxPossible / 10) * 10);

  // Grid + axes
  const gridColor = "#d5d0c3";
  const axisColor = "#7b7160";
  const gridSteps = 5;
  for (let i = 0; i <= gridSteps; i += 1) {
    const y = padT + (innerH * i) / gridSteps;
    const value = Math.round(yMax * (1 - i / gridSteps));
    svg.append(
      makeLine(padL, y, W - padR, y, i === gridSteps ? axisColor : gridColor, i === gridSteps ? 1.2 : 0.6),
      makeText(padL - 8, y + 3, String(value), "end", "#4a4438", 10),
    );
  }
  // X ticks (every ~5 batches)
  const step = batches.length > 20 ? Math.ceil(batches.length / 20) : 1;
  for (let i = 0; i < batches.length; i += step) {
    const x = padL + (innerW * i) / Math.max(1, batches.length - 1);
    svg.append(makeText(x, H - padB + 15, String(i + 1), "middle", "#4a4438", 10));
  }

  // "Possible" line as a faint background
  const possiblePts = batches
    .map((b, i) => {
      const x = padL + (innerW * i) / Math.max(1, batches.length - 1);
      const y = padT + innerH * (1 - (b.points_possible ?? 0) / yMax);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  svg.append(makePolyline(possiblePts, "#c9bfa0", 1.2, "4 4"));

  // Earned line
  const earnedPts = batches
    .map((b, i) => {
      const x = padL + (innerW * i) / Math.max(1, batches.length - 1);
      const y = padT + innerH * (1 - (b.points_earned ?? 0) / yMax);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  svg.append(makePolyline(earnedPts, "#2d6a4f", 2.2));

  // Data points
  batches.forEach((b, i) => {
    const x = padL + (innerW * i) / Math.max(1, batches.length - 1);
    const y = padT + innerH * (1 - (b.points_earned ?? 0) / yMax);
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", x.toFixed(1));
    circle.setAttribute("cy", y.toFixed(1));
    circle.setAttribute("r", "3");
    circle.setAttribute("fill", "#d7a928");
    circle.setAttribute("stroke", "#5c4900");
    circle.setAttribute("stroke-width", "0.8");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = `Batch ${b.batch_index + 1} (cycle ${b.cycle}): ${b.points_earned} / ${b.points_possible}`;
    circle.append(title);
    svg.append(circle);
  });
}

function renderTable() {
  const tbody = document.querySelector("#batch-rows");
  if (!state.batches.length) {
    tbody.replaceChildren();
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="6" class="muted">No batches yet.</td>';
    tbody.append(tr);
    return;
  }
  // Show newest first in the table
  const rows = state.batches.slice().reverse().map((b) => {
    const tr = document.createElement("tr");
    const completedAt = b.completed_at
      ? new Date(b.completed_at.endsWith("Z") ? b.completed_at : `${b.completed_at}Z`).toLocaleString()
      : "—";
    const perPuzzle = (b.per_puzzle_points ?? []).join(" · ");
    tr.innerHTML = `
      <td class="mono strong">${b.batch_index + 1}</td>
      <td class="mono">${b.cycle}</td>
      <td>${completedAt}</td>
      <td class="mono strong">${b.points_earned} / ${b.points_possible}</td>
      <td class="mono">${b.puzzles_solved} / 5</td>
      <td class="per-puzzle">${perPuzzle}</td>
    `;
    return tr;
  });
  tbody.replaceChildren(...rows);
}

function makeLine(x1, y1, x2, y2, color, width) {
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", x1);
  line.setAttribute("y1", y1);
  line.setAttribute("x2", x2);
  line.setAttribute("y2", y2);
  line.setAttribute("stroke", color);
  line.setAttribute("stroke-width", String(width));
  return line;
}

function makeText(x, y, text, anchor, color, size) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
  el.setAttribute("x", x);
  el.setAttribute("y", y);
  el.setAttribute("text-anchor", anchor);
  el.setAttribute("fill", color);
  el.setAttribute("font-size", String(size));
  el.setAttribute("font-family", "IBM Plex Mono, ui-monospace, monospace");
  el.textContent = text;
  return el;
}

function makePolyline(points, color, width, dashArray) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  el.setAttribute("points", points);
  el.setAttribute("fill", "none");
  el.setAttribute("stroke", color);
  el.setAttribute("stroke-width", String(width));
  if (dashArray) el.setAttribute("stroke-dasharray", dashArray);
  return el;
}

load();
