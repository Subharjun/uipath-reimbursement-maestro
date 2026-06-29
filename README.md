# Reimbursement Process Automation — UiPath Maestro

An end-to-end, **agentic reimbursement pipeline** built on UiPath Maestro. An employee emails a
receipt; the system extracts it, classifies the expense, scores risk, runs a policy check,
routes it to a **human approver**, disburses the payout, and emails the claimant — every step
auditable and orchestrated by a Maestro **Case**.

Built for **UiPath AgentHack 2026 — Track 1 (Reimbursement Process Automation)**.

---

## 🧭 What it does

```
 ┌────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
 │ 1. Intake  │──▶│ 2. Receipt   │──▶│ 3. Classify  │──▶│ 4. Policy    │
 │  (email →  │   │   Extract    │   │  + risk score│   │   check      │
 │   bucket)  │   │  (Doc U.)    │   │  (AI Agent)  │   │ (deterministic)│
 └────────────┘   └──────────────┘   └──────────────┘   └──────┬───────┘
                                                               │
                          ┌────────────────────────────────────┘
                          ▼
                  ┌─────────────────┐   approve   ┌──────────────┐   ┌───────────────┐
                  │ 5. Human review │────────────▶│ 6. Payout    │──▶│ 7. Notify     │
                  │ (Action Center  │             │  (Stripe)    │   │ (Gmail email) │
                  │  approval app)  │             └──────────────┘   └───────────────┘
                  └───────┬─────────┘
                          │ reject
                          ▼
                  ┌───────────────────┐
                  │ 7b. Reject Notify │  (emails claimant the rejection reason)
                  └───────────────────┘
```

All stages are wired together by a **UiPath Maestro Case** (`MaestroCase/`) and run on the
hackathon cloud tenant as **serverless** jobs.

---

## 📂 Repository layout

| Path | Stage | What it is |
|------|-------|------------|
| [`IntakeAndExtraction/`](IntakeAndExtraction/) | 1/2 — Intake & IDP | Cross-platform RPA bots: **email intake** (Gmail → receipt → bucket) and **receipt extraction** (Document Understanding → structured `out_JSON`). Run serverless. |
| [`ReimbursementClassificationAgent/`](ReimbursementClassificationAgent/) | 3 — Classify | Coded **LangGraph** agent (gpt-4o via UiPath LLM Gateway + deterministic fallback). Classifies expense type, scores risk, detects duplicates. |
| [`PolicyRuleCheckWorkflow/`](PolicyRuleCheckWorkflow/) | 4 — Policy | Deterministic **API workflow** that checks the claim against the policy DB and decides proceed / escalate. |
| [`classification-approval-app/`](classification-approval-app/) | 5 — HITL | **Coded Action App** (React/Vite) — the human-in-the-loop approval gate shown in Action Center (Approve / Reject + reviewer notes). |
| [`StripePayoutWorkflow/`](StripePayoutWorkflow/) | 6 — Payout | **API workflow** that disburses via **Stripe** (test mode): Customer → confirmed PaymentIntent → `succeeded`. |
| [`NotificationAgent/`](NotificationAgent/) | 7 — Notify | Coded **LangGraph** agent: writes a warm note (LLM) and sends a polished **HTML email** via the Gmail connector on payout success. |
| [`RejectionNotificationAgent/`](RejectionNotificationAgent/) | 7b — Reject | Sibling agent that emails the claimant a "not approved" message **including the rejection reason** when the reviewer rejects. |
| [`ReimbursementApiSolution/`](ReimbursementApiSolution/) | — | The **deployable solution** (`.uipx`) bundling Classify + Policy + Stripe + Notify + RejectNotify into one package. |
| [`MaestroCase/`](MaestroCase/) | orchestration | The downloaded **Maestro Case** that wires all stages end-to-end (`_unpacked/content/caseplan.json` is the readable source). |
| [`data/`](data/) | — | `mock_policy.json` (policy DB) + `case_schema.json`. |

> The Case invokes the Stage 1/2 bots by process name; their source is under
> [`IntakeAndExtraction/`](IntakeAndExtraction/). The classifier (Stage 3) consumes the
> extractor's `out_JSON`.

---

## 🛠️ Tech stack

- **UiPath Maestro** (Case Management orchestration)
- **UiPath AI Agents / Agent Builder** — coded LangGraph agents in Python
- **UiPath Action Center** — human-in-the-loop approval
- **UiPath Document Understanding** — receipt extraction
- **UiPath Orchestrator + Integration Service** — serverless runs, Gmail connector
- **UiPath LLM Gateway** — gpt-4o for classification & note-writing
- **Python · LangGraph · React/Vite · Stripe API · Gmail API**

---

## 🚀 Running it yourself

> You need your own **UiPath tenant** (with Orchestrator / Action Center / Integration Service),
> a **Gmail Integration Service connection**, and a free **Stripe test-mode key** (`sk_test_…`).
> The connection IDs / folder keys committed here point at the original hackathon tenant — replace
> them with your own.

### 0. Prerequisites
```bash
npm install -g @uipath/cli          # UiPath CLI (uip)
uip login --authority "https://cloud.uipath.com/identity_" \
          --organization "<your-org>" --tenant "<your-tenant>"
```

### 1. Intake & extraction bots (Stage 1/2 — RPA)
These are cross-platform (Portable) RPA processes that run **serverless** on Orchestrator.
They need a **Gmail connection** (intake reads the inbox) and a **storage bucket** named
`Receipt` (intake uploads, extraction downloads), plus a **Document Understanding** Receipts
model for extraction.
```bash
# pack & upload each project, then create + start a serverless process
uip rpa pack IntakeAndExtraction/ReimbursementIntakeBot ./build
uip or packages upload ./build/<packed>.nupkg
uip or processes create --name ReimbursementIntakeBot_XP --package-key <Id> --package-version <v> --folder-key <folder>
uip or jobs start <process-key> --folder-key <folder> --runtime-type Serverless --wait-for-completion
```
> Run **IntakeBot first** (it fills the `Receipt` bucket), then ReceiptExtractor. ReceiptExtractor's
> `Main.xaml` + DU bundle live inside the deployed tenant package — see
> [`IntakeAndExtraction/README.md`](IntakeAndExtraction/README.md).

### 2. Coded agents (Classify / Notify / RejectNotify)
```bash
cd ReimbursementClassificationAgent
uip codedagent setup --force        # recreates the .venv (not committed)
source .venv/bin/activate
uip codedagent run agent --file <input.json>     # local run
```
Stage 6 needs a Gmail connection — supply it via `__uipath/uipath.json` resourceOverwrites
(`connectionId` + `folderKey`) or env `REIMBURSEMENT_GMAIL_CONNECTION_ID`.

### 3. API workflows (Policy / Stripe)
```bash
cd StripePayoutWorkflow
uip api-workflow run ./StripePayoutWorkflow.json --no-auth \
  --input-arguments '{ "...case fields...", "stripe_secret_key": "sk_test_…" }'
```

### 4. Approval Action App
```bash
cd classification-approval-app
npm install
npm run build
uip codedapp pack dist -n classification-approval-app --version 0.0.3
uip codedapp publish -t Action --name classification-approval-app --version 0.0.3
```

### 5. The whole solution
```bash
uip solution pack ReimbursementApiSolution ./build --version <ver>
uip solution publish ./build/ReimbursementApiSolution_<ver>.zip --tenant <tenant>
uip solution deploy run --package-name ReimbursementApiSolution --package-version <ver> \
  --name ReimbursementFullSolution --folder-name ReimbursementFullSolution --parent-folder-path Shared
```

### 6. The Maestro Case
Open `MaestroCase/_unpacked/content/caseplan.json` in Studio Web (the readable Case source),
rebind the process references to **your own** deployed packages, set your Stripe key
(`sk_test_…`), then publish the Case. The original packed `.nupkg` is intentionally **not**
committed — it embedded a Stripe test key, so rebuild it from this source against your tenant.

---

## 🔌 Integration contract (Stage 3 → Stage 4)

The classifier emits a drop-in payload for the policy stage:

```json
{
  "case_id": "...", "expense_type": "...", "amount": 0.0, "currency": "USD",
  "vendor": "...", "date": "...", "reason": "...", "document_attached": true,
  "risk_score": "Low", "duplicate_detected": false, "business_purpose_valid": true
}
```
Plus claimant extras (`employee_name`, `employee_email`) used by the notifiers.
The field is `expense_type` (not `expense_type_confirmed`); the policy stage routes to
`proceed_to_payment` or `escalate_to_human_review`.

---

## ✅ What's validated

- **Stage 1/2** — email intake + receipt extraction (Document Understanding) ran Successful on serverless; the intake → bucket → extraction → `out_JSON` chain executes end-to-end.
- **Stage 3** — smoke + edge eval sets pass; live cloud job Successful.
- **Stage 4** — routing scenarios correct.
- **Stage 5** — human approval gate renders risk/confidence and captures Approve/Reject + reviewer notes in Action Center.
- **Stage 6** — **real Stripe test-mode payout** (PaymentIntent `succeeded`).
- **Stage 7 / 7b** — real Gmail sends (HTML email, message id returned) on both approve and reject paths; evals 2/2.
- **Whole solution** — deployed + active on the tenant; serverless jobs Successful.

---

## 🔐 A note on secrets

No credentials are committed. Real keys live in `.env` / Orchestrator Assets (both gitignored):
`UIPATH_ACCESS_TOKEN`, `stripe_secret_key`, etc. The connection IDs visible in source are tenant
identifiers, not credentials — they're inert without auth to that tenant. Swap in your own.

---

## 👥 Team — AgentHack 2026, Track 1

Reimbursement Process Automation, built by a 4-person team (Case management, Document
Understanding/intake, Agents & APIs, demo). This repo contains the **Agents, API workflows,
approval app, policy DB, and the orchestrating Maestro Case**.
