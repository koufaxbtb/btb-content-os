import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

META_API_VERSION = os.environ.get("META_API_VERSION", "v24.0")
META_APP_ID = os.environ.get("META_APP_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "")


@app.get("/")
def home():
    return {
        "service": "BTB Content OS",
        "status": "ok",
        "instagram_oauth": "/auth/instagram",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/instagram")
def instagram_login():
    if not META_APP_ID or not META_REDIRECT_URI:
        return {"error": "META_APP_ID and META_REDIRECT_URI must be configured"}, 500

    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "state": state,
        "response_type": "code",
        "scope": ",".join(
            [
                "instagram_basic",
                "instagram_content_publish",
                "instagram_manage_insights",
                "pages_show_list",
                "pages_read_engagement",
                "business_management",
            ]
        ),
    }
    return redirect(f"https://www.facebook.com/{META_API_VERSION}/dialog/oauth?{urlencode(params)}")


@app.get("/auth/instagram/callback")
def instagram_callback():
    error = request.args.get("error")
    if error:
        return {
            "error": error,
            "error_description": request.args.get("error_description", ""),
        }, 400

    if request.args.get("state") != session.pop("oauth_state", None):
        return {"error": "Invalid OAuth state"}, 400

    code = request.args.get("code")
    if not code:
        return {"error": "Missing authorization code"}, 400

    if not all([META_APP_ID, META_APP_SECRET, META_REDIRECT_URI]):
        return {"error": "Meta OAuth environment variables are incomplete"}, 500

    response = requests.get(
        f"https://graph.facebook.com/{META_API_VERSION}/oauth/access_token",
        params={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "redirect_uri": META_REDIRECT_URI,
            "code": code,
        },
        timeout=20,
    )

    if not response.ok:
        return {"error": "Token exchange failed", "meta": response.json()}, response.status_code

    token_data = response.json()
    # Do not print or expose the access token in logs or the browser.
    return {
        "status": "connected",
        "message": "Instagram authorization succeeded. Token received securely by the server.",
        "token_type": token_data.get("token_type", "bearer"),
        "expires_in": token_data.get("expires_in"),
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
