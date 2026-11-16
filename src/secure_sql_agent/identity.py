"""Verify the caller's JWT and return the human user id.

Accepts Supabase Auth access tokens. Hosted Supabase projects sign with asymmetric keys
published at <SUPABASE_URL>/auth/v1/.well-known/jwks.json; older projects use the HS256
legacy JWT secret. Both are supported, chosen by the token header.

Rejected on purpose:
  * service_role / anon tokens (a service account must never be the identity),
  * tokens without a UUID `sub`,
  * expired tokens or tokens for another audience/issuer.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient


class InvalidIdentity(Exception):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    sub: uuid.UUID
    claims: dict


class IdentityVerifier:
    def __init__(self, *, issuer: str, audience: str = "authenticated",
                 jwks_url: str | None = None, hs256_secret: str | None = None, leeway_s: int = 10):
        if not jwks_url and not hs256_secret:
            raise ValueError("configure jwks_url and/or hs256_secret")
        self.issuer, self.audience, self.leeway = issuer, audience, leeway_s
        self._jwks = PyJWKClient(jwks_url, cache_keys=True) if jwks_url else None
        self._hs = hs256_secret

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg")
            if alg == "HS256":
                if not self._hs:
                    raise InvalidIdentity("HS256 tokens not accepted")
                key = self._hs
            elif alg in ("ES256", "RS256", "EdDSA"):
                if not self._jwks:
                    raise InvalidIdentity("asymmetric tokens not accepted")
                key = self._jwks.get_signing_key_from_jwt(token).key
            else:
                raise InvalidIdentity(f"unsupported alg {alg!r}")
            claims = jwt.decode(token, key, algorithms=[alg], audience=self.audience, issuer=self.issuer,
                                leeway=self.leeway, options={"require": ["exp", "sub", "aud", "iss"]})
        except InvalidIdentity:
            raise
        except jwt.PyJWTError as e:
            raise InvalidIdentity(str(e)) from e

        if claims.get("role") in ("service_role", "anon", "supabase_admin"):
            raise InvalidIdentity(f"role {claims.get('role')!r} cannot be an end-user identity")
        try:
            sub = uuid.UUID(claims["sub"])
        except (ValueError, TypeError) as e:
            raise InvalidIdentity("sub is not a UUID") from e
        return VerifiedIdentity(sub=sub, claims=claims)
