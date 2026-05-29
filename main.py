
from flask import Flask, request, redirect, session
from urllib.parse import urlencode

import os
import secrets
import requests
import pandas as pd
import json

# =====================================================
# FLASK
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

CLIENT_SECRET = os.environ.get(
    "XERO_CLIENT_SECRET"
)

REDIRECT_URI = os.environ.get(
    "XERO_REDIRECT_URI"
)

# =====================================================
# XERO URLS
# =====================================================

AUTH_URL = (
    "https://login.xero.com/"
    "identity/connect/authorize"
)

TOKEN_URL = (
    "https://identity.xero.com/"
    "connect/token"
)

CONNECTIONS_URL = (
    "https://api.xero.com/connections"
)

EMPLOYEES_URL = (
    "https://api.xero.com/"
    "payroll.xro/2.0/Employees"
)

TIMESHEETS_URL = (
    "https://api.xero.com/"
    "payroll.xro/2.0/Timesheets"
)

PAYRUNS_URL = (
    "https://api.xero.com/"
    "payroll.xro/2.0/PayRuns"
)

# =====================================================
# HOME
# =====================================================

@app.route("/")
def home():

    if not CLIENT_ID:
        return "Missing CLIENT_ID", 500

    if not CLIENT_SECRET:
        return "Missing CLIENT_SECRET", 500

    if not REDIRECT_URI:
        return "Missing REDIRECT_URI", 500

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

    auth_url = (
        f"{AUTH_URL}?"
        f"{urlencode(params)}"
    )

    return redirect(auth_url)

# =====================================================
# HEADERS
# =====================================================

def build_headers(access_token, tenant_id):

    return {
        "Authorization":
            f"Bearer {access_token}",

        "Xero-tenant-id":
            tenant_id,

        "Accept":
            "application/json",

        "Content-Type":
            "application/json",
    }

# =====================================================
# MATCH PAYRUN
# =====================================================

def get_matching_payrun(
    work_date,
    payroll_type,
    payruns_data
):

    for payrun in payruns_data["payRuns"]:

        if (
            payrun["calendarType"].lower()
            != payroll_type.lower()
        ):
            continue

        start_date = pd.to_datetime(
            payrun["periodStartDate"]
        )

        end_date = pd.to_datetime(
            payrun["periodEndDate"]
        )

        if start_date <= work_date <= end_date:

            return {
                "payrollCalendarID":
                    payrun["payrollCalendarID"],

                "startDate":
                    start_date,

                "endDate":
                    end_date,

                "calendarType":
                    payrun["calendarType"]
            }

    return None

# =====================================================
# CALLBACK
# =====================================================

