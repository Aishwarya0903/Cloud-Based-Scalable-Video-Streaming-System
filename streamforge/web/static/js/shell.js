import { api, session, toast } from "./api.js";

// Sign-in state in the top bar.
function renderNav() {
  for (const node of document.querySelectorAll("[data-auth]")) {
    node.hidden = (node.dataset.auth === "in") !== session.signedIn;
  }
}

document.querySelector('[data-action="logout"]')?.addEventListener("click", () => {
  session.clear();
  renderNav();
  toast("Signed out.");
  if (["studio", "upload"].includes(document.body.dataset.page)) location.href = "/";
});

// Keep the search box in sync with ?q=
const q = new URLSearchParams(location.search).get("q");
const search = document.getElementById("q");
if (search && q) search.value = q;

renderNav();

// Drop a stale token quietly so the nav never claims you're signed in when you aren't.
if (session.signedIn) {
  api("/auth/me").catch(() => { session.clear(); renderNav(); });
}
