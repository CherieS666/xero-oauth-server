from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets

app = Flask(__name__)

# =========================================
# FLASK SECRET
# =========================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret"
)

# =========================================
# ENV VARIABLES
# =========================================

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

# =========================================
# XERO URLS
# =========================================

AUTH_URL = "https://login.xero.com/identity/connect/authorize"

TOKEN_URL = "https://identity.xero.com/connect/token"

CONNECTIONS_URL = "https://api.xero.com/connections"

EMPLOYEES_URL = "https://api.xero.com/payroll.xro/2.0/Employees"

# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    # Check env vars
    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI", 500

    # Create OAuth state
    state = secrets.token_hex(16)

    session["oauth_state"] = state

    # OAuth parameters
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": (
            "openid "
            "profile "
            "email "
            "offline_access "
            "payroll.employees "
            "payroll.timesheets "
            "payroll.payruns"
        ),
        "state": state,
    }

    # Build auth URL
    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    print("AUTH URL:")
    print(auth_url)

    # Redirect to Xero login
    return redirect(auth_url)

# =========================================
# CALLBACK
# =========================================

@app.route("/callback")
def callback():

    # Check state
    returned_state = request.args.get("state")

    if returned_state != session.get("oauth_state"):
        return "Invalid state parameter", 400

    # Get auth code
    code = request.args.get("code")

    if not code:
        return "No authorization code received", 400

    # =====================================
    # EXCHANGE CODE FOR TOKEN
    # =====================================

    token_response = requests.post(
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

    # Debugging
    print("TOKEN STATUS:")
    print(token_response.status_code)

    print("TOKEN RESPONSE:")
    print(token_response.text)

    # Check token response
    if token_response.status_code != 200:
        return f"""
        <h2>Token Error</h2>
        <pre>{token_response.text}</pre>
        """, 500

    # Parse token JSON
    token_data = token_response.json()

    access_token = token_data["access_token"]

    refresh_token = token_data["refresh_token"]

    # Save tokens in session
    session["access_token"] = access_token
    session["refresh_token"] = refresh_token

    # =====================================
    # GET XERO CONNECTIONS
    # =====================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )

    connections_data = connections_response.json()

    print("CONNECTIONS:")
    print(connections_data)

    # Check if any tenants exist
    if not connections_data:
        return "No Xero tenants found", 400

    # Get first tenant
    tenant_id = connections_data[0]["tenantId"]

    tenant_name = connections_data[0]["tenantName"]

    # Save tenant info
    session["tenant_id"] = tenant_id

    # =====================================
    # API HEADERS
    # =====================================

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }

    # =====================================
    # GET PAYROLL EMPLOYEES
    # =====================================

    employees_response = requests.get(
        EMPLOYEES_URL,
        headers=headers,
    )

    print("EMPLOYEES STATUS:")
    print(employees_response.status_code)

    print("EMPLOYEES RESPONSE:")
    print(employees_response.text)

    # =====================================
    # SUCCESS PAGE
    # =====================================

    return f"""
    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Employees API Response</h2>
    <pre>{employees_response.text}</pre>
    """

# =========================================
# ERROR HANDLER
# =========================================

@app.errorhandler(Exception)
def handle_exception(e):

    return f"""
    <h1>Application Error</h1>
    <pre>{str(e)}</pre>
    """, 500

# =========================================
# START SERVER
# =========================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )