from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"


@app.route("/")
def home():

    state = secrets.token_hex(16)
    session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": (
            "offline_access "
            "payroll.employees "
            "payroll.timesheets "
            "payroll.payruns"
        ),
        "state": state,
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    return redirect(auth_url)


@app.route("/callback")
def callback():

    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid state", 400

    code = request.args.get("code")

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={
            "Accept": "application/json",
        },
    )

    return response.text


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)