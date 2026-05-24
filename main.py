from flask import Flask, request, redirect
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
import os

app = Flask(__name__)


def get_xero_client():
    client_id = os.environ.get("XERO_CLIENT_ID")
    client_secret = os.environ.get("XERO_CLIENT_SECRET")

    config = Configuration(
        oauth2_token=OAuth2Token(
            client_id=client_id,
            client_secret=client_secret
        )
    )

    return ApiClient(config)


@app.route("/")
def home():

    redirect_uri = os.environ.get("XERO_REDIRECT_URI")

    api_client = get_xero_client()

    auth_url = api_client.oauth2.get_authorization_url(
        scopes=[
            "offline_access",
            "payroll.employees",
            "payroll.timesheets",
            "payroll.payruns"
        ],
        redirect_uri=redirect_uri
    )

    return redirect(auth_url)


@app.route("/callback")
def callback():

    redirect_uri = os.environ.get("XERO_REDIRECT_URI")

    api_client = get_xero_client()

    code = request.args.get("code")

    token = api_client.oauth2.get_token(
        code=code,
        redirect_uri=redirect_uri
    )

    return "✅ Login successful. Token received!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)