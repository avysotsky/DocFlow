# DocFlow — handoff for version 1.1.1.5 RealCorpus

Status: **COMPLETED**  
Working branch: `DocFlow/v_1.1.1.5_RealCorpus`  
Completed on: `2026-09-30`

The original objective of this handoff was to replace synthetic-only confidence with measured evidence from real third-party supplier PDFs before introducing heavier extraction technology.

That objective has now been completed.

## Final evidence

The public-reference workflow attempted 11 public sources and admitted 8 successfully acquired unique PDF documents into the audited benchmark corpus:

```text
digital PDFs: 5
scanned/OCR PDFs: 3
unique PDF contents: 8
audit errors: 0
audit warnings: 0
```

The final benchmark on implementation head `7b10cefda5714d6c6c445e1fcd38382216894491` produced:

```text
documents_total:              8
documents_passed:             8
documents_failed:             0
document_pass_rate:           1.0

document_type_correct:        8
document_type_accuracy:       1.0

validation_status_checked:     8
validation_status_correct:     8
validation_status_accuracy:   1.0

fields_checked:                37
fields_matched:                37
field_accuracy:                1.0

failure_reason_counts:         {}
```

Ground truth for business fields and validation status was recorded independently from DocFlow output.

## Failures discovered and corrected during real-corpus evaluation

The first validation-enabled run exposed two concrete real-document weaknesses:

1. Xero-style invoices without SKU and OCR rows whose long descriptions shift numeric columns.
2. OCR invoice item values with lost decimal separators and a missing quantity column.

The fixes were kept generic:

- invoice SKU is optional;
- shifted numeric tails are parsed from right to left;
- OCR monetary alternatives are constrained by arithmetic;
- a missing quantity is inferred only from an exact integral `line_total / unit_price` relationship;
- OCR item candidates are accepted only when their line totals reconcile exactly to the extracted subtotal.

No supplier id is used to select those parsing rules.

## CI hardening

`Public Reference Benchmark` now preserves diagnostic reports on failure but also enforces the real `real_corpus.py` exit code.

It additionally requires:

```text
validation_status_checked == documents_total
```

so future benchmark cases cannot silently omit validation-status ground truth.

Final CI state:

```text
Python Worker CI:            success
Benchmark Smoke:             success
Automation E2E:              success
Scanned OCR E2E:             success
Public Reference Benchmark:  success
```

Python worker regression suite:

```text
51 passed
1 skipped
```

## Architectural conclusion

The measured failures in this initial public corpus were deterministic/OCR-layout failures and were fixed without a model fallback.

There is therefore no measured reason in this corpus to add ONNX or an external LLM to the production extraction path yet.

The next evidence-driven stage should expand corpus diversity and deliberately target currently weak or untested cases such as locale variation, discounts, multiple taxes, long multi-page tables, noisy scans, rotation/skew and semantic ambiguity.

A future ONNX/LLM experiment should be triggered by measured semantic failures that cannot be handled safely by deterministic/OCR improvements, not by speculation.

## Detailed completion record

See:

```text
docs/HANDOFF_v1.1.1.5_COMPLETED.md
```

It records:

- corpus composition;
- source-acquisition failures;
- independently reviewed validation ground truth;
- measured failure classes;
- parser/OCR fixes;
- final benchmark metrics;
- final CI state;
- architectural decision and remaining coverage gaps.

---

Version `1.1.1.5 RealCorpus`: **COMPLETED**.
