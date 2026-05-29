```python
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

PAYROLL_CALENDARS_URL = "https://api.xero.com/payroll.xro/2.0/PayrollCalendars"

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
            "payroll.settings "
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

    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid state", 400

    code = request.args.get("code")

    if not code:
        return "No code received", 400

    # ==================================================
    # GET ACCESS TOKEN
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

    token_json = token_response.json()

    access_token = token_json["access_token"]

    # ==================================================
    # GET TENANT
    # ==================================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
    )

    connections = connections_response.json()

    tenant_id = connections[0]["tenantId"]

    tenant_name = connections[0]["tenantName"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Accept": "application/json",
    }

    # ==================================================
    # GET EARNINGS RATES
    # ==================================================

    settings_response = requests.get(
        SETTINGS_URL,
        headers=headers
    )

    settings_json = settings_response.json()

    earnings_rates = settings_json.get("settings", {}).get(
        "earningsRates",
        []
    )

    earnings_table = """
    <table border="1" cellpadding="5">
    <tr>
        <th>Name</th>
        <th>Earnings Rate ID</th>
        <th>Account Code</th>
        <th>Type Of Units</th>
    </tr>
    """

    for rate in earnings_rates:

        earnings_table += f"""
        <tr>
            <td>{rate.get('name')}</td>
            <td>{rate.get('earningsRateID')}</td>
            <td>{rate.get('accountCode')}</td>
            <td>{rate.get('typeOfUnits')}</td>
        </tr>
        """

    earnings_table += "</table>"

    # ==================================================
    # GET PAYROLL CALENDARS
    # ==================================================

    calendar_response = requests.get(
        PAYROLL_CALENDARS_URL,
        headers=headers
    )

    calendars_json = calendar_response.json()

    payroll_calendars = calendars_json.get(
        "payrollCalendars",
        []
    )

    # ==================================================
    # READ EXCEL
    # ==================================================

    df = pd.read_excel("TestTS.xlsx")

    all_results = []

    # ==================================================
    # LOOP EXCEL ROWS
    # ==================================================

    for _, row in df.iterrows():

        try:

            employee_id = row["employeeID"]

            payroll_type = row["payrollType"]

            work_date = pd.to_datetime(row["date"])

            work_date_str = work_date.strftime("%Y-%m-%d")

            earnings_rate_id = row["earningsRateID"]

            number_of_units = float(row["numberOfUnits"])

            # ==========================================
            # FIND MATCHING CALENDAR
            # ==========================================

            matched_calendar = None

            for cal in payroll_calendars:

                if cal["calendarType"].lower() == payroll_type.lower():

                    matched_calendar = cal
                    break

            if not matched_calendar:

                raise Exception(
                    f"No calendar found for {payroll_type}"
                )

            payroll_calendar_id = matched_calendar[
                "payrollCalendarID"
            ]

            # ==========================================
            # CALCULATE PERIOD
            # ==========================================

            if payroll_type.lower() == "weekly":

                # Sunday -> Saturday

                days_from_sunday = (
                    work_date.weekday() + 1
                ) % 7

                start_date = (
                    work_date
                    - pd.Timedelta(days=days_from_sunday)
                )

                end_date = (
                    start_date
                    + pd.Timedelta(days=6)
                )

            else:

                # Fortnightly

                days_from_monday = work_date.weekday()

                start_date = (
                    work_date
                    - pd.Timedelta(days=days_from_monday)
                )

                end_date = (
                    start_date
                    + pd.Timedelta(days=13)
                )

            start_date_str = start_date.strftime("%Y-%m-%d")

            end_date_str = end_date.strftime("%Y-%m-%d")

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
                        "numberOfUnits": number_of_units,
                    }
                ]
            }

            print(json.dumps(payload, indent=2))

            # ==========================================
            # CREATE TIMESHEET
            # ==========================================

            response = requests.post(
                TIMESHEETS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Xero-tenant-id": tenant_id,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            all_results.append({
                "employeeID": employee_id,
                "status": response.status_code,
                "response": response.text,
            })

        except Exception as e:

            all_results.append({
                "employeeID": row.get("employeeID", "UNKNOWN"),
                "status": "ERROR",
                "response": str(e),
            })

    # ==================================================
    # RESULTS HTML
    # ==================================================

    results_html = ""

    for result in all_results:

        results_html += f"""
        <h3>Employee ID</h3>
        <pre>{result['employeeID']}</pre>

        <h3>Status</h3>
        <pre>{result['status']}</pre>

        <h3>Response</h3>
        <pre>{result['response']}</pre>

        <hr>
        """

    return f"""

    <h1>✅ Xero Connected Successfully</h1>

    <h2>Tenant Name</h2>
    <pre>{tenant_name}</pre>

    <h2>Earnings Rates</h2>

    {earnings_table}

    <h2>Upload Results</h2>

    {results_html}

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

    port = int(os.environ.get("PORT", 5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )
```
