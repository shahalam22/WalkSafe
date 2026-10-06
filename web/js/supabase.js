import { createClient } from "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm";
import { SUPABASE_URL, SUPABASE_KEY } from "./config.js";

// The password-reset link in the email opens this page with a login for that
// account in the address (#access_token=…&type=recovery), or an error when the
// link has expired. Read it before the library takes it out of the address.
const hash = new URLSearchParams(location.hash.slice(1));
export const resetLink = {
  recovery: hash.get("type") === "recovery" && hash.has("access_token"),
  failed: hash.has("error_code") || hash.has("error_description"),
};

// The login is kept on the phone and refreshed automatically, so a phone set
// up once stays signed in.
export const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
  auth: { persistSession: true, autoRefreshToken: true, storageKey: "walksafe-auth" },
});

export const roleOf = (session) =>
  session?.user?.app_metadata?.role === "admin" ? "admin" : "blind";
