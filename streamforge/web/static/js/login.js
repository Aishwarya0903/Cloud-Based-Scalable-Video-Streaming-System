import { api, session } from "./api.js";

const form = document.getElementById("auth-form");
const errorBox = document.getElementById("form-error");
const submit = document.getElementById("auth-submit");
let mode = "login";

function setMode(next) {
  mode = next;
  const register = mode === "register";
  document.getElementById("auth-title").textContent = register ? "Create an account" : "Sign in";
  submit.textContent = register ? "Create account" : "Sign in";
  document.getElementById("name-field").hidden = !register;
  document.getElementById("switch-text").textContent = register ? "Already have an account?" : "New here?";
  document.getElementById("switch-mode").textContent = register ? "Sign in" : "Create an account";
  document.getElementById("password").autocomplete = register ? "new-password" : "current-password";
  errorBox.hidden = true;
}

document.getElementById("switch-mode").addEventListener("click", () => setMode(mode === "login" ? "register" : "login"));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.hidden = true;
  submit.disabled = true;
  const body = {
    email: document.getElementById("email").value,
    password: document.getElementById("password").value,
  };
  if (mode === "register") body.display_name = document.getElementById("display_name").value;
  try {
    const data = await api(`/auth/${mode}`, { method: "POST", body, auth: false });
    session.save(data);
    const next = new URLSearchParams(location.search).get("next");
    location.href = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

if (session.signedIn) location.href = "/";
