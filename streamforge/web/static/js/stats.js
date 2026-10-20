import { api, el, formatBitrate, formatDuration, requireSignIn } from "./api.js";

const videoId = document.querySelector("[data-video-id]").dataset.videoId;
const SVG = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}) => {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
};

function kpi(label, value, note) {
  return el("div", { class: "kpi" }, el("dt", { text: label }), el("dd", { text: value }), note ? el("span", { text: note }) : null);
}

// Single-series column chart: 20 slices of the video, 0-100% of sessions.
function retentionChart(values) {
  const W = 760, H = 240, padL = 40, padB = 28, padT = 10, gap = 2;
  const plotW = W - padL, plotH = H - padB - padT;
  const bw = plotW / values.length;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Audience retention by 5% slice of the video" });

  for (const pct of [0, 25, 50, 75, 100]) {
    const y = padT + plotH - (pct / 100) * plotH;
    root.append(svg("line", { x1: padL, x2: W, y1: y, y2: y, class: pct ? "grid" : "axis" }));
    const t = svg("text", { x: padL - 8, y: y + 4, "text-anchor": "end", class: "tick" });
    t.textContent = `${pct}%`;
    root.append(t);
  }
  for (const [i, label] of [[0, "Start"], [values.length / 2, "Middle"], [values.length, "End"]]) {
    const t = svg("text", { x: padL + i * bw, y: H - 8, "text-anchor": i === 0 ? "start" : i === values.length ? "end" : "middle", class: "tick" });
    t.textContent = label;
    root.append(t);
  }

  const tip = el("div", { class: "tip", role: "status" });
  tip.hidden = true;
  values.forEach((v, i) => {
    const h = Math.max(v > 0 ? 2 : 0, (v / 100) * plotH);
    const x = padL + i * bw + gap / 2, y = padT + plotH - h, w = bw - gap;
    // Rounded top only: data end rounded, anchored flat on the baseline.
    const r = Math.min(4, h, w / 2);
    const bar = svg("path", {
      class: "bar",
      d: `M${x},${padT + plotH} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${padT + plotH} Z`,
    });
    const hit = svg("rect", { x: padL + i * bw, y: padT, width: bw, height: plotH, class: "hit", tabindex: 0,
      "aria-label": `${i * 5}–${(i + 1) * 5}% of the video: ${v}% of sessions` });
    const show = () => {
      bar.classList.add("on");
      tip.hidden = false;
      tip.textContent = `${i * 5}–${(i + 1) * 5}% of the video: ${v}% of sessions`;
      tip.style.left = `${((padL + (i + 0.5) * bw) / W) * 100}%`;
      tip.style.top = `${(y / H) * 100}%`;
    };
    const hide = () => { bar.classList.remove("on"); tip.hidden = true; };
    hit.addEventListener("mouseenter", show);
    hit.addEventListener("focus", show);
    hit.addEventListener("mouseleave", hide);
    hit.addEventListener("blur", hide);
    root.append(bar, hit);
  });
  return [root, tip];
}

async function load() {
  const { video, stats } = await api(`/videos/${videoId}/stats`);
  document.getElementById("stats-title").textContent = video.title;
  document.title = `Stats: ${video.title} | StreamForge`;
  document.getElementById("stats-sub").textContent =
    `${formatDuration(video.duration_s)} long, ${video.renditions.map((r) => r.name).join(" / ")}`;

  const ms = (v) => (v === null ? "–" : `${Math.round(v)} ms`);
  document.getElementById("kpis").replaceChildren(
    kpi("Views", String(stats.views), `${stats.unique_viewers} unique viewers`),
    kpi("Watch time", formatDuration(stats.watch_time_seconds), `${formatDuration(stats.avg_watch_seconds)} per view`),
    kpi("Average watched", `${stats.avg_percent_watched}%`, `${stats.completion_rate}% finished`),
    kpi("Startup time", ms(stats.startup_ms_p50), `95th percentile ${ms(stats.startup_ms_p95)}`),
    kpi("Rebuffering", `${stats.rebuffer_ratio}%`, `of viewing time; ${stats.sessions_with_stalls}% of views stalled`),
    kpi("Delivered quality", formatBitrate(stats.avg_bitrate_bps), `${stats.avg_quality_switches} switches per view`),
  );

  const block = document.querySelector(".chart-block");
  if (!stats.views) {
    block.hidden = true;
    document.getElementById("empty").hidden = false;
    return;
  }
  document.getElementById("chart").replaceChildren(...retentionChart(stats.retention));
  document.getElementById("ret-rows").replaceChildren(...stats.retention.map((v, i) =>
    el("tr", {}, el("td", { text: `${i * 5}–${(i + 1) * 5}%` }), el("td", { text: `${v}%` }))));
}

if (requireSignIn()) {
  load().catch((err) => {
    document.getElementById("stats-title").textContent = "Stats unavailable";
    document.getElementById("stats-sub").textContent = err.message;
  });
}
