import base64
import hashlib
import os
import secrets
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException
from fastapi.responses import RedirectResponse


SESSION = "ledger-account"
VERIFIER = "ledger-pkce"
CALLBACK = "/auth/callback"


class AccountAuth:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")
        self.origin = os.getenv("LEDGER_SITE_URL", "").rstrip("/")

    @property
    def enabled(self):
        return bool(self.url and self.key and self.origin)

    def cookie(self, response, name, value, lifetime):
        response.set_cookie(
            name, value, max_age=lifetime, httponly=True, samesite="lax",
            secure=self.origin.startswith("https://"),
        )

    def start(self):
        if not self.enabled:
            raise HTTPException(404, "Google sign-in is not configured.")
        verifier = secrets.token_urlsafe(48)
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        params = urlencode({
            "provider": "google", "redirect_to": self.origin + CALLBACK,
            "code_challenge": challenge, "code_challenge_method": "s256",
        })
        response = RedirectResponse(f"{self.url}/auth/v1/authorize?{params}", 303)
        self.cookie(response, VERIFIER, verifier, 600)
        return response

    async def finish(self, code, verifier):
        if not self.enabled or not code or not verifier:
            return self.callback_response()
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                result = await client.post(
                    f"{self.url}/auth/v1/token",
                    params={"grant_type": "pkce"},
                    headers={"apikey": self.key},
                    json={"auth_code": code, "code_verifier": verifier},
                )
            result.raise_for_status()
            session = result.json()
            lifetime = min(3600, int(session["expires_in"]))
            token = session["access_token"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return self.callback_response()
        response = self.callback_response(success=True)
        self.cookie(response, SESSION, token, lifetime)
        return response

    def callback_response(self, success=False):
        response = RedirectResponse("/#memory" if success else "/?signin=failed", 303)
        response.delete_cookie(VERIFIER)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def account(self, token):
        if not self.enabled or not token:
            return None
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                result = await client.get(
                    f"{self.url}/auth/v1/user",
                    headers={"apikey": self.key, "Authorization": f"Bearer {token}"},
                )
            if result.status_code in (401, 403):
                return None
            result.raise_for_status()
            user = result.json()
            if user.get("is_anonymous"):
                return None
            return UUID(user["id"]).hex
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Sign-in verification is temporarily unavailable.") from None
