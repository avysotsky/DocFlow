# DocFlow — active handoff for 1.1.1.7 DegradedOCR

Status: **READY FOR MILESTONE CLOSURE**  
Working branch: `DocFlow/v_1.1.1.7_DegradedOCR`  
Started from completed milestone: `DocFlow/v_1.1.1.6_HardCases`

## 1. Starting evidence

Inherited green baseline from 1.1.1.6:

```text
Public Reference Benchmark #74
16/16 public documents passed
91/91 checked business fields matched
68 Python regression tests passed
Automation E2E #95: SUCCESS
Scanned OCR E2E #72: SUCCESS
```

## 2. Purpose

Add measured evidence for real-world OCR degradation that was not represented strongly enough by the previous corpus, then implement only generic recovery justified by the measured failure.

## 3. Admitted real degraded source

Public degraded reproduction:

```text
id: biffa-wirral-invoice-wir00286
supplier: Biffa Waste Services Ltd
customer: Wirral Council
source kind: scanned image / public reproduction
image size: 578 x 825
source image sha256: 1b2ded90e34473463f03655a920ad16fb3501e84983ae74646a078c10a215f23
layout class: degraded grayscale photocopy scan
preprocessing before DocFlow: none
```

The source is publicly traceable but is **not** hosted by Wirral Council. The benchmark metadata explicitly records that provenance distinction.

The original JPEG bytes are preserved by the acquisition script and wrapped losslessly in a one-page image-only PDF only because the current DocFlow ingestion contract is PDF-based.

Ground truth was transcribed before DocFlow processing:

```text
invoice_number: WIR00286
invoice_date: 2013-12-18
currency: GBP
subtotal: 860167.73
vat_rate: 20
vat_amount: 172033.55
total: 1032201.28
```

Expected DocFlow validation status is `incomplete`, not `valid`, because the degraded scan does not provide reliable quantity/unit-price columns for independent line-total/subtotal verification. Correct field extraction is therefore separated from arithmetic-verification completeness.

## 4. Measured baseline before production fix

Public Reference Benchmark #76 measured the existing pipeline against the admitted degraded scan.

```text
documents_total: 17
documents_passed: 16
documents_failed: 1
document_type_correct: 17/17
fields_checked: 98
fields_matched: 94
```

The document type, invoice number, currency and total were already recovered correctly. The measured missing fields were:

```text
invoice_date
subtotal
vat_rate
vat_amount
```

The OCR output itself contained usable evidence:

```text
Invoice Date: ... 18-Dec-13
VATaoe@ 20% ... £172,033.55
TOTAL £1,032,201.28
```

The subtotal label/value area was more severely damaged.

## 5. Production recovery implemented

Added `docflow_worker/degraded_invoice_fallbacks.py` and inserted it into the normal supplier-invoice structured pipeline.

The recovery is deliberately generic and conservative:

1. textual dates are recovered only after an explicit `Invoice Date` label;
2. abbreviated English month dates such as `18-Dec-13` are supported;
3. same-line OCR layout noise between the date label and date is tolerated without crossing a newline;
4. VAT recovery requires an explicit VAT-like label plus percentage;
5. VAT amount prefers an explicit currency-symbol amount;
6. if the subtotal is unreadable, it is derived only when both gross total and VAT amount are confidently known;
7. the fallback does not invent line items and does not promote validation status.

This keeps the existing validation semantics intact: extraction can recover the business values while the validator still reports `incomplete` when item-level arithmetic cannot be independently verified.

## 6. Regression coverage

Added a degraded-OCR regression fixture mirroring the measured failure class:

```text
Invoice No: WIR00286
Invoice Date: <large same-line OCR gap> . 18-Dec-13
corrupted subtotal label
VATaoe@ 20% ... £172,033.55
TOTAL £1,032,201.28
```

The regression asserts all recovered fields and the expected `incomplete` validation status.

## 7. Final public benchmark

Public Reference Benchmark #78 on head `a67dcd9c0f90d0ad93ec9b5dacd528a9403daede` is fully green:

```text
Python regression tests: 69 passed

documents_total: 17
documents_passed: 17
documents_failed: 0
document_pass_rate: 1.0

document_type_correct: 17/17
document_type_accuracy: 1.0

validation_status_checked: 17
validation_status_correct: 17
validation_status_accuracy: 1.0

fields_checked: 98
fields_matched: 98
field_accuracy: 1.0
failure_reason_counts: {}
```

Artifact:

```text
artifact id: 11151732373
sha256: 81435e818fabf8b0ef856c3666bcd94820fa82b27ca36d4f5fe96d81c0b27582
```

## 8. Acceptance criteria status

All DegradedOCR acceptance criteria are met:

- real/public degraded source is traceable;
- degradation is visible and not synthetic;
- ground truth was transcribed independently of DocFlow output;
- weakness was measured before production changes;
- recovery rules are generic to the observed OCR/layout degradation;
- clean digital/OCR regression cases remain green;
- Public Reference Benchmark is green after admission and fix.

## 9. Model fallback decision

ONNX/LLM remains **not justified** by this milestone.

The measured failure was recoverable deterministically from OCR/layout evidence. No semantic failure remains that would justify adding model inference cost or nondeterminism.

## 10. CI discipline and closure

Intermediate implementation/test commits used `[skip ci]`. Public Reference was run only for measured checkpoints and final validation.

Before marking this milestone completed, run milestone-level validation once:

```text
Automation E2E
Scanned OCR E2E
```

Do not rerun Public Reference merely for closure; #78 is already the consolidated green reference baseline.
