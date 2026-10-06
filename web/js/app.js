// Start-up and routing: sign-in → the guidance screen (blind user) or the
// admin dashboard (admin, who can also open the guidance screen). A password
// reset link from the email opens the new-password screen instead.
import { initAdmin } from "./admin.js";
import { initGuide, leaveGuide } from "./guide.js";
import { resetLink, roleOf, supabase } from "./supabase.js";
import { $, prefs, showScreen } from "./ui.js";

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

const LINK_EXPIRED = "This reset link has expired or was already used. Ask for a new one.";

let shownFor = null;          // "<user id>:<screen>" on show now
let recovering = resetLink.recovery;

function route(session) {
  if (recovering) {
    const key = `reset:${session?.user?.id ?? ""}`;
    if (key === shownFor) return;
    shownFor = key;
    leaveGuide();
    showScreen("reset");
    $("#reset-who").textContent = session
      ? `Choose a new password for ${session.user.email}.`
      : "Choose a new password for your account.";
    $("#reset-password").focus();
    return;
  }
  if (!session) {
    shownFor = null;
    leaveGuide();
    showScreen("login");
    if ($("#login-form").hidden) $("#forgot-email").focus();
    else $("#login-email").focus();
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

// ── Sign in ──────────────────────────────────────────────────────────────────

function loginMessage(text, { ok = false, forgot = false } = {}) {
  $("#login-notice").hidden = !(text && ok);
  $("#login-notice").textContent = ok ? text : "";
  $("#login-error").hidden = !(text && !ok);
  $("#login-error").textContent = ok ? "" : text;
  if (forgot) $("#login-forgot").hidden = false;
}

function showLoginForm() {
  $("#forgot-form").hidden = true;
  $("#login-form").hidden = false;
  $("#login-email").focus();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#login-submit");
  loginMessage("");
  btn.disabled = true;
  btn.textContent = "Signing in…";
  const { error } = await supabase.auth.signInWithPassword({
    email: $("#login-email").value.trim(),
    password: $("#login-password").value,
  });
  btn.disabled = false;
  btn.textContent = "Sign in";
  if (error) {
    if (/invalid/i.test(error.message)) loginMessage("Wrong credentials.", { forgot: true });
    else loginMessage(error.message);
  } else {
    $("#login-password").value = "";
    $("#login-forgot").hidden = true;
  }
});

// ── Forgot password: email a reset link ──────────────────────────────────────

$("#login-forgot").addEventListener("click", () => {
  $("#forgot-email").value = $("#login-email").value.trim();
  $("#forgot-msg").hidden = true;
  $("#login-form").hidden = true;
  $("#forgot-form").hidden = false;
  $("#forgot-email").focus();
});

$("#forgot-back").addEventListener("click", showLoginForm);

$("#forgot-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("#forgot-email").value.trim();
  const msg = $("#forgot-msg");
  const btn = $("#forgot-submit");
  btn.disabled = true;
  btn.textContent = "Sending…";
  // The link comes back to this page, which then shows the new-password screen.
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${location.origin}${location.pathname}`,
  });
  btn.disabled = false;
  btn.textContent = "Send Reset Link";
  msg.hidden = false;
  if (error) {
    msg.className = "error";
    msg.textContent = error.status === 429
      ? "Too many reset emails. Wait a few minutes and try again."
      : error.message;
  } else {
    msg.className = "ok";
    msg.textContent = `If an account uses ${email}, a reset link is on its way. Check the inbox and spam folder.`;
  }
});

// ── New password (from the reset link) ───────────────────────────────────────

function clearResetLink() {
  history.replaceState(history.state, "", `${location.pathname}${location.search}`);
}

async function leaveReset(text, ok) {
  recovering = false;
  shownFor = null;
  clearResetLink();
  await supabase.auth.signOut();
  $("#reset-form").reset();
  showLoginForm();
  loginMessage(text, { ok, forgot: !ok });
  route(null);
}

$("#reset-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#reset-error");
  const btn = $("#reset-submit");
  const password = $("#reset-password").value;
  err.hidden = true;
  if (password.length < 6) {
    err.textContent = "The password needs at least 6 characters.";
    err.hidden = false;
    return;
  }
  if (password !== $("#reset-confirm").value) {
    err.textContent = "The two passwords do not match.";
    err.hidden = false;
    return;
  }
  btn.disabled = true;
  btn.textContent = "Saving…";
  const { error } = await supabase.auth.updateUser({ password });
  btn.disabled = false;
  btn.textContent = "Reset password";
  if (!error) {
    await leaveReset("Password changed. Sign in with your new password.", true);
  } else if (/session/i.test(error.message)) {
    await leaveReset(LINK_EXPIRED, false);
  } else {
    err.textContent = error.message;
    err.hidden = false;
  }
});

$("#reset-cancel").addEventListener("click", () => leaveReset("", true));

if (resetLink.failed) {
  clearResetLink();
  loginMessage(LINK_EXPIRED, { forgot: true });
}

supabase.auth.onAuthStateChange((event, session) => {
  if (event === "PASSWORD_RECOVERY") recovering = true;
  // Run outside the callback: Supabase holds a lock while it runs.
  setTimeout(() => route(session), 0);
});
