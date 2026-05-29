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
# PAYROLL SETTINGS
# =========================================

PAYROLL_CALENDAR_ID = "cb4913a8-82dc-4d48-ba55-b0d8567f29be"

PERIOD_START = "2026-05-18"

PERIOD_END = "2026-05-24"

PAYMENT_DATE = "2026-05-27"

EXCEL_FILE = "TestTS.xlsx"

# =========================================
# HOME
# =========================================

@app.route("/")
def home():

    # Validate ENV variables
    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI", 500

    # Generate OAuth state
    state = secrets.token_hex(16)

    session["oauth_state"] = state

    # OAuth Parameters
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
    # GET AUTHORIZATION CODE
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
        "Content-Type": "application/json",
    }

    # =====================================
    # READ EXCEL
    # =====================================

    try:

        df = pd.read_excel(EXCEL_FILE)

    except Exception as e:

        return f"""
        <h1>Excel Read Error</h1>
        <pre>{str(e)}</pre>
        """, 500

    print("EXCEL DATA:")
    print(df)

    # =====================================
    # VALIDATE COLUMNS
    # =====================================

    required_columns = [
        "employeeID",
        "date",
        "numberOfUnits",
        "earningsRateID",
    ]

    missing_columns = []

    for column in required_columns:

        if column not in df.columns:
            missing_columns.append(column)

    if missing_columns:

        return f"""
        <h1>Missing Excel Columns</h1>
        <pre>{missing_columns}</pre>
        """, 500

    # =====================================
    # GROUP BY EMPLOYEE
    # =====================================

    grouped = df.groupby("employeeID")

    create_results = []

    # =====================================
    # CREATE TIMESHEETS
    # =====================================

    for employee_id, employee_rows in grouped:

        timesheet_lines = []

        for index, row in employee_rows.iterrows():

            try:

                date = pd.to_datetime(
                    row["date"]
                ).strftime("%Y-%m-%d")

                number_of_units = float(
                    row["numberOfUnits"]
                )

                earnings_rate_id = str(
                    row["earningsRateID"]
                )

                line = {
                    "date": date,
                    "earningsRateID": earnings_rate_id,
                    "numberOfUnits": number_of_units,
                }

                timesheet_lines.append(line)

            except Exception as e:

                create_results.append({
                    "employeeID": employee_id,
                    "status": "FAILED",
                    "error": str(e)
                })

        # =================================
        # BUILD PAYLOAD
        # =================================

        payload = {
            "employeeID": employee_id,
            "payrollCalendarID": PAYROLL_CALENDAR_ID,
            "startDate": PERIOD_START,
            "endDate": PERIOD_END,
            "timesheetLines": timesheet_lines
        }

        print("TIMESHEET PAYLOAD:")
        print(json.dumps(payload, indent=2))

        # =================================
        # CREATE TIMESHEET
        # =================================

        create_response = requests.post(
            TIMESHEETS_URL,
            headers=headers,
            json=payload,
        )

        print("TIMESHEET STATUS:")
        print(create_response.status_code)

        print("TIMESHEET RESPONSE:")
        print(create_response.text)

        create_results.append({
            "employeeID": employee_id,
            "status": create_response.status_code,
            "response": create_response.text
        })

    # =====================================
    # CREATE DRAFT PAY RUN
    # =====================================

    payrun_payload = {
        "payrollCalendarID": PAYROLL_CALENDAR_ID,
        "periodStartDate": PERIOD_START,
        "periodEndDate": PERIOD_END,
        "paymentDate": PAYMENT_DATE
    }

    print("PAYRUN PAYLOAD:")
    print(json.dumps(payrun_payload, indent=2))

    payrun_create_response = requests.post(
        PAYRUNS_URL,
        headers=headers,
        json=payrun_payload,
    )

    print("PAYRUN STATUS:")
    print(payrun_create_response.status_code)

    print("PAYRUN RESPONSE:")
    print(payrun_create_response.text)

    payrun_create_json = payrun_create_response.text

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
    # GET PAY RUNS
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
    # SUCCESS PAGE
    # =====================================

    return f"""

    <h1>✅ Payroll Automation Complete</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Timesheet Upload Results</h2>
    <pre>{json.dumps(create_results, indent=2)}</pre>

    <h2>Pay Run Status</h2>
    <pre>{payrun_create_response.status_code}</pre>

    <h2>Pay Run Response</h2>
    <pre>{payrun_create_json}</pre>

    <h2>All Timesheets</h2>
    <pre>{timesheets_json}</pre>

    <h2>All Pay Runs</h2>
    <pre>{payruns_json}</pre>

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
