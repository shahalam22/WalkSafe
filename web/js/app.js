// Start-up and routing: sign-in → the guidance screen (blind user) or the
// admin dashboard (admin, who can also open the guidance screen).
import { initAdmin } from "./admin.js";
import { initGuide, leaveGuide } from "./guide.js";
import { roleOf, supabase } from "./supabase.js";
import { $, prefs, showScreen } from "./ui.js";

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

let shownFor = null;          // "<user id>:<screen>" on show now

function route(session) {
  if (!session) {
    shownFor = null;
    leaveGuide();
    showScreen("login");
    $("#login-email").focus();
    return;
  }
  const role = roleOf(session);
  const screen = role === "admin" && prefs.get("admin-screen", "admin") === "admin" ? "admin" : "guide";
  const key = `${session.user.id}:${screen}`;
  if (key === shownFor) return;            // token refreshes re-fire the auth event
  shownFor = key;

  if (screen === "admin") {
    leaveGuide();
    showScreen("admin");
    initAdmin(session, { onOpenGuide: () => switchTo("guide") });
  } else {
    showScreen("guide");
    initGuide(session, { onOpenAdmin: () => switchTo("admin") });
    $("#guide-toggle").focus();
  }
}

async function switchTo(screen) {
  prefs.set("admin-screen", screen);
  const { data: { session } } = await supabase.auth.getSession();
  route(session);
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#login-error");
  const btn = $("#login-submit");
  err.hidden = true;
  btn.disabled = true;
  btn.textContent = "Signing in…";
  const { error } = await supabase.auth.signInWithPassword({
    email: $("#login-email").value.trim(),
    password: $("#login-password").value,
  });
  btn.disabled = false;
  btn.textContent = "Sign in";
  if (error) {
    err.textContent = /invalid/i.test(error.message) ? "Wrong email or password." : error.message;
    err.hidden = false;
  } else {
    $("#login-password").value = "";
  }
});

supabase.auth.onAuthStateChange((event, session) => {
  // Run outside the callback: Supabase holds a lock while it runs.
  setTimeout(() => route(session), 0);
});
