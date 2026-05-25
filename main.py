from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets
import json
import pandas as pd

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

    # Check environment variables
    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI", 500

    # Generate OAuth state
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

    # Redirect user to Xero
    return redirect(auth_url)

# =========================================
# CALLBACK
# =========================================

@app.route("/callback")
def callback():

    # Validate state
    returned_state = request.args.get("state")

    if returned_state != session.get("oauth_state"):
        return "Invalid state parameter", 400

    # Get authorization code
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

    print("TOKEN STATUS:")
    print(token_response.status_code)

    print("TOKEN RESPONSE:")
    print(token_response.text)

    # Check token response
    if token_response.status_code != 200:

        return f"""
        <h1>Token Error</h1>
        <pre>{token_response.text}</pre>
        """, 500

    # =====================================
    # PARSE TOKENS
    # =====================================

    token_data = token_response.json()

    access_token = token_data.get("access_token")

    refresh_token = token_data.get("refresh_token")

    # Save tokens
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

    print("CONNECTIONS STATUS:")
    print(connections_response.status_code)

    print("CONNECTIONS RESPONSE:")
    print(connections_response.text)

    # Check connections response
    if connections_response.status_code != 200:

        return f"""
        <h1>Connections Error</h1>
        <pre>{connections_response.text}</pre>
        """, 500

    connections_data = connections_response.json()

    if not connections_data:
        return "No Xero tenants found", 400

    # =====================================
    # GET TENANT INFO
    # =====================================

    tenant_id = connections_data[0]["tenantId"]

    tenant_name = connections_data[0]["tenantName"]

    # Save tenant
    session["tenant_id"] = tenant_id

    # =====================================
    # XERO API HEADERS
    # =====================================

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }

    # =====================================
    # READ EXCEL FILE
    # =====================================

    excel_path = "TestTS.xlsx"

    df = pd.read_excel(excel_path)

    print(df)

    # =====================================
    # GET EMPLOYEES
    # =====================================

    employees_response = requests.get(
        EMPLOYEES_URL,
        headers=headers,
    )

    timesheets_response = requests.get(
        "https://api.xero.com/payroll.xro/2.0/Timesheets",
        headers=headers,
    )

    print(timesheets_response.text)

    try:
        timesheets_json = json.dumps(
        timesheets_response.json(),
        indent=2
        )
    except Exception:
        timesheets_json=timesheets_response.text

    # =====================================
    # GET DETAILED TIMESHEET
    # =====================================

    timesheet_id = "b133588d-5580-4ccc-b6a4-67c08a811a7f"

    details_response = requests.get(
        f"https://api.xero.com/payroll.xro/2.0/Timesheets/{timesheet_id}",
        headers=headers,
    )

    print("DETAILS RESPONSE:")
    print(details_response.text)

    try:
        details_json = json.dumps(
            details_response.json(),
            indent=2
        )
    except Exception:
        details_json = details_response.text

    # =====================================
    # GET EARNINGS RATES
    # =====================================

    earnings_response = requests.get(
        "https://api.xero.com/payroll.xro/2.0/EarningsRates",
        headers=headers,
    )

    print("EARNINGS STATUS:")
    print(earnings_response.status_code)

    print("EARNINGS RESPONSE:")
    print(earnings_response.text)

    try:
        earnings_json = json.dumps(
            earnings_response.json(),
            indent=2
        )
    except Exception:
        earnings_json = earnings_response.text




    payruns_response = requests.get(
        "https://api.xero.com/payroll.xro/2.0/PayRuns",
        headers=headers,
    )

    try:
        payruns_json = json.dumps(
            payruns_response.json(),
            indent=2
        )
    except Exception:
        payruns_json = payruns_response.text


    print("EMPLOYEES STATUS:")
    print(employees_response.status_code)

    print("EMPLOYEES RESPONSE:")
    print(employees_response.text)

    # =====================================
    # FORMAT EMPLOYEE JSON
    # =====================================

    try:
        employees_json = json.dumps(
            employees_response.json(),
            indent=2
        )
    except Exception:
        employees_json = employees_response.text

    # =====================================
    # SUCCESS PAGE
    # =====================================

    return f"""
    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Employees API Status</h2>
    <pre>{employees_response.status_code}</pre>

    <h2>Employees API Response</h2>
    <pre>{employees_json}</pre>
    
    <h2>Timesheets</h2>
    <pre>{timesheets_json}</pre>
    
    <h2>Detailed Timesheet</h2>
    <pre>{details_json}</pre>
    
    <h2>Pay Runs</h2>
    <pre>{payruns_json}</pre>
    
    <h2>Earnings Rates</h2>
    <pre>{earnings_json}</pre>
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