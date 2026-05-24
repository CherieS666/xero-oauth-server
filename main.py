from flask import Flask, request, redirect
import os
import requests

app = Flask(__name__)

# =========================
# ENV VARIABLES (Render)
# =========================
CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

# =========================
# XERO ENDPOINTS
# =========================
AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"


# =========================
# HOME - REDIRECT TO XERO
# =========================
@app.route("/")
def home():

    if not CLIENT_ID or not REDIRECT_URI:
        return "Missing environment variables", 500

    scope = "offline_access payroll.employees payroll.timesheets payroll.payruns"

    url = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scope}"
    )

    return redirect(url)


# =========================
# CALLBACK - GET CODE
# =========================
@app.route("/callback")
def callback():

    code = request.args.get("code")

    if not code:
        return "No authorization code received", 400

    # =========================
    # EXCHANGE CODE FOR TOKEN
    # =========================
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
    )

    if response.status_code != 200:
        return f"Token Error: {response.text}", 500

    token_data = response.json()

    return f"""
    <h2>✅ Xero Login Successful</h2>
    <pre>{token_data}</pre>
    """


# =========================
# RUN LOCALLY / RENDER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)