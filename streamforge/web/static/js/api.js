// Small fetch wrapper + session handling shared by every page.
const TOKEN_KEY = "sf.token";
const USER_KEY = "sf.user";

function store(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage unavailable (private mode): session lasts for this page only */ }
}
function load(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

let memoryToken = load(TOKEN_KEY);

export const session = {
  get token() { return memoryToken; },
  get user() {
    try { return JSON.parse(load(USER_KEY) || "null"); } catch { return null; }
  },
  get signedIn() { return Boolean(memoryToken); },
  save({ token, user }) {
    memoryToken = token;
    store(TOKEN_KEY, token);
    store(USER_KEY, JSON.stringify(user));
  },
  clear() {
    memoryToken = null;
    store(TOKEN_KEY, null);
    store(USER_KEY, null);
  },
};

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;

  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = data.error || {};
    if (resp.status === 401 && ["token_expired", "invalid_token"].includes(err.code)) session.clear();
    throw new ApiError(resp.status, err.code || "http_error", err.message || `Request failed (${resp.status}).`, err.details);
  }
  return data;
}

export function requireSignIn() {
  if (!session.signedIn) {
    location.href = `/login?next=${encodeURIComponent(location.pathname + location.search)}`;
    return false;
  }
  return true;
}

// ---------------------------------------------------------------- formatting
export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const s = Math.floor(seconds % 60), m = Math.floor(seconds / 60) % 60, h = Math.floor(seconds / 3600);
  const ss = String(s).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

export function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
}

export function formatBitrate(bps) {
  if (!bps) return "–";
  return bps >= 1e6 ? `${(bps / 1e6).toFixed(1)} Mbps` : `${Math.round(bps / 1e3)} kbps`;
}

export function timeAgo(iso) {
  const secs = (Date.now() - new Date(iso).getTime()) / 1000;
  const steps = [[60, "second"], [60, "minute"], [24, "hour"], [30, "day"], [12, "month"], [Infinity, "year"]];
  let value = secs;
  for (const [size, unit] of steps) {
    if (value < size) {
      const n = Math.max(1, Math.floor(value));
      return `${n} ${unit}${n === 1 ? "" : "s"} ago`;
    }
    value /= size;
  }
  return "";
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined) node.append(child);
  }
  return node;
}

export function toast(message, ms = 3200) {
  const node = document.querySelector(".toast");
  if (!node) return;
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { node.hidden = true; }, ms);
}

// The rendition ladder in miniature: one bar per rung, length scaled to bitrate.
export function miniLadder(renditions) {
  const max = Math.max(...renditions.map((r) => r.video_kbps), 1);
  if (!renditions.length) return null;
  return el("span", { class: "mini-ladder", title: `Streams in ${renditions.map((r) => r.name).join(", ")}` },
    el("b", { text: renditions[0].name }),
    renditions.map((r) => {
      const bar = el("i");
      bar.style.width = `${Math.max(18, (r.video_kbps / max) * 100)}%`;
      return bar;
    }));
}
