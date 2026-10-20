// Adaptive-bitrate player built on hls.js, with a live view of the rendition ladder.
import { api, el, formatBitrate, formatDuration, timeAgo } from "./api.js";

const $ = (id) => document.getElementById(id);
const videoId = document.querySelector(".watch").dataset.videoId;
const video = $("video");
const player = $("player");
const seek = $("seek");
const ladderList = $("ladder");
const quality = $("quality");
const msg = $("player-msg");

let hls = null;
let levels = [];        // [{ name, height, bitrate }] in hls.js level order
let switches = 0;
let thumbs = [];        // [{ start, end, url, x, y, w, h }] from the WebVTT sprite map
const loadStarted = performance.now();

function showMessage(text) {
  msg.textContent = text;
  msg.hidden = false;
}

function withQuery(url, query) {
  return query ? `${url}${url.includes("?") ? "&" : "?"}${query}` : url;
}

// ----------------------------------------------------------------- ladder panel
function buildLadder(renditions) {
  const max = Math.max(...renditions.map((r) => r.bandwidth), 1);
  // hls.js orders levels lowest-first; the ladder reads top-down from the best rung.
  const order = levels.map((lvl, i) => i).sort((a, b) => levels[b].height - levels[a].height);
  ladderList.replaceChildren(...order.map((i) => {
    const lvl = levels[i];
    const r = renditions.find((x) => x.height === lvl.height) || { name: `${lvl.height}p`, bandwidth: lvl.bitrate };
    const bar = el("b");
    bar.style.width = `${Math.max(8, (r.bandwidth / max) * 100)}%`;
    return el("li", { "data-level": i },
      el("button", { type: "button", "aria-label": `Lock quality to ${r.name}`, onclick: () => lock(i) },
        el("span", { class: "rung-name", text: r.name }),
        el("span", { class: "rung-bar" }, bar, el("small", { text: `${lvl.width}×${lvl.height}, ${formatBitrate(r.bandwidth)}` }))));
  }));
  quality.replaceChildren(el("option", { value: "-1", text: "Auto" }),
    ...order.map((i) => el("option", { value: String(i), text: `${levels[i].height}p` })));
}

function markLevel(index) {
  for (const li of ladderList.children) {
    li.classList.toggle("active", Number(li.dataset.level) === index);
    li.classList.toggle("locked", hls && !hls.autoLevelEnabled && Number(li.dataset.level) === index);
  }
}

function lock(index) {
  if (!hls) return;
  hls.currentLevel = index; // -1 = automatic
  quality.value = String(index);
  $("ladder-note").textContent = index < 0
    ? "Auto picks the best quality your connection can sustain."
    : "Quality is locked. Choose Auto to let it adapt again.";
  markLevel(index < 0 ? hls.currentLevel : index);
}
quality.addEventListener("change", () => lock(Number(quality.value)));

// ------------------------------------------------------------------ live stats
function updateStats() {
  if (hls) $("st-bw").textContent = formatBitrate(hls.bandwidthEstimate);
  const b = video.buffered;
  let ahead = 0;
  for (let i = 0; i < b.length; i++) {
    if (b.start(i) <= video.currentTime && video.currentTime <= b.end(i)) ahead = b.end(i) - video.currentTime;
  }
  $("st-buf").textContent = `${ahead.toFixed(1)} s`;
  if (b.length && video.duration) $("seek-buffer").style.width = `${(b.end(b.length - 1) / video.duration) * 100}%`;
}
setInterval(updateStats, 1000);

// ------------------------------------------------------------------- controls
const playBtn = $("play");
function togglePlay() { video.paused ? video.play() : video.pause(); }
playBtn.addEventListener("click", togglePlay);
video.addEventListener("click", togglePlay);
video.addEventListener("play", () => { player.classList.add("playing"); playBtn.setAttribute("aria-label", "Pause"); });
video.addEventListener("pause", () => { player.classList.remove("playing"); playBtn.setAttribute("aria-label", "Play"); });
video.addEventListener("playing", () => {
  if ($("st-start").textContent === "–") $("st-start").textContent = `${Math.round(performance.now() - loadStarted)} ms`;
}, { once: false });

video.addEventListener("timeupdate", () => {
  const pct = video.duration ? (video.currentTime / video.duration) * 100 : 0;
  $("seek-fill").style.width = `${pct}%`;
  seek.setAttribute("aria-valuenow", String(Math.round(pct)));
  seek.setAttribute("aria-valuetext", formatDuration(video.currentTime));
  $("time").textContent = `${formatDuration(video.currentTime)} / ${formatDuration(video.duration)}`;
});

$("mute").addEventListener("click", () => { video.muted = !video.muted; });
video.addEventListener("volumechange", () => {
  player.classList.toggle("muted", video.muted);
  $("mute").setAttribute("aria-label", video.muted ? "Unmute" : "Mute");
});
$("fullscreen").addEventListener("click", () => {
  document.fullscreenElement ? document.exitFullscreen() : player.requestFullscreen?.();
});

function ratioAt(clientX) {
  const rect = seek.getBoundingClientRect();
  return Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
}
seek.addEventListener("click", (e) => { if (video.duration) video.currentTime = ratioAt(e.clientX) * video.duration; });
seek.addEventListener("keydown", (e) => {
  const step = { ArrowLeft: -5, ArrowRight: 5, Home: -Infinity, End: Infinity }[e.key];
  if (step !== undefined && video.duration) {
    e.preventDefault();
    video.currentTime = Math.min(video.duration, Math.max(0, video.currentTime + step));
  }
});

// Seek-bar hover preview from the sprite sheet.
seek.addEventListener("mousemove", (e) => {
  if (!video.duration) return;
  const ratio = ratioAt(e.clientX);
  const t = ratio * video.duration;
  const thumb = thumbs.find((c) => t >= c.start && t < c.end) || thumbs[thumbs.length - 1];
  const preview = $("preview");
  preview.hidden = false;
  preview.style.left = `${ratio * 100}%`;
  $("preview-time").textContent = formatDuration(t);
  const img = $("preview-img");
  if (thumb) {
    img.hidden = false;
    img.style.width = `${thumb.w}px`;
    img.style.height = `${thumb.h}px`;
    img.style.backgroundImage = `url("${thumb.url}")`;
    img.style.backgroundPosition = `-${thumb.x}px -${thumb.y}px`;
  } else {
    img.hidden = true;
  }
});
seek.addEventListener("mouseleave", () => { $("preview").hidden = true; });

document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select")) return;
  const actions = {
    " ": togglePlay, k: togglePlay,
    j: () => { video.currentTime -= 10; }, l: () => { video.currentTime += 10; },
    m: () => { video.muted = !video.muted; }, f: () => $("fullscreen").click(),
  };
  const action = actions[e.key];
  if (action && !(e.key === " " && e.target.closest("button"))) { e.preventDefault(); action(); }
});

// Hide controls while playing and the pointer is still.
let idleTimer;
function wake() {
  player.classList.remove("idle");
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { if (!video.paused) player.classList.add("idle"); }, 2500);
}
player.addEventListener("mousemove", wake);
player.addEventListener("focusin", wake);

// ------------------------------------------------------------- sprite thumbs
function parseVttTime(s) {
  const [h, m, rest] = s.split(":");
  return Number(h) * 3600 + Number(m) * 60 + Number(rest);
}

async function loadThumbnails(vttUrl, query) {
  try {
    const text = await (await fetch(vttUrl)).text();
    const cues = text.split(/\n\n+/).map((b) => b.trim().split("\n")).filter((l) => l[0]?.includes("-->"));
    thumbs = cues.map(([timing, ref]) => {
      const [start, end] = timing.split("-->").map((x) => parseVttTime(x.trim()));
      const [file, frag] = ref.split("#xywh=");
      const [x, y, w, h] = frag.split(",").map(Number);
      const base = new URL(vttUrl.split("?")[0], location.href); // vttUrl may be path-relative
      return { start, end, x, y, w, h, url: withQuery(new URL(file, base).href, query) };
    });
  } catch { thumbs = []; }
}

// ---------------------------------------------------------------------- boot
async function boot() {
  let data, pb;
  try {
    data = (await api(`/videos/${videoId}`)).video;
    $("title").textContent = data.title;
    document.title = `${data.title} | StreamForge`;
    $("meta").textContent = `${data.owner.display_name}, ${data.view_count} views, ${timeAgo(data.created_at)}`;
    $("desc").textContent = data.description;
    if (data.status !== "ready") {
      showMessage(data.status === "failed" ? "This video couldn't be processed." : "This video is still being processed. Check back in a moment.");
      return;
    }
    pb = (await api(`/videos/${videoId}/playback`)).playback;
  } catch (err) {
    $("title").textContent = "Video not found";
    showMessage(err.status === 404 ? "This video doesn't exist or is private." : err.message);
    return;
  }

  video.poster = pb.poster;
  loadThumbnails(pb.thumbnails, pb.query);

  if (window.Hls?.isSupported()) {
    hls = new window.Hls({
      capLevelToPlayerSize: true,
      startLevel: -1,
      // CloudFront signed URLs: the same signature query rides on every playlist/segment request.
      xhrSetup: pb.query ? (xhr, url) => xhr.open("GET", withQuery(url, pb.query), true) : undefined,
    });
    hls.on(window.Hls.Events.MANIFEST_PARSED, (_e, info) => {
      levels = info.levels;
      buildLadder(data.renditions);
    });
    hls.on(window.Hls.Events.LEVEL_SWITCHED, (_e, { level }) => {
      switches += 1;
      $("st-switch").textContent = String(Math.max(0, switches - 1)); // first switch is the initial pick
      markLevel(level);
    });
    hls.on(window.Hls.Events.ERROR, (_e, info) => {
      if (!info.fatal) return;
      if (info.details === window.Hls.ErrorDetails.MANIFEST_INCOMPATIBLE_CODECS_ERROR) {
        showMessage("This browser can't decode H.264 video. Open the page in Chrome, Safari, Edge or Firefox.");
        hls.destroy();
        return;
      }
      if (info.type === window.Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
      else if (info.type === window.Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
      else showMessage("Playback stopped because of an error. Reload the page to try again.");
    });
    hls.loadSource(pb.hls);
    hls.attachMedia(video);
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = pb.hls; // Safari on iOS: native HLS
    ladderList.replaceChildren(el("li", { text: "Quality is managed by your device's player." }));
  } else {
    showMessage("Your browser can't play HLS video.");
  }
}

boot();
