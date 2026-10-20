import { api, el, formatDuration, miniLadder, timeAgo } from "./api.js";

const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const pager = document.getElementById("pager");
const params = new URLSearchParams(location.search);
const state = { q: params.get("q") || "", sort: params.get("sort") || "recent", page: Number(params.get("page")) || 1 };

if (state.q) {
  document.getElementById("library-title").textContent = `Results for “${state.q}”`;
  empty.querySelector("h2").textContent = "No matching videos";
  empty.querySelector("p").textContent = "Try a different word, or browse the whole library.";
  const link = empty.querySelector("a");
  link.textContent = "Show all videos";
  link.href = "/";
}

function card(v) {
  const img = v.poster_url
    ? el("img", { src: v.poster_url, alt: "", loading: "lazy", decoding: "async" })
    : null;
  return el("a", { class: "frame", href: `/watch/${v.id}` },
    el("div", { class: "frame-img" }, img, el("span", { class: "frame-dur", text: formatDuration(v.duration_s) })),
    el("div", { class: "frame-body" },
      el("span", { class: "frame-title", text: v.title }),
      miniLadder(v.renditions),
      el("span", { class: "frame-sub", text: `${v.owner.display_name}, ${v.view_count} views, ${timeAgo(v.created_at)}` }),
    ),
  );
}

async function render() {
  const qs = new URLSearchParams({ sort: state.sort, page: state.page, per_page: 12 });
  if (state.q) qs.set("q", state.q);
  history.replaceState(null, "", `/?${qs}`);
  for (const b of document.querySelectorAll("[data-sort]")) b.setAttribute("aria-pressed", String(b.dataset.sort === state.sort));

  try {
    const data = state.sort === "trending" && !state.q
      ? { ...(await api("/trending", { auth: false })), page: 1, pages: 1 }
      : await api(`/videos?${qs}`, { auth: false });
    data.total ??= data.items.length;
    grid.replaceChildren(...data.items.map(card));
    empty.hidden = data.total > 0;
    if (!state.q) {
      const trendingEmpty = state.sort === "trending";
      empty.querySelector("h2").textContent = trendingEmpty ? "Nothing is trending yet" : "No videos yet";
      empty.querySelector("p").textContent = trendingEmpty
        ? "Videos show up here once people start watching them."
        : "Uploaded videos appear here once they finish processing.";
    }
    pager.hidden = data.pages <= 1;
    document.getElementById("page-label").textContent = `Page ${data.page} of ${data.pages}`;
    pager.querySelector('[data-page-step="-1"]').disabled = data.page <= 1;
    pager.querySelector('[data-page-step="1"]').disabled = data.page >= data.pages;
  } catch (err) {
    grid.replaceChildren(el("p", { class: "form-error", text: `Couldn't load videos: ${err.message}` }));
  }
}

document.querySelectorAll("[data-sort]").forEach((b) =>
  b.addEventListener("click", () => { state.sort = b.dataset.sort; state.page = 1; render(); }));
pager.addEventListener("click", (e) => {
  const step = Number(e.target.closest("[data-page-step]")?.dataset.pageStep || 0);
  if (step) { state.page += step; render(); window.scrollTo({ top: 0 }); }
});

render();
