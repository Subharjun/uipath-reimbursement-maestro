# Stage 1/2 — Email Intake & Receipt Extraction (IDP)

The front of the pipeline: pull the reimbursement email + receipt, then extract structured
fields with **UiPath Document Understanding**. Both are **cross-platform (Portable) RPA
processes** that run **serverless** on the tenant (the hackathon tenant has 0 Robot Units, so
Windows jobs can't run — these were converted to Portable to run as Platform-Unit serverless jobs).

| Project | Stage | What it does |
|---------|-------|--------------|
| [`ReimbursementIntakeBot/`](ReimbursementIntakeBot/) | 1 — Intake | Reads Gmail (Subject contains "Reimbursement"), downloads the receipt attachment, and uploads it to the `Receipt` storage bucket. Outputs `out_CaseId`, `out_emailBody`, `out_attachmentName`. |
| [`ReceiptExtractor/`](ReceiptExtractor/) | 2 — IDP | Downloads the receipt from the `Receipt` bucket and runs **Document Understanding** (Receipts model) to emit `out_JSON` = `{ case_id, emailbody, expense{vendor, date, amount, currency}, document{...} }`. |

## How they connect

```
Gmail inbox ──▶ ReimbursementIntakeBot ──▶ [Receipt bucket] ──▶ ReceiptExtractor ──▶ out_JSON ──▶ Stage 3 (Classify)
```

Run **IntakeBot first** — it populates the bucket; ReceiptExtractor reads from it. The bucket
persists the blob (ReceiptExtractor only deletes its local temp copy).

## Notes on source

- **`ReimbursementIntakeBot/`** is the full editable cross-platform source, including `Main.xaml`.
- **`ReceiptExtractor/`** here is the **package metadata** (project / bindings / entry-points)
  extracted from the deployed tenant package. Its `Main.xaml` and the Document Understanding
  bundle (`ReimbursementDUReceiptsV1`) are generated at author time and ship inside the deployed
  package on the tenant rather than as loose source — they are not reproduced here.

> These two stages were authored by the team's IDP/intake owner; they're included so the repo
> tells the **complete end-to-end story** that the Maestro Case orchestrates.
