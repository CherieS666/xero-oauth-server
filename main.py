from flask import Flask, request, redirect
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
import os

app = Flask(__name__)

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

config = Configuration(
    oauth2_token=OAuth2Token(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
)

api_client = ApiClient(config)


@app.route("/")
def home():
    auth_url = api_client.oauth2.get_authorization_url(
        scopes=[
            "offline_access",
            "payroll.employees",
            "payroll.timesheets",
            "payroll.payruns"
        ],
        redirect_uri=REDIRECT_URI
    )

    return redirect(auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")

    token = api_client.oauth2.get_token(
        code=code,
        redirect_uri=REDIRECT_URI
    )

    return "✅ Login successful. Token received!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)