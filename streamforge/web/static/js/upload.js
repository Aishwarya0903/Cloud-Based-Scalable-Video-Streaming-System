// Parallel, resumable, direct-to-S3 multipart upload.
//
// The API only plans the upload and signs URLs; this page PUTs each part straight to
// S3 with CONCURRENCY requests in flight, retries failed parts with backoff, re-signs
// expired URLs, and can resume after a reload by asking S3 which parts it already has.
import { api, ApiError, el, formatBytes, requireSignIn, toast } from "./api.js";

const CONCURRENCY = 4;
const MAX_RETRIES = 4;
const MAX_CELLS = 600;
const EXT_TYPES = { mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm",
  mkv: "video/x-matroska", avi: "video/x-msvideo", mpg: "video/mpeg", mpeg: "video/mpeg" };

const $ = (id) => document.getElementById(id);
const form = $("upload-form");
const drop = $("drop");
const fileInput = $("file");
let active = null; // the upload in progress

// ------------------------------------------------------------- resume memory
function resumeKey(file) {
  return `sf.upload:${file.name}:${file.size}:${file.lastModified}`;
}
function remember(file, videoId) {
  try { localStorage.setItem(resumeKey(file), videoId); } catch { /* resume just won't be offered */ }
}
function recall(file) {
  try { return localStorage.getItem(resumeKey(file)); } catch { return null; }
}
function forget(file) {
  try { localStorage.removeItem(resumeKey(file)); } catch { /* ignore */ }
}

// ------------------------------------------------------------------ choosing
function pick(file) {
  if (!file) return;
  $("drop-title").textContent = file.name;
  $("drop-sub").textContent = recall(file)
    ? `${formatBytes(file.size)}. This upload was interrupted earlier and will continue where it stopped.`
    : formatBytes(file.size);
  if (!$("title").value) $("title").value = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
}

fileInput.addEventListener("change", () => pick(fileInput.files[0]));
for (const type of ["dragenter", "dragover"]) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add("over"); });
}
for (const type of ["dragleave", "drop"]) {
  drop.addEventListener(type, () => drop.classList.remove("over"));
}
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files.length) {
    fileInput.files = e.dataTransfer.files;
    pick(fileInput.files[0]);
  }
});

// --------------------------------------------------------------- part grid UI
class PartGrid {
  constructor(count) {
    this.perCell = Math.ceil(count / MAX_CELLS);
    this.cells = Array.from({ length: Math.ceil(count / this.perCell) }, () => el("i"));
    $("parts").replaceChildren(...this.cells);
    $("parts-legend").textContent = this.perCell > 1
      ? `${count} parts, each square is ${this.perCell} parts.`
      : `${count} parts, uploading ${Math.min(CONCURRENCY, count)} at a time.`;
  }
  set(part, state) {
    this.cells[Math.floor((part - 1) / this.perCell)].className = state;
  }
}

// --------------------------------------------------------------------- upload
class Upload {
  constructor(file, plan, alreadyUploaded) {
    this.file = file;
    this.videoId = plan.video_id;
    this.partSize = plan.part_size;
    this.partCount = plan.part_count;
    this.batch = plan.sign_batch_limit || 100;
    this.urls = new Map();
    this.loaded = new Map(); // part -> bytes sent
    this.xhrs = new Set();
    this.cancelled = false;
    this.grid = new PartGrid(this.partCount);
    this.pending = [];
    for (let n = 1; n <= this.partCount; n++) {
      if (alreadyUploaded.has(n)) {
        this.loaded.set(n, this.sizeOf(n));
        this.grid.set(n, "resumed");
      } else {
        this.pending.push(n);
      }
    }
    this.startBytes = this.sentBytes();
    this.startTime = performance.now();
  }

  sizeOf(n) {
    return Math.min(this.partSize, this.file.size - (n - 1) * this.partSize);
  }

  sentBytes() {
    let total = 0;
    for (const v of this.loaded.values()) total += v;
    return total;
  }

  async urlFor(n) {
    if (!this.urls.has(n)) {
      // Sign this part plus the next few still waiting, in one request.
      const numbers = [n, ...this.pending.filter((p) => !this.urls.has(p))].slice(0, this.batch);
      const signing = api(`/uploads/${this.videoId}/parts`, { method: "POST", body: { part_numbers: numbers } })
        .then((data) => data.urls);
      for (const p of numbers) this.urls.set(p, signing.then((urls) => urls[p]));
    }
    return this.urls.get(n);
  }

