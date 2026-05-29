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

TIMESHEETS_URL = "https://api.xero.com/payroll.xro/2.0/Timesheets"

PAYRUNS_URL = "https://api.xero.com/payroll.xro/2.0/PayRuns"

EARNINGS_URL = "https://api.xero.com/payroll.xro/2.0/EarningsRates"

# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI", 500

    # OAuth state
    state = secrets.token_hex(16)

    session["oauth_state"] = state

    # OAuth params
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
        return "Invalid state parameter", 400

    # =====================================
    # GET AUTH CODE
    # =====================================

    code = request.args.get("code")

    if not code:
        return "No authorization code received", 400

    # =====================================
    # EXCHANGE TOKEN
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

    if token_response.status_code != 200:

        return f"""
        <h1>Token Error</h1>
        <pre>{token_response.text}</pre>
        """, 500

    token_data = token_response.json()

    access_token = token_data.get("access_token")

    refresh_token = token_data.get("refresh_token")

    session["access_token"] = access_token
    session["refresh_token"] = refresh_token

    # =====================================
    # GET CONNECTIONS
    # =====================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )

    if connections_response.status_code != 200:

        return f"""
        <h1>Connections Error</h1>
        <pre>{connections_response.text}</pre>
        """, 500

    connections_data = connections_response.json()

    if not connections_data:
        return "No Xero tenants found", 400

    tenant_id = connections_data[0]["tenantId"]

    tenant_name = connections_data[0]["tenantName"]

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
    # READ EXCEL FILE
    # =====================================

    excel_path = "TestTS.xlsx"

    df = pd.read_excel(excel_path)

    print("EXCEL DATA:")
    print(df)

    # =====================================
    # FIRST ROW
    # =====================================

    row = df.iloc[0]

    employee_id = row["employeeID"]

    date = pd.to_datetime(row["date"]).strftime("%Y-%m-%d")

    number_of_units = float(row["numberOfUnits"])

    earnings_rate_id = "3747f42a-4cda-40c6-8e8f-896cd931f557"

    # =====================================
    # PAYROLL CALENDAR
    # =====================================

    payroll_calendar_id = "cb4913a8-82dc-4d48-ba55-b0d8567f29be"

    # =====================================
    # BUILD PAYLOAD
    # =====================================

    payload = {
        "employeeID": employee_id,
        "payrollCalendarID": payroll_calendar_id,
        "startDate": "2026-05-25",
        "endDate": "2026-05-31",
        "timesheetLines": [
            {
                "date": date,
                "earningsRateID": earnings_rate_id,
                "numberOfUnits": number_of_units,
            }
        ]
    }

    print("PAYLOAD:")
    print(json.dumps(payload, indent=2))

    # =====================================
    # CREATE TIMESHEET
    # =====================================

    create_response = requests.post(
        TIMESHEETS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Xero-tenant-id": tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
    )

    print("CREATE STATUS:")
    print(create_response.status_code)

    print("CREATE RESPONSE:")
    print(create_response.text)

    create_json = create_response.text

    # =====================================
    # GET EMPLOYEES
    # =====================================

    employees_response = requests.get(
        EMPLOYEES_URL,
        headers=headers,
    )

    try:
        employees_json = json.dumps(
            employees_response.json(),
            indent=2
        )
    except Exception:
        employees_json = employees_response.text

    # =====================================
    # GET TIMESHEETS
    # =====================================

    timesheets_response = requests.get(
        TIMESHEETS_URL,
        headers=headers,
    )

    try:
        timesheets_json = json.dumps(
            timesheets_response.json(),
            indent=2
        )
    except Exception:
        timesheets_json = timesheets_response.text

    # =====================================
    # GET PAYRUNS
    # =====================================

    payruns_response = requests.get(
        PAYRUNS_URL,
        headers=headers,
    )

    try:
        payruns_json = json.dumps(
            payruns_response.json(),
            indent=2
        )
    except Exception:
        payruns_json = payruns_response.text

    # =====================================
    # GET EARNINGS RATES
    # =====================================



    # =====================================
    # SUCCESS PAGE
    # =====================================

    return f"""

    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Create Timesheet Status</h2>
    <pre>{create_response.status_code}</pre>

    <h2>Create Timesheet Response</h2>
    <pre>{create_json}</pre>

    <h2>Employees</h2>
    <pre>{employees_json}</pre>

    <h2>Timesheets</h2>
    <pre>{timesheets_json}</pre>

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