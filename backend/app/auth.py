"""Microsoft Entra ID JWT bearer-token validation for FastAPI.

Validates v2.0 access tokens issued by Entra ID for this API:
    - signature against the tenant's JWKS (cached)
    - issuer matches https://login.microsoftonline.com/<tenant>/v2.0
    - audience matches the API app id (GUID or api://GUID)
    - the required delegated scope is present in the `scp` claim
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
import jwt
from cachetools import TTLCache
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

logger = logging.getLogger("declagent.auth")

TENANT_ID = os.environ["TENANT_ID"]
API_APP_ID = os.environ["API_APP_ID"]
REQUIRED_SCOPE = os.environ.get("REQUIRED_SCOPE", "access_as_user")

ISSUER_V2 = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
ISSUER_V1 = f"https://sts.windows.net/{TENANT_ID}/"
VALID_ISSUERS = {ISSUER_V1, ISSUER_V2}
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
VALID_AUDIENCES = {API_APP_ID, f"api://{API_APP_ID}"}

_jwk_client = PyJWKClient(JWKS_URI, cache_keys=True, lifespan=3600)
_openid_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=1, ttl=3600)
_bearer = HTTPBearer(auto_error=True)


def _openid_config() -> dict[str, Any]:
    cfg = _openid_cache.get("cfg")
    if cfg is None:
        url = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0/.well-known/openid-configuration"
        cfg = httpx.get(url, timeout=10).raise_for_status().json()
        _openid_cache["cfg"] = cfg
    return cfg


def _decode(token: str) -> dict[str, Any]:
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token).key
        # Validate audience and signature here; validate issuer manually below
        # so that both v1.0 (sts.windows.net) and v2.0 (login.microsoftonline.com)
        # tokens are accepted.
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=list(VALID_AUDIENCES),
            options={"require": ["exp", "iat", "iss", "aud"], "verify_iss": False},
        )
        if claims.get("iss") not in VALID_ISSUERS:
            raise jwt.InvalidIssuerError(
                f"Issuer {claims.get('iss')!r} not in {sorted(VALID_ISSUERS)}"
            )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if claims.get("nbf", 0) > time.time() + 30:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token not yet valid")
    return claims


def _ensure_scope(claims: dict[str, Any]) -> None:
    scopes = set((claims.get("scp") or "").split())
    if REQUIRED_SCOPE not in scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required scope '{REQUIRED_SCOPE}'",
        )


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """FastAPI dependency: returns validated token claims for the caller."""
    token = creds.credentials
    _log_token(token)
    claims = _decode(token)
    _ensure_scope(claims)
    return claims


def _log_token(token: str) -> None:
    """Log the raw bearer token plus its decoded header/payload.

    WARNING: bearer tokens are credentials. This is intended for local
    development only — disable or remove before deploying to any shared
    environment.
    """
    try:
        header = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as exc:
        logger.warning("Received malformed bearer token: %s", exc)
        logger.warning("Raw token: %s", token)
        return

    logger.info("---- Incoming Entra ID bearer token ----")
    logger.info("Raw token: %s", token)
    logger.info("Header: %s", json.dumps(header, indent=2, default=str))
    logger.info("Payload: %s", json.dumps(payload, indent=2, default=str))
    logger.info("----------------------------------------")