  put(url, n) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      this.xhrs.add(xhr);
      xhr.open("PUT", url);
      xhr.upload.onprogress = (e) => { this.loaded.set(n, e.loaded); this.render(); };
      xhr.onload = () => {
        this.xhrs.delete(xhr);
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(Object.assign(new Error(`HTTP ${xhr.status}`), { status: xhr.status }));
      };
      xhr.onerror = xhr.onabort = () => {
        this.xhrs.delete(xhr);
        reject(Object.assign(new Error("network"), { status: 0 }));
      };
      xhr.send(this.file.slice((n - 1) * this.partSize, (n - 1) * this.partSize + this.sizeOf(n)));
    });
  }

  async sendPart(n) {
    for (let attempt = 0; ; attempt++) {
      if (this.cancelled) throw new Error("cancelled");
      this.grid.set(n, attempt ? "retry" : "sending");
      try {
        await this.put(await this.urlFor(n), n);
        this.loaded.set(n, this.sizeOf(n));
        this.grid.set(n, "sent");
        this.render();
        return;
      } catch (err) {
        this.loaded.set(n, 0);
        if (this.cancelled || attempt >= MAX_RETRIES) throw err;
        if (err.status === 403) this.urls.delete(n); // signature expired: re-sign
        await new Promise((r) => setTimeout(r, 1000 * 2 ** attempt));
      }
    }
  }

  async run() {
    const worker = async () => {
      while (this.pending.length && !this.cancelled) await this.sendPart(this.pending.shift());
    };
    await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  }

  render() {
    const sent = this.sentBytes();
    const pct = (sent / this.file.size) * 100;
    $("bar-fill").style.width = `${pct}%`;
    $("pct").textContent = `${pct.toFixed(pct < 10 ? 1 : 0)}%  ${formatBytes(sent)} of ${formatBytes(this.file.size)}`;
    const secs = (performance.now() - this.startTime) / 1000;
    const rate = (sent - this.startBytes) / Math.max(secs, 0.001);
    if (secs > 1 && rate > 0) {
      $("rate").textContent = `${formatBytes(rate)}/s`;
      const left = (this.file.size - sent) / rate;
      $("eta").textContent = left > 1 ? `about ${Math.ceil(left)} s left` : "";
    }
  }

  cancel() {
    this.cancelled = true;
    for (const xhr of this.xhrs) xhr.abort();
  }
}

// ----------------------------------------------------------- transcode watch
async function watchProcessing(videoId) {
  $("processing").hidden = false;
  const line = $("proc-line");
  for (;;) {
    const { video } = await api(`/videos/${videoId}`);
    $("proc-fill").style.width = `${video.status === "ready" ? 100 : video.progress}%`;
    if (video.status === "queued") line.textContent = "Waiting for a worker.";
    if (video.status === "processing") line.textContent = `Encoding every quality at once: ${Math.round(video.progress)}%`;
    if (video.status === "ready") {
      line.replaceChildren(
        `Ready in ${video.processing_seconds}s: ${video.renditions.map((r) => r.name).join(", ")}. `,
        el("a", { href: `/watch/${videoId}`, text: "Watch it now" }),
      );
      return;
    }
    if (video.status === "failed") {
      line.textContent = `Processing failed: ${video.error || "unknown error"}`;
      return;
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
}

// ------------------------------------------------------------------- submit
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;
  const contentType = file.type || EXT_TYPES[file.name.split(".").pop().toLowerCase()] || "";
  $("start").disabled = true;

  try {
    // Resume if S3 still holds an unfinished upload for this exact file.
    let plan = null;
    let uploaded = new Set();
    const previous = recall(file);
    if (previous) {
      try {
        const status = await api(`/uploads/${previous}`);
        if (status.status === "uploading") {
          plan = { video_id: previous, part_size: status.part_size, part_count: status.part_count };
          uploaded = new Set(status.uploaded_parts);
        }
      } catch { forget(file); }
    }
    if (!plan) {
      plan = await api("/uploads", {
        method: "POST",
        body: {
          filename: file.name,
          size: file.size,
          content_type: contentType,
          title: $("title").value,
          description: $("description").value,
          visibility: form.elements.visibility.value,
        },
      });
      remember(file, plan.video_id);
    }

    form.hidden = true;
    $("transfer").hidden = false;
    $("transfer-title").textContent = $("title").value || file.name;
    active = new Upload(file, plan, uploaded);
    active.render();
    await active.run();

    $("cancel").hidden = true;
    $("eta").textContent = "";
    $("rate").textContent = "Upload complete";
    $("parts-legend").textContent = `All ${active.partCount} parts are in storage.`;
    $("transfer").classList.add("done");
    await api(`/uploads/${plan.video_id}/complete`, { method: "POST" });
    forget(file);
    await watchProcessing(plan.video_id);
  } catch (err) {
    if (active?.cancelled) return;
    const message = err instanceof ApiError ? err.message : "The upload stopped. Choose the same file again to continue.";
    toast(message, 6000);
    $("rate").textContent = message;
    $("start").disabled = false;
  }
});

$("cancel").addEventListener("click", async () => {
  if (!active) return;
  active.cancel();
  forget(active.file);
  await api(`/uploads/${active.videoId}`, { method: "DELETE" }).catch(() => {});
  toast("Upload cancelled.");
  location.reload();
});

requireSignIn();
