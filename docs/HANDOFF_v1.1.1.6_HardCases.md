# DocFlow — active handoff for version 1.1.1.6 HardCases

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.6_HardCases`  
Started from completed milestone: `DocFlow/v_1.1.1.5_RealCorpus`

## 1. Why this milestone exists

Version 1.1.1.5 established a real public-reference baseline:

```text
8/8 documents passed
8/8 document types correct
8/8 validation statuses correct
37/37 checked business fields correct
5 digital PDFs
3 scanned/OCR PDFs
audit: 0 errors, 0 warnings
```

That is useful regression evidence, but it is not a production-accuracy claim. The corpus is still small and does not cover several document classes that commonly break deterministic/OCR extraction.

Version 1.1.1.6 therefore expands evidence **before** adding ONNX or LLM fallback.

## 2. Objective

Deliberately add real/public supplier documents that stress previously underrepresented difficulty classes, run them through the existing benchmark, classify every failure, and fix only failure classes that are supported by measured evidence.

Target loop:

```text
new hard real document
        ↓
independent ground truth
        ↓
corpus audit
        ↓
current pipeline
        ↓
measured failure
        ↓
classify root cause
        ↓
minimal generic fix
        ↓
regression test
        ↓
rerun complete public corpus
```

## 3. Priority hard-case classes

Priority is based on remaining coverage gaps from 1.1.1.5.

### A. Locale and language variation

Examples:

- decimal comma and thousands separators;
- non-US date formats;
- currency symbols/codes placed differently;
- at least one non-English or bilingual invoice where Tesseract language support is practical.

### B. Tax/total variation

Examples:

- discount before tax;
- shipping/freight line;
- multiple VAT/tax rates;
- zero-rated or tax-exempt item;
- invoice where tax is summarized separately from item rows.

### C. Table/layout variation

Examples:

- long multi-page item table;
- repeated table header on later pages;
- borderless multi-page table;
- item descriptions wrapping over multiple physical lines;
- totals appearing on a final page separate from the first item page.

### D. OCR degradation

Examples:

- visibly noisy scan;
- skew/rotation;
- low contrast;
- scan with separators/decimal punctuation damaged by OCR;
- mobile-camera-like document if a legitimate public source is available.

## 4. Corpus policy

Public third-party PDFs continue to be downloaded at CI runtime and are not committed to the repository.

Every admitted document must have:

- a stable id;
- public source URL;
- SHA-256 pinned by the generated manifest;
- supplier/source metadata;
- source kind;
- layout class;
- language;
- independently transcribed expected business fields;
- independently reviewed expected validation status when applicable.

Do not derive expected values from DocFlow output.

## 5. Benchmark gate

The hardened 1.1.1.5 public-reference workflow is inherited.

A run must fail when:

- the audit fails;
- the benchmark returns non-zero;
- an admitted document fails expected fields/type/status;
- a benchmark report is missing;
- validation-status ground truth is missing for any admitted document.

Reports must still upload on failure for diagnosis.

## 6. Failure classification

For every failing hard case, classify the primary root cause before editing extraction code:

```text
source acquisition/page selection
OCR/text recognition
layout/table reconstruction
document-type detection
field extraction
arithmetic validation
semantic ambiguity
```

A fix must be generic to the failure class. Do not add supplier-id-specific extraction branches merely to turn one benchmark green.

Source-specific logic is acceptable only inside the public corpus acquisition tooling when it is needed to select the intended original page from a larger public pack; it must not leak into the production extraction engine.

## 7. ML/LLM decision rule

Do not add ONNX or an external LLM simply because a new document fails.

Model fallback becomes justified only when measured failures demonstrate semantic ambiguity that cannot be handled safely by:

- better OCR;
- locale-aware deterministic parsing;
- layout/table reconstruction;
- arithmetic reconciliation;
- clearer document-type detection;
- deterministic field-label rules.

If such a failure class appears, first create an isolated benchmark experiment. Do not replace the current deterministic production path immediately.

## 8. Initial engineering target

Expand the admitted public corpus beyond the current 8 unique documents.

A useful target for this milestone is:

```text
15+ admitted unique PDFs
at least 4 newly represented hard-case classes
both digital and OCR documents retained
at least 2 locale/language variants beyond the current dominant English layouts
at least 1 genuinely multi-page item-table case
```

These numbers are engineering coverage targets, not statistical accuracy claims.

## 9. Completion criteria

Version 1.1.1.6 can close when:

1. the corpus has materially broader difficulty coverage than 1.1.1.5;
2. new ground truth is independently recorded;
3. audit has no unresolved errors;
4. every new measured failure has a documented root-cause class;
5. generic deterministic/OCR fixes have regression tests;
6. complete Python Worker CI is green;
7. Benchmark Smoke is green;
8. Automation E2E is green;
9. Scanned OCR E2E is green;
10. Public Reference Benchmark is green or any remaining intentionally unsupported cases are explicitly documented with evidence and architecture consequences;
11. the milestone records whether there is now evidence for an ONNX/LLM experiment.

## 10. Immediate next action

Find and admit the first new public documents that add coverage rather than more examples of the same Xero-style English invoice.

Preferred first additions:

```text
1. decimal-comma / European-format invoice
2. invoice with explicit discount or freight
3. true multi-page item table
4. more degraded scanned invoice
```

Run the complete benchmark immediately after each small batch so failures remain attributable.

---

Current status: **1.1.1.6 HardCases started; baseline is 8/8 green from 1.1.1.5.**
