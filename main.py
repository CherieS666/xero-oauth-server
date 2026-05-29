
from flask import Flask, request, redirect, session
from urllib.parse import urlencode

import os
import secrets
import requests
import json
import pandas as pd

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-secret"
)

# =====================================================
# ENV VARIABLES
# =====================================================

CLIENT_ID = os.environ.get("XERO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("XERO_CLIENT_SECRET")
REDIRECT_URI = os.environ.get("XERO_REDIRECT_URI")

# =====================================================
# XERO URLS
# =====================================================

AUTH_URL = "https://login.xero.com/identity/connect/authorize"

TOKEN_URL = "https://identity.xero.com/connect/token"

CONNECTIONS_URL = "https://api.xero.com/connections"

TIMESHEETS_URL = "https://api.xero.com/payroll.xro/2.0/Timesheets"

EMPLOYEES_URL = "https://api.xero.com/payroll.xro/2.0/Employees"

PAYRUNS_URL = "https://api.xero.com/payroll.xro/2.0/PayRuns"

# =====================================================
# PAYROLL CALENDAR IDS
# =====================================================

WEEKLY_CALENDAR_ID = "cb4913a8-82dc-4d48-ba55-b0d8567f29be"

FORTNIGHTLY_CALENDAR_ID = "590c0331-8b61-40ac-bbfa-33d7ed78e5d6"

# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():

    if not CLIENT_ID:
        return "Missing XERO_CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing XERO_CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing XERO_REDIRECT_URI", 500

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
            "payroll.payruns"
        ),
        "state": state,
    }

    auth_url = f"{AUTH_URL}?{urlencode(params)}"

    return redirect(auth_url)

# =====================================================
# HELPER FUNCTIONS
# =====================================================

def build_headers(access_token, tenant_id):

    return {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

def get_calendar_and_dates(work_date, payroll_type):

    if payroll_type == "Weekly":

        payroll_calendar_id = WEEKLY_CALENDAR_ID

        start_date = (
            work_date
            - pd.Timedelta(days=work_date.weekday())
        )

        end_date = (
            start_date
            + pd.Timedelta(days=6)
        )

        total_days = 7

    else:

        payroll_calendar_id = FORTNIGHTLY_CALENDAR_ID

        start_date = (
            work_date
            - pd.Timedelta(days=work_date.weekday())
        )

        end_date = (
            start_date
            + pd.Timedelta(days=13)
        )

        total_days = 14

    return (
        payroll_calendar_id,
        start_date,
        end_date,
        total_days
    )

# =====================================================
# CALLBACK
# =====================================================

@app.route("/callback")
def callback():

    # =================================================
    # VALIDATE STATE
    # =================================================

    returned_state = request.args.get("state")

    if returned_state != session.get("oauth_state"):
        return "Invalid OAuth state", 400

    # =================================================
    # GET AUTH CODE
    # =================================================

    code = request.args.get("code")

    if not code:
        return "Missing authorization code", 400

    # =================================================
    # EXCHANGE TOKEN
    # =================================================

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

    # =================================================
    # GET CONNECTIONS
    # =================================================

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

    connections = connections_response.json()

    if not connections:
        return "No tenants found", 400

    tenant = connections[0]

    tenant_id = tenant["tenantId"]

    tenant_name = tenant["tenantName"]

    session["tenant_id"] = tenant_id

    headers = build_headers(access_token, tenant_id)

    # =================================================
    # READ EXCEL
    # =================================================

    excel_path = "TestTS.xlsx"

    df = pd.read_excel(excel_path)

    print("======================================")
    print("EXCEL DATA")
    print("======================================")

    print(df)

    # =================================================
    # CLEAN DATA
    # =================================================

    df["employeeID"] = (
        df["employeeID"]
        .astype(str)
        .str.strip()
    )

    df["earningsRateID"] = (
        df["earningsRateID"]
        .astype(str)
        .str.strip()
    )

    df["payrollType"] = (
        df["payrollType"]
        .astype(str)
        .str.strip()
    )

    df["date"] = pd.to_datetime(df["date"])

    df["numberOfUnits"] = (
        df["numberOfUnits"]
        .astype(float)
    )

    # =================================================
    # BUILD GROUPED TIMESHEETS
    # =================================================

    grouped_timesheets = {}

    for _, row in df.iterrows():

        employee_id = row["employeeID"]

        payroll_type = row["payrollType"]

        work_date = row["date"]

        earnings_rate_id = row["earningsRateID"]

        number_of_units = float(row["numberOfUnits"])

        (
            payroll_calendar_id,
            start_date,
            end_date,
            total_days
        ) = get_calendar_and_dates(
            work_date,
            payroll_type
        )

        start_date_str = start_date.strftime("%Y-%m-%d")

        end_date_str = end_date.strftime("%Y-%m-%d")

        key = (
            employee_id,
            payroll_calendar_id,
            start_date_str,
            end_date_str
        )

        # =============================================
        # CREATE BASE TIMESHEET
        # =============================================

        if key not in grouped_timesheets:

            grouped_timesheets[key] = {
                "employeeID": employee_id,
                "payrollCalendarID": payroll_calendar_id,
                "startDate": start_date_str,
                "endDate": end_date_str,
                "lines": {}
            }

        # =============================================
        # CREATE EARNINGS LINE
        # =============================================

        if earnings_rate_id not in grouped_timesheets[key]["lines"]:

            grouped_timesheets[key]["lines"][
                earnings_rate_id
            ] = [0] * total_days

        # =============================================
        # DAY INDEX
        # =============================================

        day_index = (
            work_date - start_date
        ).days

        grouped_timesheets[key]["lines"][
            earnings_rate_id
        ][day_index] += number_of_units

    # =================================================
    # CREATE TIMESHEETS
    # =================================================

    all_results = []

    for key, ts in grouped_timesheets.items():

        timesheet_lines = []

        for earnings_rate_id, units_array in ts["lines"].items():

            timesheet_lines.append({
                "earningsRateID": earnings_rate_id,
                "numberOfUnits": units_array
            })

        payload = {
            "employeeID": ts["employeeID"],
            "payrollCalendarID": ts["payrollCalendarID"],
            "startDate": ts["startDate"],
            "endDate": ts["endDate"],
            "timesheetLines": timesheet_lines
        }

        print("======================================")
        print("TIMESHEET PAYLOAD")
        print("======================================")

        print(json.dumps(payload, indent=2))

        try:

            create_response = requests.post(
                TIMESHEETS_URL,
                headers=headers,
                json=payload,
            )

            print("STATUS:")
            print(create_response.status_code)

            print("RESPONSE:")
            print(create_response.text)

            all_results.append({
                "employeeID": ts["employeeID"],
                "status": create_response.status_code,
                "response": create_response.text,
            })

        except Exception as e:

            all_results.append({
                "employeeID": ts["employeeID"],
                "status": "ERROR",
                "response": str(e),
            })

    # =================================================
    # GET EMPLOYEES
    # =================================================

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

    # =================================================
    # GET TIMESHEETS
    # =================================================

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

    # =================================================
    # GET PAYRUNS
    # =================================================

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

    # =================================================
    # BUILD RESULTS HTML
    # =================================================

    results_html = ""

    for result in all_results:

        results_html += f"""
        <h3>Employee ID</h3>
        <pre>{result["employeeID"]}</pre>

        <h3>Status</h3>
        <pre>{result["status"]}</pre>

        <h3>Response</h3>
        <pre>{result["response"]}</pre>

        <hr>
        """

    # =================================================
    # SUCCESS PAGE
    # =================================================

    return f"""

    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Upload Results</h2>

    {results_html}

    <h2>Employees</h2>
    <pre>{employees_json}</pre>

    <h2>Timesheets</h2>
    <pre>{timesheets_json}</pre>

    <h2>Pay Runs</h2>
    <pre>{payruns_json}</pre>

    """

# =====================================================
# ERROR HANDLER
# =====================================================

@app.errorhandler(Exception)
def handle_exception(e):

    return f"""
    <h1>Application Error</h1>
    <pre>{str(e)}</pre>
    """, 500

# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )


