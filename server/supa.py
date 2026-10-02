"""Talks to Supabase with the secret key: table writes (REST) and user
management (Auth admin API). Only the server holds the secret key."""
import httpx


class SupabaseError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status  = status
        self.message = message


class Supabase:
    def __init__(self, url, secret_key, transport=None, timeout=15.0):
        headers = {"apikey": secret_key}
        if secret_key.startswith("eyJ"):        # older service_role keys are JWTs
            headers["Authorization"] = f"Bearer {secret_key}"
        self.http = httpx.Client(base_url=url.rstrip("/"), headers=headers,
                                 timeout=timeout, transport=transport)

    # ── Tables ────────────────────────────────────────────────────────────────

    def insert(self, table, rows, on_conflict=None):
        if not rows:
            return
        prefer = "return=minimal"
        params = None
        if on_conflict:
            prefer += ",resolution=ignore-duplicates"
            params  = {"on_conflict": on_conflict}
        self._check(self.http.post(f"/rest/v1/{table}", params=params, json=rows,
                                   headers={"Prefer": prefer}))

    def update(self, table, match, values):
        params = {k: f"eq.{v}" for k, v in match.items()}
        self._check(self.http.patch(f"/rest/v1/{table}", params=params, json=values,
                                    headers={"Prefer": "return=minimal"}))

    def select(self, table, match, columns="*"):
        params = {k: f"eq.{v}" for k, v in match.items()}
        params["select"] = columns
        return self._check(self.http.get(f"/rest/v1/{table}", params=params)).json()

    # ── Users ─────────────────────────────────────────────────────────────────

    def create_user(self, email, password, role, display_name):
        r = self.http.post("/auth/v1/admin/users", json={
            "email":         email,
            "password":      password,
            "email_confirm": True,
            "app_metadata":  {"role": role},
            "user_metadata": {"display_name": display_name},
        })
        return self._check(r).json()

    def update_user(self, user_id, **attrs):
        return self._check(self.http.put(f"/auth/v1/admin/users/{user_id}", json=attrs)).json()

    def delete_user(self, user_id):
        self._check(self.http.delete(f"/auth/v1/admin/users/{user_id}"))

    @staticmethod
    def _check(r):
        if r.is_success:
            return r
        try:
            body = r.json()
            msg  = body.get("msg") or body.get("message") or body.get("error_description") \
                   or body.get("error") or r.text
        except ValueError:
            msg = r.text
        raise SupabaseError(r.status_code, msg)
