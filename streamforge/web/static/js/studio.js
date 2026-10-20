import { api, el, formatBytes, formatDuration, requireSignIn, toast } from "./api.js";

const rows = document.getElementById("studio-rows");
const table = document.getElementById("studio");
const empty = document.getElementById("empty");
let timer;

const STATUS_TEXT = {
  uploading: "Upload not finished",
  queued: "Waiting to process",
  processing: "Processing",
  ready: "Ready",
  failed: "Failed",
};

function row(v) {
  const thumb = el("div", { class: "studio-thumb" }, v.poster_url ? el("img", { src: v.poster_url, alt: "", loading: "lazy" }) : null);
  const status = el("span", { class: `status status-${v.status}`, text: STATUS_TEXT[v.status] || v.status });
  const statusCell = el("td", {}, status);
  if (v.status === "processing") {
    const bar = el("span", { class: "bar status-progress" }, el("span", { class: "bar-fill bar-fill-signal" }));
    bar.firstChild.style.width = `${v.progress}%`;
    bar.firstChild.style.display = "block";
    statusCell.append(bar);
  }
  if (v.status === "failed" && v.error) statusCell.append(el("span", { class: "studio-sub", text: v.error }));

  const actions = el("div", { class: "row-actions" });
  if (v.status === "failed" || v.status === "ready") {
    actions.append(el("button", {
      class: "btn", type: "button", text: v.status === "failed" ? "Try again" : "Reprocess",
      onclick: async () => {
        await api(`/videos/${v.id}/retranscode`, { method: "POST" });
        toast("Queued for processing.");
        load();
      },
    }));
  }
  actions.append(el("button", {
    class: "btn", type: "button", text: "Delete",
    onclick: async () => {
      if (!window.confirm(`Delete “${v.title}”? This removes every quality and can’t be undone.`)) return;
      await api(`/videos/${v.id}`, { method: "DELETE" });
      toast("Video deleted.");
      load();
    },
  }));

  const link = v.status === "ready" ? el("a", { href: `/watch/${v.id}`, text: v.title }) : el("strong", { text: v.title });
  const visibility = { public: "Everyone", unlisted: "Anyone with the link", private: "Only me" }[v.visibility];
  return el("tr", {},
    el("td", {}, el("div", { class: "studio-video" }, thumb,
      el("div", {}, link, el("span", { class: "studio-sub", text: `${visibility}, ${formatBytes(v.size_bytes)}${v.duration_s ? `, ${formatDuration(v.duration_s)}` : ""}` })))),
    statusCell,
    el("td", { text: v.renditions.map((r) => r.name).join(" ") || "–" }),
    el("td", { text: String(v.view_count) }),
    el("td", {}, actions),
  );
}

async function load() {
  clearTimeout(timer);
  try {
    const data = await api("/me/videos?per_page=50");
    rows.replaceChildren(...data.items.map(row));
    table.hidden = data.total === 0;
    empty.hidden = data.total > 0;
    // Keep polling while anything is still moving through the pipeline.
    if (data.items.some((v) => ["queued", "processing"].includes(v.status))) timer = setTimeout(load, 3000);
  } catch (err) {
    toast(err.message);
  }
}

if (requireSignIn()) load();