@app.route("/callback")
def callback():

    # =================================================
    # VALIDATE STATE
    # =================================================

    returned_state = request.args.get("state")

    if returned_state != session.get(
        "oauth_state"
    ):
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
            "grant_type":
                "authorization_code",

            "code":
                code,

            "redirect_uri":
                REDIRECT_URI,
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={
            "Accept":
                "application/json",
        },
    )

    if token_response.status_code != 200:

        return f"""
        <h1>Token Error</h1>
        <pre>{token_response.text}</pre>
        """

    token_data = token_response.json()

    access_token = token_data.get(
        "access_token"
    )

    refresh_token = token_data.get(
        "refresh_token"
    )

    session["access_token"] = access_token

    session["refresh_token"] = refresh_token

    # =================================================
    # GET CONNECTIONS
    # =================================================

    connections_response = requests.get(
        CONNECTIONS_URL,
        headers={
            "Authorization":
                f"Bearer {access_token}",

            "Accept":
                "application/json",
        },
    )

    if connections_response.status_code != 200:

        return f"""
        <h1>Connections Error</h1>
        <pre>{connections_response.text}</pre>
        """

    connections = connections_response.json()

    if not connections:
        return "No tenants found"

    tenant = connections[0]

    tenant_id = tenant["tenantId"]

    tenant_name = tenant["tenantName"]

    headers = build_headers(
        access_token,
        tenant_id
    )

    # =================================================
    # GET EMPLOYEES
    # =================================================

    employees_response = requests.get(
        EMPLOYEES_URL,
        headers=headers,
    )

    employees_data = employees_response.json()

    employee_map = {}

    for emp in employees_data["employees"]:

        employee_map[
            emp["employeeID"]
        ] = emp

    # =================================================
    # GET PAYRUNS
    # =================================================

    payruns_response = requests.get(
        PAYRUNS_URL,
        headers=headers,
    )

    payruns_data = payruns_response.json()

    # =================================================
    # READ EXCEL
    # =================================================

    excel_path = "TestTS.xlsx"

    df = pd.read_excel(excel_path)

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

    df["date"] = pd.to_datetime(
        df["date"]
    )

    df["numberOfUnits"] = (
        df["numberOfUnits"]
        .astype(float)
    )

    # =================================================
    # GROUP TIMESHEETS
    # =================================================

    grouped_timesheets = {}

    all_results = []

    for _, row in df.iterrows():

        try:

            employee_id = row["employeeID"]

            payroll_type = row["payrollType"]

            work_date = row["date"]

            earnings_rate_id = (
                row["earningsRateID"]
            )

            number_of_units = float(
                row["numberOfUnits"]
            )

            # =========================================
            # EMPLOYEE EXISTS
            # =========================================

            if employee_id not in employee_map:

                all_results.append({
                    "employeeID":
                        employee_id,

                    "status":
                        "ERROR",

                    "response":
                        "Employee not found"
                })

                continue

            employee = employee_map[
                employee_id
            ]

            # =========================================
            # EMPLOYEE TERMINATED
            # =========================================

            end_date = employee.get("endDate")

            if end_date:

                end_date = pd.to_datetime(
                    end_date
                )

                if work_date > end_date:

                    all_results.append({
                        "employeeID":
                            employee_id,

                        "status":
                            "SKIPPED",

                        "response":
                            (
                                "Work date after "
                                "employee end date"
                            )
                    })

                    continue

            # =========================================
            # MATCH PAYRUN
            # =========================================

            matching_payrun = (
                get_matching_payrun(
                    work_date,
                    payroll_type,
                    payruns_data
                )
            )

            if not matching_payrun:

                all_results.append({
                    "employeeID":
                        employee_id,

                    "status":
                        "ERROR",

                    "response":
                        (
                            "No matching payrun "
                            "found"
                        )
                })

                continue

            payroll_calendar_id = (
                matching_payrun[
                    "payrollCalendarID"
                ]
            )

            start_date = (
                matching_payrun[
                    "startDate"
                ]
            )

            end_date = (
                matching_payrun[
                    "endDate"
                ]
            )

            start_date_str = (
                start_date.strftime(
                    "%Y-%m-%d"
                )
            )

            end_date_str = (
                end_date.strftime(
                    "%Y-%m-%d"
                )
            )

            # =========================================
            # CALENDAR VALIDATION
            # =========================================

            employee_calendar = (
                employee[
                    "payrollCalendarID"
                ]
            )

            if (
                employee_calendar
                != payroll_calendar_id
            ):

                all_results.append({
                    "employeeID":
                        employee_id,

                    "status":
                        "ERROR",

                    "response":
                        (
                            "Employee payroll "
                            "calendar mismatch"
                        )
                })

                continue

            # =========================================
            # TOTAL DAYS
            # =========================================

            if payroll_type.lower() == "weekly":
                total_days = 7
            else:
                total_days = 14

            # =========================================
            # GROUP KEY
            # =========================================

            key = (
                employee_id,
                payroll_calendar_id,
                start_date_str,
                end_date_str
            )

            # =========================================
            # CREATE GROUP
            # =========================================

            if key not in grouped_timesheets:

                grouped_timesheets[key] = {
                    "employeeID":
                        employee_id,

                    "payrollCalendarID":
                        payroll_calendar_id,

                    "startDate":
                        start_date_str,

                    "endDate":
                        end_date_str,

                    "lines":
                        {}
                }

            # =========================================
            # CREATE EARNINGS LINE
            # =========================================

            if (
                earnings_rate_id
                not in grouped_timesheets[
                    key
                ]["lines"]
            ):

                grouped_timesheets[
                    key
                ]["lines"][
                    earnings_rate_id
                ] = [0] * total_days

            # =========================================
            # DAY INDEX
            # =========================================

            day_index = (
                work_date - start_date
            ).days

            grouped_timesheets[
                key
            ]["lines"][
                earnings_rate_id
            ][day_index] += (
                number_of_units
            )

        except Exception as e:

            all_results.append({
                "employeeID":
                    row.get(
                        "employeeID",
                        "UNKNOWN"
                    ),

                "status":
                    "ERROR",

                "response":
                    str(e)
            })

    # =================================================
    # CREATE TIMESHEETS
    # =================================================

    for key, ts in grouped_timesheets.items():

        try:

            timesheet_lines = []

            for (
                earnings_rate_id,
                units_array
            ) in ts["lines"].items():

                timesheet_lines.append({
                    "earningsRateID":
                        earnings_rate_id,

                    "numberOfUnits":
                        units_array
                })

            payload = {
                "employeeID":
                    ts["employeeID"],

                "payrollCalendarID":
                    ts["payrollCalendarID"],

                "startDate":
                    ts["startDate"],

                "endDate":
                    ts["endDate"],

                "timesheetLines":
                    timesheet_lines
            }

            print("================================")
            print("TIMESHEET PAYLOAD")
            print("================================")

            print(
                json.dumps(
                    payload,
                    indent=2
                )
            )

            create_response = requests.post(
                TIMESHEETS_URL,
                headers=headers,
                json=payload,
            )

            print("STATUS:")
            print(
                create_response.status_code
            )

            print("RESPONSE:")
            print(create_response.text)

            all_results.append({
                "employeeID":
                    ts["employeeID"],

                "status":
                    create_response.status_code,

                "response":
                    create_response.text
            })

        except Exception as e:

            all_results.append({
                "employeeID":
                    ts["employeeID"],

                "status":
                    "ERROR",

                "response":
                    str(e)
            })

    # =================================================
    # FORMAT RESULTS
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

    <h1>
    ✅ Xero Connected Successfully
    </h1>

    <h2>Tenant Name</h2>

    <pre>{tenant_name}</pre>

    <h2>Upload Results</h2>

    {results_html}

    """

# =====================================================
# ERROR HANDLER
# =====================================================

@app.errorhandler(Exception)
def handle_exception(e):

    return f"""

    <h1>Application Error</h1>

    <pre>{str(e)}</pre>

    """

# =====================================================
# START SERVER
# =====================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )

