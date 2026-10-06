// Admin pages: session data (read straight from Supabase, so it works while the
// server is off), user and admin accounts (through the server, which holds the
// secret key), and the server address.
import { barChart, lineChart, tiles } from "./charts.js";
import { api, cleanUrl, explain, health, loadServerUrl, saveServerUrl } from "./server.js";
import { supabase } from "./supabase.js";
import { $, $$, el, fmtDateTime, fmtDuration, fmtNum, pretty } from "./ui.js";

let users = [];
let current = null;          // the session open in the detail view
let wired = false;

export function initAdmin(session, { onOpenGuide }) {
  $("#admin-who").textContent = session.user.email;
  $("#setup-url").textContent = location.href.split("#")[0];
  if (!wired) {
    wired = true;
    $$(".tabs [role=tab]").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));
    $("#admin-signout").onclick = () => supabase.auth.signOut();
    $("#admin-guide").onclick = onOpenGuide;
    $("#sess-refresh").onclick = () => loadOverview();
    $("#sess-user").onchange = () => loadOverview();
    $("#detail-back").onclick = () => openTab("sessions");
    $$("[data-export]").forEach((b) => b.addEventListener("click", () => exportCsv(b.dataset.export, b)));
    $("#user-form").addEventListener("submit", createUser);
    $("#server-form").addEventListener("submit", saveServer);
    $("#server-test").onclick = testServer;
  }
  openTab("sessions");
}

function openTab(name) {
  $$(".tabs [role=tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  for (const p of $$(".tab-panel")) p.hidden = p.id !== `tab-${name}`;
  if (name === "sessions") loadUsers().then(loadOverview);
  if (name === "users") loadUsers().then(renderUsers);
  if (name === "server") loadServer();
}

const fail = (host, error) => host.replaceChildren(el("p", { class: "error" }, error.message || String(error)));

// ── Sessions ─────────────────────────────────────────────────────────────────

async function loadUsers() {
  const { data, error } = await supabase
    .from("profiles")
    .select("id, email, display_name, role, is_active, created_at, sessions(count)")
    .order("created_at");
  if (error) { users = []; return; }
  users = data;
  const sel = $("#sess-user");
  const keep = sel.value;
  sel.replaceChildren(el("option", { value: "" }, "All users"),
    ...users.map((u) => el("option", { value: u.id }, `${u.display_name || u.email} (${u.role})`)));
  sel.value = users.some((u) => u.id === keep) ? keep : "";
}

const userName = (id) => {
  const u = users.find((x) => x.id === id);
  return u ? u.display_name || u.email : "Deleted user";
};

async function loadOverview() {
  const userId = $("#sess-user").value || null;
  const [stats, list] = await Promise.all([
    supabase.rpc("session_stats", { p_session: null, p_user: userId }),
    (() => {
      let q = supabase.from("sessions")
        .select("session_id, user_id, started_at, ended_at, total_frames, end_reason")
        .order("started_at", { ascending: false }).limit(200);
      if (userId) q = q.eq("user_id", userId);
      return q;
    })(),
  ]);

  if (stats.error) fail($("#sess-tiles"), stats.error);
  else {
    const s = stats.data;
    tiles($("#sess-tiles"), [
      ["Sessions", fmtNum(s.sessions)],
      ["Frames", fmtNum(s.total_frames)],
      ["Average speed", s.avg_speed_ms == null ? "—" : `${s.avg_speed_ms} m/s`],
      ["Agent encounters", fmtNum(s.total_agents)],
      ["Critical events", fmtNum(s.critical_count)],
    ]);
    barChart($("#chart-commands"), s.commands);
    barChart($("#chart-risks"), s.risks, { status: true });
    barChart($("#chart-actions"), s.actions);
  }

  const table = $("#sess-table");
  if (list.error) return fail(table, list.error);
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Started", "User", "Length", "Frames", "Ended by", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...(list.data.length ? list.data.map((r) => el("tr", {},
      el("td", {}, fmtDateTime(r.started_at)),
      el("td", {}, userName(r.user_id)),
      el("td", {}, r.ended_at ? fmtDuration(r.started_at, r.ended_at) : "running"),
      el("td", { class: "num" }, fmtNum(r.total_frames)),
      el("td", {}, pretty(r.end_reason)),
      el("td", {}, el("button", { class: "btn small", onclick: () => openSession(r) }, "View")),
    )) : [el("tr", {}, el("td", { colspan: 6, class: "empty" }, "No sessions yet"))])),
  );
}

async function openSession(row) {
  current = row;
  for (const p of $$(".tab-panel")) p.hidden = p.id !== "tab-session";
  $("#detail-title").textContent = `${userName(row.user_id)} · ${fmtDateTime(row.started_at)}`;
  $("#detail-sub").textContent =
    `Session ${row.session_id.slice(0, 8)} · ${row.ended_at ? fmtDuration(row.started_at, row.ended_at) : "still running"}`;
  for (const id of ["#detail-tiles", "#chart-speed", "#detail-commands", "#detail-risks", "#detail-actions"]) {
    $(id).replaceChildren(el("p", { class: "empty" }, "Loading…"));
  }

  const [stats, speed] = await Promise.all([
    supabase.rpc("session_stats", { p_session: row.session_id, p_user: null }),
    supabase.rpc("session_speed", { p_session: row.session_id, p_points: 400 }),
  ]);
  if (stats.error) return fail($("#detail-tiles"), stats.error);
  const s = stats.data;
  tiles($("#detail-tiles"), [
    ["Frames", fmtNum(s.total_frames)],
    ["Average speed", s.avg_speed_ms == null ? "—" : `${s.avg_speed_ms} m/s`],
    ["Agent encounters", fmtNum(s.total_agents)],
    ["Critical events", fmtNum(s.critical_count)],
  ]);
  barChart($("#detail-commands"), s.commands);
  barChart($("#detail-risks"), s.risks, { status: true });
  barChart($("#detail-actions"), s.actions);
  if (speed.error) fail($("#chart-speed"), speed.error);
  else lineChart($("#chart-speed"), speed.data.map((p) => ({ x: p.frame_idx, y: p.ego_speed_ms, label: p.action })),
    { yUnit: "m/s" });
}

