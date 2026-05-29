from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets
import json

app = Flask(__name__)

# ======================================================
# FLASK SECRET
# ======================================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret"
)

# ======================================================
# ENV VARIABLES
# ======================================================

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

# ======================================================
# XERO URLS
# ======================================================

AUTH_URL = "https://login.xero.com/identity/connect/authorize"

TOKEN_URL = "https://identity.xero.com/connect/token"

CONNECTIONS_URL = "https://api.xero.com/connections"

SETTINGS_URL = "https://api.xero.com/payroll.xro/2.0/Settings"

# ======================================================
# APP
# ======================================================

app = Flask(__name__)

# ======================================================
# HOME
# ======================================================

@app.route("/")
def home():

    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID"

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET"

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI"

    state = secrets.token_hex(16)

    session["oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,

        # IMPORTANT:
        # payroll.settings is REQUIRED
        "scope": (
            "openid "
            "profile "
            "email "
            "offline_access "
            "payroll.settings"
        ),

        "state": state,
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    return redirect(auth_url)

# ======================================================
# CALLBACK
# ======================================================

@app.route("/callback")
def callback():

    # ==================================================
    # VALIDATE STATE
    # ==================================================

    returned_state = request.args.get("state")

    if returned_state != session.get("oauth_state"):
        return "Invalid state"

    # ==================================================
    # GET CODE
    # ==================================================

    code = request.args.get("code")

    if not code:
        return "No code returned"

    # ==================================================
    # TOKEN REQUEST
    # ==================================================

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

    # ==================================================
    # TOKEN ERROR
    # ==================================================

    if token_response.status_code != 200:

        return f"""
        <h1>TOKEN ERROR</h1>
        <pre>{token_response.text}</pre>
        """

    # ==================================================
    # TOKEN JSON
    # ==================================================

    token_json = token_response.json()

    access_token = token_json.get("access_token")

    # ==================================================
    # CONNECTIONS
    # ==================================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )

    # ==================================================
    # CONNECTION ERROR
    # ==================================================

    if connections_response.status_code != 200:

        return f"""
        <h1>CONNECTION ERROR</h1>
        <pre>{connections_response.text}</pre>
        """

    # ==================================================
    # CONNECTION JSON
    # ==================================================

    connections_json = connections_response.json()

    if not connections_json:
        return "No tenants found"

    tenant_id = connections_json[0]["tenantId"]

    tenant_name = connections_json[0]["tenantName"]

    # ==================================================
    # HEADERS
    # ==================================================

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }

    # ==================================================
    # SETTINGS REQUEST
    # ==================================================

    settings_response = requests.get(
        SETTINGS_URL,
        headers=headers,
    )

    # ==================================================
    # RAW RESPONSE
    # ==================================================

    raw_text = settings_response.text

    # ==================================================
    # API ERROR
    # ==================================================

    if settings_response.status_code != 200:

        return f"""
        <h1>API ERROR</h1>

        <h2>Status</h2>
        <pre>{settings_response.status_code}</pre>

        <h2>Response</h2>
        <pre>{raw_text}</pre>
        """

    # ==================================================
    # JSON PARSE
    # ==================================================

    try:
        settings_json = settings_response.json()

    except Exception as e:

        return f"""
        <h1>JSON ERROR</h1>

        <h2>Exception</h2>
        <pre>{str(e)}</pre>

        <h2>Raw Response</h2>
        <pre>{raw_text}</pre>
        """

    # ==================================================
    # DEBUG FULL JSON
    # ==================================================

    pretty_json = json.dumps(
        settings_json,
        indent=2
    )

    # ==================================================
    # EARNINGS RATES
    # ==================================================

    earnings_rates = settings_json.get(
        "earningsRates",
        []
    )

    # ==================================================
    # HTML TABLE
    # ==================================================

    table_rows = ""

    for rate in earnings_rates:

        name = rate.get("name", "")

        earnings_rate_id = rate.get(
            "earningsRateID",
            ""
        )

        account_code = rate.get(
            "accountCode",
            ""
        )

        type_of_units = rate.get(
            "typeOfUnits",
            ""
        )

        table_rows += f"""
        <tr>
            <td>{name}</td>
            <td>{earnings_rate_id}</td>
            <td>{account_code}</td>
            <td>{type_of_units}</td>
        </tr>
        """

    # ==================================================
    # NO DATA
    # ==================================================

    if not earnings_rates:

        table_rows = """
        <tr>
            <td colspan='4'>
                No earnings rates found
            </td>
        </tr>
        """

    # ==================================================
    # SUCCESS PAGE
    # ==================================================

    return f"""

    <h1>✅ Xero Connected</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Earnings Rates</h2>

    <table border="1" cellpadding="8">

        <tr>
            <th>Name</th>
            <th>Earnings Rate ID</th>
            <th>Account Code</th>
            <th>Type Of Units</th>
        </tr>

        {table_rows}

    </table>

    <h2>Raw Settings JSON</h2>

    <pre>{pretty_json}</pre>

    """

# ======================================================
# ERROR HANDLER
# ======================================================

@app.errorhandler(Exception)
def handle_error(e):

    return f"""
    <h1>Application Error</h1>
    <pre>{str(e)}</pre>
    """

# ======================================================
# START
# ======================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )