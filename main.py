
from flask import Flask, request, redirect, session
from urllib.parse import urlencode
import os
import requests
import secrets
import json
import pandas as pd

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

EMPLOYEES_URL = "https://api.xero.com/payroll.xro/2.0/Employees"

TIMESHEETS_URL = "https://api.xero.com/payroll.xro/2.0/Timesheets"

SETTINGS_URL = "https://api.xero.com/payroll.xro/2.0/Settings"

# ======================================================
# PAYROLL CALENDARS
# ======================================================

WEEKLY_CALENDAR_ID = "cb4913a8-82dc-4d48-ba55-b0d8567f29be"

FORTNIGHTLY_CALENDAR_ID = "590c0331-8b61-40ac-bbfa-33d7ed78e5d6"

# ======================================================
# HOME
# ======================================================

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
            "payroll.payruns"
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
        return "Invalid OAuth state", 400

    # ==================================================
    # GET AUTH CODE
    # ==================================================

    code = request.args.get("code")

    if not code:
        return "No authorization code", 400

    # ==================================================
    # EXCHANGE TOKEN
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
            "Accept": "application/json"
        }
    )

    if token_response.status_code != 200:

        return f"""
        <h1>Token Error</h1>
        <pre>{token_response.text}</pre>
        """

    token_data = token_response.json()

    access_token = token_data["access_token"]

    # ==================================================
    # GET CONNECTIONS
    # ==================================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
    )

    connections = connections_response.json()

    tenant_id = connections[0]["tenantId"]

    tenant_name = connections[0]["tenantName"]

    # ==================================================
    # HEADERS
    # ==================================================

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json"
    }

    # ==================================================
    # GET SETTINGS
    # ==================================================

    settings_response = requests.get(
        SETTINGS_URL,
        headers=headers
    )

    settings_json = settings_response.json()

    earnings_rates = settings_json.get(
        "earningsRates",
        []
    )

    # ==================================================
    # BUILD EARNINGS TABLE HTML
    # ==================================================

    earnings_html = """
    <table border="1" cellpadding="6">
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
            <td>{rate.get("name")}</td>
            <td>{rate.get("earningsRateID")}</td>
            <td>{rate.get("accountCode")}</td>
            <td>{rate.get("typeOfUnits")}</td>
        </tr>
        """

    earnings_html += "</table>"

    # ==================================================
    # READ EXCEL
    # ==================================================

    excel_path = "TestTS.xlsx"

    df = pd.read_excel(excel_path)

    print(df)

    # ==================================================
    # RESULTS
    # ==================================================

    all_results = []

    # ==================================================
    # LOOP ROWS
    # ==================================================

    for index, row in df.iterrows():

        try:

            # ==========================================
            # EXCEL VALUES
            # ==========================================

            employee_id = str(
                row["employeeID"]
            ).strip()

            payroll_type = str(
                row["payrollType"]
            ).strip()

            work_date = pd.to_datetime(
                row["date"]
            )

            work_date_str = work_date.strftime(
                "%Y-%m-%d"
            )

            number_of_units = float(
                row["numberOfUnits"]
            )

            earnings_rate_id = str(
                row["earningsRateID"]
            ).strip()

            # ==========================================
            # VALIDATION
            # ==========================================

            if not earnings_rate_id:

                raise Exception(
                    "Missing earningsRateID"
                )

            # ==========================================
            # PAYROLL CALENDAR
            # ==========================================

            if payroll_type.lower() == "weekly":

                payroll_calendar_id = WEEKLY_CALENDAR_ID

                start_date = (
                    work_date
                    - pd.Timedelta(days=work_date.weekday())
                )

                end_date = (
                    start_date
                    + pd.Timedelta(days=6)
                )

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

            # ==========================================
            # IMPORTANT
            # XERO NEEDS PYTHON DATE OBJECTS
            # ==========================================

            start_date_str = start_date.date().isoformat()

            end_date_str = end_date.date().isoformat()

            # ==========================================
            # DEBUGGING
            # ==========================================

            print("================================")
            print("EMPLOYEE:", employee_id)
            print("WORK DATE:", work_date_str)
            print("START:", start_date_str)
            print("END:", end_date_str)
            print("EARNINGS RATE:", earnings_rate_id)
            print("================================")

            # ==========================================
            # PAYLOAD
            # ==========================================

            payload = {
                "employeeID": employee_id,
                "payrollCalendarID": payroll_calendar_id,
                "startDate": start_date_str,
                "endDate": end_date_str,
                "timesheetLines": [
                    {
                        "date": work_date_str,
                        "earningsRateID": earnings_rate_id,
                        "numberOfUnits": number_of_units
                    }
                ]
            }

            print(json.dumps(payload, indent=2))

            # ==========================================
            # CREATE TIMESHEET
            # ==========================================

            create_response = requests.post(
                TIMESHEETS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": tenant_id,
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                json=payload
            )

            print(create_response.status_code)
            print(create_response.text)

            all_results.append({
                "employeeID": employee_id,
                "status": create_response.status_code,
                "response": create_response.text
            })

        except Exception as e:

            all_results.append({
                "employeeID": row.get(
                    "employeeID",
                    "UNKNOWN"
                ),
                "status": "ERROR",
                "response": str(e)
            })

    # ==================================================
    # GET ALL TIMESHEETS
    # ==================================================

    timesheets_response = requests.get(
        TIMESHEETS_URL,
        headers=headers
    )

    try:

        timesheets_json = json.dumps(
            timesheets_response.json(),
            indent=2
        )

    except Exception:

        timesheets_json = timesheets_response.text

    # ==================================================
    # BUILD RESULTS HTML
    # ==================================================

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

    # ==================================================
    # FINAL PAGE
    # ==================================================

    return f"""

    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Tenant ID</h2>
    <pre>{tenant_id}</pre>

    <h2>Earnings Rates</h2>

    {earnings_html}

    <h2>Upload Results</h2>

    {results_html}

    <h2>All Timesheets</h2>

    <pre>{timesheets_json}</pre>

    """

# ======================================================
# ERROR HANDLER
# ======================================================

@app.errorhandler(Exception)
def handle_exception(e):

    return f"""
    <h1>Application Error</h1>
    <pre>{str(e)}</pre>
    """, 500

# ======================================================
# START SERVER
# ======================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )

