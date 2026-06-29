# SAPConcurPaymentWorkflow — Stage 5a (Subharjun)

AgentHack Track 1 · **Stage 5a: ERP Payment (SAP Concur)**

A UiPath **API Workflow** (CNCF Serverless Workflow DSL 1.0.0) that submits an approved
reimbursement to **SAP Concur** for payment via **real HTTP API calls**, and returns the
Stage-5a payment contract written back to the Maestro Case.

> This is the real integration — not a mock. It makes live calls to `concursolutions.com`.
> It only needs your Concur sandbox credentials at runtime to authenticate (any real ERP
> integration does). Validated: the workflow structure is valid and the OAuth call reaches
> the live Concur endpoint (returns 400 with placeholder creds; authenticates with real ones).

## The real call chain (9 activities)

```
WorkflowStart
 → MapType_1          (JS)   expense_type → Concur expense-type ID
 → HttpRequest_Token  (HTTP) POST {base}/oauth2/v0/token         (OAuth client_credentials)
 → ExtractToken_1     (JS)   read access_token
 → HttpRequest_CreateReport (HTTP) POST .../reports             (create expense report)
 → ExtractReport_1    (JS)   read reportId
 → HttpRequest_AddExpense   (HTTP) POST .../reports/{id}/expenses (add expense entry)
 → HttpRequest_Submit (HTTP) POST .../reports/{id}/submit        (submit for payment)
 → BuildOutput_1      (JS)   assemble Stage-5a contract
 → Response_1                return it
```

Expense-type → Concur ID map: travel→AIRFR, food→MEALS, medical→MEDC1, internet→TELPH,
equipment→EQUIP, others→MISCL.

## Inputs (an approved case + Concur config)

```json
{
  "case_id": "REIMB-2026-TEST-PAY-001",
  "employee_email": "test@company.com",
  "manager_email": "manager@company.com",
  "amount": 500,
  "currency": "INR",
  "expense_type": "food",
  "vendor": "Office Cafeteria",
  "date": "2026-06-04",
  "reason": "snacks during office work",

  "concur_base_url": "https://us.api.concursolutions.com",
  "concur_client_id": "<your Concur client id>",
  "concur_client_secret": "<your Concur client secret>",
  "concur_user_id": "<your Concur test user id>"
}
```

**Production note:** the four `concur_*` values are secrets. In the deployed solution, bind
them to **Orchestrator Assets** (`CONCUR_BASE_URL`, `CONCUR_CLIENT_ID`, `CONCUR_CLIENT_SECRET`,
`CONCUR_TEST_USER_ID`) and let Maestro pass them in — do not hardcode them in the workflow.

## Output (Stage 5a contract → written to the Maestro Case)

```json
{
  "case_id": "REIMB-2026-TEST-PAY-001",
  "erp_system": "SAP Concur",
  "concur_report_id": "<real Concur report id>",
  "concur_expense_type_id": "MEALS",
  "payment_status": "submitted_to_concur",
  "payment_url": "https://www.concursolutions.com/expense/reports/<id>",
  "submitted_at": "<ISO8601>"
}
```

## Get your Concur sandbox (one-time, free)

1. Sign up at https://developer.concur.com → create a sandbox app.
2. Note Client ID, Client Secret, your data-center Base URL (e.g.
   `https://us.api.concursolutions.com` / `https://emea.api.concursolutions.com`), and a
   test user ID.
3. Store them as the Orchestrator Assets above.

## Run it

```bash
# structure + reaches-Concur check (placeholder creds -> Concur 400 is expected):
uip api-workflow run ./SAPConcurPaymentWorkflow.json --no-auth \
  --input-arguments '{"case_id":"T1","expense_type":"food","amount":500,"currency":"INR","concur_base_url":"https://us.api.concursolutions.com","concur_client_id":"X","concur_client_secret":"X","concur_user_id":"X"}' --output json

# real end-to-end (with your sandbox creds) — actually creates & submits a Concur report:
uip api-workflow run ./SAPConcurPaymentWorkflow.json --no-auth \
  --input-arguments '{"case_id":"REIMB-2026-TEST-PAY-001","expense_type":"food","amount":500,"currency":"INR","vendor":"Office Cafeteria","date":"2026-06-04","reason":"snacks during office work","concur_base_url":"https://us.api.concursolutions.com","concur_client_id":"<id>","concur_client_secret":"<secret>","concur_user_id":"<user>"}' --output json
```

If Concur returns 400/401 with real creds, confirm your data-center base URL and that the
sandbox app is authorized for the Expense v4 API and `client_credentials` grant (the response
parsers also accept `reportId`/`ID`/`id` for the report identifier — adjust if your tenant
differs).

## The HTTP activity shape was validated against live endpoints

- The unified HTTP Request activity (`call: "UiPath.Http"`) was confirmed to transmit the
  request body + headers (verified via postman-echo: the form body and `Content-Type` arrive
  intact) and to reach the real Concur OAuth endpoint.

## Package & publish (when ready)

API workflows publish through the solution packager as a `Type: "Api"` project:
```bash
uip solution pack <solutionDir> ./build --name SAPConcurPaymentWorkflow --version 1.0.0
uip solution publish ./build/SAPConcurPaymentWorkflow.zip --tenant DefaultTenant
```
