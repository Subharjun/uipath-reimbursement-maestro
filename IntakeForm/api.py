"""
Intake Form API — FastAPI backend

Receives the expense form submission, uploads the receipt to the UiPath
storage bucket, then starts the Maestro Case with the form data as
trigger inputs (replacing the email intake stage entirely).

Run:
    pip install -r requirements.txt
    uvicorn api:app --reload --port 8000
"""

import asyncio
import io
import json
import os
import re
import smtplib
import subprocess
import uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="Reimbursement Intake API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:4173"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

# ── Config (all overridable via .env) ─────────────────────────────────────────

UIPATH_BASE_URL = os.getenv(
    "UIPATH_BASE_URL",
    "https://staging.uipath.com/hackathon26_332/DefaultTenant",
)

# Numeric Orchestrator folder id for the team AgentHack folder
UIPATH_FOLDER_ID = os.getenv("UIPATH_FOLDER_ID", "3054578")

# Storage bucket id (the "Receipt" bucket)
BUCKET_ID = int(os.getenv("UIPATH_BUCKET_ID", "199727"))

# Maestro Case package key (without version)
CASE_PROCESS_KEY = os.getenv(
    "UIPATH_CASE_PROCESS_KEY",
    "ReimbursementProcessMaestro.caseManagement.ReimbursementProcessCase",
)

# Case subfolder key (where the Case runs)
CASE_FOLDER_KEY = os.getenv(
    "UIPATH_CASE_FOLDER_KEY",
    "49133aec-2677-4b92-bcff-f7e03587bb5b",
)

# Release key UUID — required by `uip maestro case process run --release-key`
CASE_RELEASE_KEY = os.getenv(
    "UIPATH_CASE_RELEASE_KEY",
    "8602dfb7-4304-4768-b853-544f1ef7d972",
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _read_auth_token() -> str:
    """Read the UiPath CLI access token from ~/.uipath/.auth."""
    auth_path = Path.home() / ".uipath" / ".auth"
    if not auth_path.exists():
        raise HTTPException(
            status_code=500,
            detail="UiPath auth file not found at ~/.uipath/.auth — run `uip login` first.",
        )
    for line in auth_path.read_text().splitlines():
        if line.startswith("UIPATH_ACCESS_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise HTTPException(
        status_code=500,
        detail="UIPATH_ACCESS_TOKEN not found in ~/.uipath/.auth — re-run `uip login`.",
    )


def _orchestrator_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-UIPATH-OrganizationUnitId": UIPATH_FOLDER_ID,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ── Bucket upload ─────────────────────────────────────────────────────────────

async def _upload_to_bucket(token: str, filename: str, content: bytes) -> str:
    """
    Upload a receipt file to the UiPath storage bucket.

    Uses the GetWriteUri endpoint to obtain a presigned URL, then PUTs
    the file there directly. Returns the blob path (bare filename).
    """
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    blob_path = safe_name

    write_uri_url = (
        f"{UIPATH_BASE_URL}/orchestrator_/odata/Buckets({BUCKET_ID})"
        f"/UiPath.Server.Configuration.OData.GetWriteUri"
        f"?path={blob_path}&expiryInMinutes=30"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(write_uri_url, headers=_orchestrator_headers(token))
        if r.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Could not get bucket write URI: {r.status_code} {r.text[:300]}",
            )
        presigned_url: str = r.json()["Uri"]

        put_r = await client.put(
            presigned_url,
            content=content,
            headers={
                "Content-Type": "application/octet-stream",
                "x-ms-blob-type": "BlockBlob",
            },
        )
        if put_r.status_code not in (200, 201, 204):
            raise HTTPException(
                status_code=502,
                detail=f"Bucket PUT failed: {put_r.status_code} {put_r.text[:300]}",
            )

    return blob_path


# ── Maestro Case trigger ──────────────────────────────────────────────────────

def _start_maestro_case(input_args: dict) -> dict:
    """
    Start the Maestro Case via the UiPath CLI.

    Returns a dict with at least {"case_id": <str>}.
    The `uip maestro case process run` command handles auth from ~/.uipath/.auth
    and prints the job/case id to stdout on success.
    """
    args_json = json.dumps(input_args)

    # Signature: uip maestro case process run <process-key> <folder-key> --release-key <uuid> -i <json>
    cmd = [
        "uip",
        "maestro",
        "case",
        "process",
        "run",
        CASE_PROCESS_KEY,
        CASE_FOLDER_KEY,
        "--release-key", CASE_RELEASE_KEY,
        "-i", args_json,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="`uip` CLI not found. Install it: npm install -g @uipath/cli",
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Case start timed out after 60 s.")

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if result.returncode != 0:
        # Auth expiry is the most common failure — give a clear hint
        hint = " (run `uip login` to refresh the token)" if "401" in stderr or "Unauthorized" in stderr else ""
        raise HTTPException(
            status_code=502,
            detail=f"Maestro Case start failed{hint}: {stderr or stdout}",
        )

    # Parse jobKey from JSON response (CLI prints pretty-printed JSON block)
    # e.g. {"Result":"Success","Code":"CaseJobStarted","Data":{"jobKey":"...","state":"Pending"}}
    job_id: str | None = None
    try:
        data = json.loads(stdout)
        job_id = data.get("Data", {}).get("jobKey") or data.get("Data", {}).get("caseKey")
    except json.JSONDecodeError:
        # Fallback: scan for bare UUID or numeric id on any line
        for line in stdout.splitlines():
            line = line.strip()
            if re.match(r"^[0-9a-f\-]{36}$", line, re.I) or line.isdigit():
                job_id = line
                break

    return {"job_id": job_id, "cli_output": stdout}


# ── Notification email ────────────────────────────────────────────────────────

NOTIFY_TO = "i.am.mir.jasim@gmail.com"

def _send_notification_email(
    employee_name: str,
    employee_email: str,
    expense_type: str,
    vendor: str,
    amount: float,
    currency: str,
    date: str,
    purpose: str,
    receipt_bytes: bytes | None = None,
    receipt_filename: str | None = None,
) -> None:
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_pass = os.getenv("SMTP_APP_PASSWORD", "").strip()
    if not smtp_user or not smtp_pass:
        return  # silently skip if not configured

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = NOTIFY_TO
    msg["Subject"] = f"New Reimbursement Request — {employee_name} ({currency} {amount:.2f})"

    body = f"""Dear Finance Team,

A new reimbursement request has been submitted via the intake portal.

Total amount: {currency} {amount:.2f}
Date: {date}
Purpose: {purpose}

Employee name: {employee_name}
Employee email: {employee_email}
Expense type: {expense_type}
Vendor: {vendor}

Best regards,
Reimbursement Portal"""

    msg.attach(MIMEText(body, "plain"))

    if receipt_bytes and receipt_filename:
        part = MIMEApplication(receipt_bytes, Name=receipt_filename)
        part["Content-Disposition"] = f'attachment; filename="{receipt_filename}"'
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, NOTIFY_TO, msg.as_string())


async def _notify_async(
    employee_name: str,
    employee_email: str,
    expense_type: str,
    vendor: str,
    amount: float,
    currency: str,
    date: str,
    purpose: str,
    receipt_bytes: bytes | None,
    receipt_filename: str | None,
) -> None:
    try:
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _send_notification_email(
                employee_name, employee_email, expense_type, vendor,
                amount, currency, date, purpose, receipt_bytes, receipt_filename,
            ),
        )
    except Exception:
        pass  # non-fatal — never fail the submission


