from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets
import json
import pandas as pd

app = Flask(__name__)

# =========================================
# SECRET KEY
# =========================================

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "super-secret-key"
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

SETTINGS_URL = "https://api.xero.com/payroll.xro/2.0/Settings"

TIMESHEETS_URL = "https://api.xero.com/payroll.xro/2.0/Timesheets"

EMPLOYEES_URL = "https://api.xero.com/payroll.xro/2.0/Employees"

# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    state = secrets.token_hex(16)

    session["oauth_state"] = state

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
            "payroll.settings"
        ),
        "state": state,
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    return redirect(auth_url)

# =========================================
# CALLBACK
# =========================================

@app.route("/callback")
def callback():

    # =====================================
    # VALIDATE STATE
    # =====================================

    returned_state = request.args.get("state")

    if returned_state != session.get("oauth_state"):
        return "Invalid OAuth state"

    # =====================================
    # GET AUTH CODE
    # =====================================

    code = request.args.get("code")

    if not code:
        return "No code received"

    # =====================================
    # TOKEN REQUEST
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
            "Accept": "application/json"
        }
    )

    token_json = token_response.json()

    access_token = token_json.get("access_token")

    if not access_token:
        return f"""
        <h1>Token Error</h1>
        <pre>{json.dumps(token_json, indent=2)}</pre>
        """

    # =====================================
    # GET TENANT
    # =====================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
    )

    connections_json = connections_response.json()

    if not connections_json:
        return "No tenants found"

    tenant_id = connections_json[0]["tenantId"]

    tenant_name = connections_json[0]["tenantName"]

    # =====================================
    # HEADERS
    # =====================================

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json"
    }

    # =====================================
    # GET SETTINGS
    # =====================================

    settings_response = requests.get(
        SETTINGS_URL,
        headers=headers
    )

    # =====================================
    # HANDLE SETTINGS ERROR
    # =====================================

    if settings_response.status_code != 200:

        return f"""
        <h1>API ERROR</h1>

        <h2>Status</h2>
        <pre>{settings_response.status_code}</pre>

        <h2>Response</h2>
        <pre>{settings_response.text}</pre>
        """

    # =====================================
    # PARSE JSON
    # =====================================

    settings_json = settings_response.json()

    earnings_rates = settings_json.get("earningsRates", [])

    # =====================================
    # BUILD HTML TABLE
    # =====================================

    earnings_html = """
    <table border="1" cellpadding="5">
        <tr>
            <th>Name</th>
            <th>Earnings Rate ID</th>
            <th>Account Code</th>
            <th>Type Of Units</th>
        </tr>
    """

    for rate in earnings_rates:

        earnings_html += f"""
        <tr>
            <td>{rate.get('name')}</td>
            <td>{rate.get('earningsRateID')}</td>
            <td>{rate.get('accountCode')}</td>
            <td>{rate.get('typeOfUnits')}</td>
        </tr>
        """

    earnings_html += "</table>"

    # =====================================
    # OPTIONAL EXCEL LOAD
    # =====================================

    excel_output = ""

    try:

        df = pd.read_excel("TestTS.xlsx")

        excel_output = df.to_html(index=False)

    except Exception as e:

        excel_output = f"""
        <h3>Excel Error</h3>
        <pre>{str(e)}</pre>
        """

    # =====================================
    # GET EMPLOYEES
    # =====================================

    employees_response = requests.get(
        EMPLOYEES_URL,
        headers=headers
    )

    employees_text = employees_response.text

    # =====================================
    # RETURN PAGE
    # =====================================

    return f"""

    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Earnings Rates</h2>

    {earnings_html}

    <h2>Excel File</h2>

    {excel_output}

    <h2>Employees</h2>

    <pre>{employees_text}</pre>

    """

# =========================================
# ERROR HANDLER
# =========================================

@app.errorhandler(Exception)
def handle_error(e):

    return f"""
    <h1>Application Error</h1>
    <pre>{str(e)}</pre>
    """, 500

# =========================================
# START APP
# =========================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )