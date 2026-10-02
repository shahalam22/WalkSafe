"""Checks Supabase login tokens on the server.

Supabase signs tokens with a key whose public half it publishes (JWKS). The
public key is fetched once and cached, so checking a token on every frame
costs no call to Supabase.
"""
from dataclasses import dataclass

import jwt

ROLES = ("admin", "blind")


@dataclass(frozen=True)
class User:
    id:    str
    email: str
    role:  str      # "admin" or "blind"

    @property
    def is_admin(self):
        return self.role == "admin"


class AuthError(Exception):
    pass


class Verifier:
    def __init__(self, supabase_url, jwks_client=None):
        self.issuer = f"{supabase_url.rstrip('/')}/auth/v1"
        self.jwks   = jwks_client or jwt.PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json", cache_keys=True, lifespan=3600)

    def verify(self, token) -> User:
        try:
            key    = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["ES256", "RS256"],
                                audience="authenticated", issuer=self.issuer)
        except jwt.PyJWTError as e:
            raise AuthError(str(e)) from e
        role = (claims.get("app_metadata") or {}).get("role")
        return User(claims["sub"], claims.get("email", ""), role if role in ROLES else "blind")