async function exportCsv(table, button) {
  if (!current) return;
  const label = button.textContent;
  button.disabled = true;
  const rows = [];
  try {
    for (let from = 0; ; from += 1000) {
      button.textContent = `${label} (${rows.length})…`;
      const { data, error } = await supabase.from(table).select("*")
        .eq("session_id", current.session_id)
        .order(table === "frames" ? "frame_idx" : "id")
        .range(from, from + 999);
      if (error) throw error;
      rows.push(...data);
      if (data.length < 1000) break;
    }
    download(`walksafe-${current.session_id.slice(0, 8)}-${table}.csv`, toCsv(rows));
  } catch (e) {
    alert(`Export failed: ${e.message}`);
  } finally {
    button.textContent = label;
    button.disabled = false;
  }
}

function toCsv(rows) {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]);
  const cell = (v) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => cell(r[c])).join(","))].join("\n");
}

function download(name, text) {
  const a = el("a", { href: URL.createObjectURL(new Blob([text], { type: "text/csv" })), download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ── Users ────────────────────────────────────────────────────────────────────

async function serverBase() {
  const { url } = await loadServerUrl();
  if (!url) throw Object.assign(new Error(), { detail: "no_address" });
  return url;
}

async function createUser(e) {
  e.preventDefault();
  const msg = $("#user-form-msg");
  msg.className = "small";
  msg.textContent = "Adding…";
  try {
    const base = await serverBase();
    const role = $("#nu-role").value;
    await api(base, "/api/admin/users", { json: {
      email: $("#nu-email").value, password: $("#nu-password").value, display_name: $("#nu-name").value, role,
    } });
    msg.textContent = role === "admin"
      ? `Added ${$("#nu-email").value} as an admin. They can sign in to this dashboard.`
      : `Added ${$("#nu-email").value}. Sign in with it on their phone.`;
    msg.className = "small ok";
    $("#user-form").reset();
    await loadUsers();
    renderUsers();
  } catch (err) {
    msg.textContent = explain(err);
    msg.className = "small error";
  }
}

function renderUsers() {
  const table = $("#users-table");
  table.replaceChildren(
    el("thead", {}, el("tr", {}, ...["Name", "Email", "Role", "Status", "Sessions", "Added", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, ...users.map((u) => el("tr", {},
      el("td", {}, u.display_name || "—"),
      el("td", {}, u.email),
      el("td", {}, u.role === "admin" ? "Admin" : "Blind user"),
      el("td", {}, u.is_active ? "Active" : "Turned off"),
      el("td", { class: "num" }, fmtNum(u.sessions?.[0]?.count ?? 0)),
      el("td", {}, fmtDateTime(u.created_at)),
      el("td", { class: "actions" }, u.role === "admin" ? "" : [
        el("button", { class: "btn small", onclick: () => changeUser(u, "password") }, "New password"),
        el("button", { class: "btn small", onclick: () => changeUser(u, "active") }, u.is_active ? "Turn off" : "Turn on"),
        el("button", { class: "btn small danger", onclick: () => changeUser(u, "delete") }, "Delete"),
      ]),
    ))),
  );
}

async function changeUser(u, what) {
  const name = u.display_name || u.email;
  let call;
  if (what === "password") {
    const pw = prompt(`New password for ${name} (at least 6 characters):`);
    if (!pw) return;
    call = { method: "PATCH", json: { password: pw } };
  } else if (what === "active") {
    call = { method: "PATCH", json: { active: !u.is_active } };
  } else {
    if (!confirm(`Delete ${name}? They can no longer sign in. Their sessions are kept.`)) return;
    call = { method: "DELETE" };
  }
  try {
    const base = await serverBase();
    await api(base, `/api/admin/users/${u.id}`, call);
    await loadUsers();
    renderUsers();
    if (what === "password") alert(`Password changed for ${name}.`);
  } catch (err) {
    alert(explain(err));
  }
}

// ── Server address ───────────────────────────────────────────────────────────

async function loadServer() {
  const { url, updatedAt } = await loadServerUrl();
  $("#server-url").value = url;
  $("#server-saved").textContent = url ? `Saved address, updated ${fmtDateTime(updatedAt)}.` : "No address saved yet.";
  $("#server-msg").textContent = "";
}

async function testServer() {
  const msg = $("#server-msg");
  msg.className = "small";
  msg.textContent = "Testing…";
  try {
    const h = await health(cleanUrl($("#server-url").value));
    msg.textContent = h.ready ? "Server is running and ready." : "Server answers but is still loading.";
    msg.className = "small ok";
  } catch (err) {
    msg.textContent = explain(err);
    msg.className = "small error";
  }
}

async function saveServer(e) {
  e.preventDefault();
  const msg = $("#server-msg");
  try {
    const url = await saveServerUrl($("#server-url").value);
    $("#server-url").value = url;
    msg.textContent = "Saved. Phones use it from their next start.";
    msg.className = "small ok";
    $("#server-saved").textContent = `Saved address, updated ${fmtDateTime(new Date().toISOString())}.`;
  } catch (err) {
    msg.textContent = `Could not save: ${err.message}`;
    msg.className = "small error";
  }
}