# ── Submit endpoint ───────────────────────────────────────────────────────────

@app.post("/api/submit")
async def submit(
    employeeName: str = Form(...),
    employeeEmail: str = Form(...),
    managerEmail: str = Form(""),
    expenseType: str = Form(...),
    vendor: str = Form(...),
    amount: str = Form(...),
    currency: str = Form("INR"),
    date: str = Form(...),
    purpose: str = Form(...),
    receipt: UploadFile | None = File(None),
):
    # ── Basic validation ──────────────────────────────────────────────────────
    try:
        amount_float = float(amount)
    except ValueError:
        raise HTTPException(status_code=422, detail="amount must be a number.")

    if amount_float <= 0:
        raise HTTPException(status_code=422, detail="amount must be greater than 0.")

    # ── Auth ──────────────────────────────────────────────────────────────────
    token = _read_auth_token()

    # ── Receipt upload (optional) ─────────────────────────────────────────────
    document_attached = False
    attachment_name: str | None = None
    receipt_bytes: bytes | None = None
    receipt_filename: str | None = None

    if receipt and receipt.filename:
        receipt_bytes = await receipt.read()
        if receipt_bytes:
            receipt_filename = receipt.filename
            attachment_name = await _upload_to_bucket(token, receipt.filename, receipt_bytes)
            document_attached = True

    # ── Build Maestro Case trigger inputs ─────────────────────────────────────
    # Construct a structured reason that the Classification Agent can read.
    constructed_reason = (
        f"Reimbursement request from {employeeName} ({employeeEmail}).\n"
        f"Business purpose: {purpose}\n"
        f"Vendor: {vendor} | Amount: {currency} {amount_float:.2f} | Date: {date}"
    )

    case_inputs: dict = {
        "employeeEmail": employeeEmail.strip(),
        "employeeManagerEmail": managerEmail.strip(),
        "expenseVendor": vendor.strip(),
        "expenseDate": date,
        "expenseAmount": amount_float,
        "expenseCurrency": currency,
        "expenseReason": constructed_reason,
        "expenseTypeConfirmed": expenseType,
        "documentAttached": document_attached,
        "ocrConfidence": 1.0,       # form data is self-attested
        "duplicateDetected": False,
        "businessPurposeValid": True,
    }

    # ── Start Case ────────────────────────────────────────────────────────────
    case_result = _start_maestro_case(case_inputs)

    # Fire notification email non-blocking — never fails the submission
    asyncio.create_task(_notify_async(
        employee_name=employeeName,
        employee_email=employeeEmail,
        expense_type=expenseType,
        vendor=vendor,
        amount=amount_float,
        currency=currency,
        date=date,
        purpose=purpose,
        receipt_bytes=receipt_bytes,
        receipt_filename=receipt_filename,
    ))

    # Generate a stable case_id for the UI (the CLI may return a numeric job id)
    case_id = str(uuid.uuid4())

    return {
        "case_id": case_id,
        "job_id": case_result.get("job_id"),
        "attachment": attachment_name,
        "employee": employeeName,
        "amount": amount_float,
        "currency": currency,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
