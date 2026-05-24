from flask import Flask, request
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
import os

app = Flask(__name__)

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")

config = Configuration(
    oauth2_token=OAuth2Token(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
)

api_client = ApiClient(config)

@app.route("/")
def home():
    return "Xero OAuth Server Running"

@app.route("/callback")
def callback():
    code = request.args.get("code")

    token = api_client.oauth2.get_token(
        code=code,
        redirect_uri=os.environ.get("XERO_REDIRECT_URI")
    )

    return f"Login successful! Token received: {token}"

if __name__ == "__main__":
    import os
    port=int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0",port=port)