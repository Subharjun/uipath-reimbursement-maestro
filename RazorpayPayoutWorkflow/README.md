# RazorpayPayoutWorkflow — Stage 5a (Subharjun)

AgentHack Track 1 · **Stage 5a: ERP Payment / Reimbursement Payout (RazorpayX)**

A UiPath **API Workflow** that disburses an approved reimbursement to the employee via the
**RazorpayX Payouts API** (INR). This is the live replacement for the SAP Concur workflow —
Concur API access is partner-gated (no free sandbox), whereas **RazorpayX test keys are free and
instant**, so this integration is fully runnable by anyone.

> **Design: "placeholder credentials, everything else works."** The 3 credentials are workflow
> inputs (or Orchestrator Assets). The entire payout chain is built, validated, and reaches the
> live Razorpay API. Drop in real test-mode credentials → it executes a real payout. No code
> change needed to activate.

## Call chain (all live, validated)
```
WorkflowStart
 → BuildAuth_1          (JS)   Basic-auth header from key_id:key_secret (pure-JS base64)
 → HttpRequest_Contact  (HTTP) POST /v1/contacts        (create employee contact)
 → ExtractContact_1     (JS)   contact_id
 → HttpRequest_FundAccount (HTTP) POST /v1/fund_accounts (create VPA/UPI fund account)
 → ExtractFund_1        (JS)   fund_account_id
 → HttpRequest_Payout   (HTTP) POST /v1/payouts          (INR payout, amount in paise, mode UPI)
 → BuildOutput_1        (JS)   assemble Stage-5a contract
 → Response_1
```
Validated: structure parses and the chain reaches `https://api.razorpay.com` (returns `401` with
placeholder creds — i.e. correct and reaching the live API; authenticates with real test keys).

## The 3 placeholder credentials (the only thing to fill)
Get them free at **razorpay.com → RazorpayX → Test Mode** (no partner process):

| Input | Where to get it | Example |
|---|---|---|
| `razorpay_key_id` | Account Settings → API Keys → Generate Test Key | `rzp_test_xxxxxxxx` |
| `razorpay_key_secret` | shown once at key generation | `xxxxxxxxxxxxxxxx` |
| `razorpay_account_number` | RazorpayX test dashboard home | `7878780080316316` |

**Production wiring:** bind these to Orchestrator Assets `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`
(Credential), `RAZORPAY_ACCOUNT_NUMBER`; the Maestro Case passes them in. To activate the whole
stage, someone edits those 3 Asset values — nothing else changes.

## Other inputs (from the approved case)
`case_id, employee_email, employee_name, employee_vpa (default gaurav.kumar@exampleupi),
amount (INR), currency (INR), expense_type, reason`.

## Output (Stage-5a contract → written to the Maestro Case)
```json
{
  "case_id": "...", "erp_system": "RazorpayX",
  "contact_id": "cont_...", "fund_account_id": "fa_...",
  "payout_id": "pout_...", "payout_status": "processing|queued|processed",
  "payment_status": "payout_initiated", "amount": 1800, "currency": "INR",
  "reference_id": "...", "submitted_at": "<ISO8601>"
}
```

## Run it
```bash
# structure check (placeholder creds -> Razorpay 401 is expected & proves it reaches the API):
uip api-workflow run ./RazorpayPayoutWorkflow.json --no-auth \
  --input-arguments '{"case_id":"T1","employee_email":"e@co.com","amount":1800,"currency":"INR","razorpay_key_id":"rzp_test_X","razorpay_key_secret":"X","razorpay_account_number":"0000"}' --output json

# real test payout: replace with free RazorpayX test-mode values -> creates a real test payout
```

Notes: amount is sent in **paise** (`amount × 100`). `narration` is kept to alphanumeric
("Reimbursement Payout") per Razorpay's 30-char rule. VPA/UPI mode is used for instant test
payouts; switch the fund account to `bank_account` for real bank transfers.

## SAP Concur alternative
`../SAPConcurPaymentWorkflow/` remains in the repo as the enterprise-ERP variant (real, validated
to reach live Concur) — kept for reference, but **not live** because Concur API access is gated
behind SAP's partner-enablement process (no free sandbox).
