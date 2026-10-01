"""Minimal Instagram OAuth entrypoint for BTB Content OS.

Keeps authentication separate from analytics ingestion. Tokens are not
persisted here; production storage is a later boundary.
"""
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

META_APP_ID = os.environ.get("META_APP_ID")
META_APP_SECRET = os.environ.get("META_APP_SECRET")
META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI")
META_API_VERSION = os.environ.get("META_API_VERSION", "v24.0")

SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_read_engagement",
    "pages_show_list",
]


def _require_config():
    missing = [
        name for name, value in {
            "META_APP_ID": META_APP_ID,
            "META_APP_SECRET": META_APP_SECRET,
            "META_REDIRECT_URI": META_REDIRECT_URI,
        }.items() if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "btb-instagram-oauth"}


@app.get("/auth/instagram")
def instagram_login():
    _require_config()
    state = secrets.token_urlsafe(32)
    session["instagram_oauth_state"] = state
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "state": state,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }
    return redirect(f"https://www.facebook.com/{META_API_VERSION}/dialog/oauth?{urlencode(params)}")


@app.get("/auth/instagram/callback")
def instagram_callback():
    _require_config()
    if request.args.get("error"):
        return {
            "connected": False,
            "error": request.args.get("error"),
            "error_description": request.args.get("error_description"),
        }, 400

    state = request.args.get("state")
    expected_state = session.pop("instagram_oauth_state", None)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return {"connected": False, "error": "invalid_oauth_state"}, 400

    code = request.args.get("code")
    if not code:
        return {"connected": False, "error": "missing_authorization_code"}, 400

    response = requests.get(
        f"https://graph.facebook.com/{META_API_VERSION}/oauth/access_token",
        params={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": META_REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )
    if not response.ok:
        return {"connected": False, "error": "token_exchange_failed"}, 502

    payload = response.json()
    # Deliberately do not return or log the access token.
    return {
        "connected": True,
        "token_received": bool(payload.get("access_token")),
        "next": "Add secure token storage and Instagram account discovery.",
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
