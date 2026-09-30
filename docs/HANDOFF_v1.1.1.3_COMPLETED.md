# DocFlow — completed handoff for version 1.1.1.3 Robustness

Date completed: 2026-09-30  
Implementation branch: `DocFlow/v_1.1.1.3_Robustness`

## 1. Milestone result

Version 1.1.1.3 extends the automatic processing pipeline from one controlled bordered supplier quotation format to several harder input classes while preserving the .NET-owned orchestration and persistence architecture introduced in 1.1.1.2.

Verified production path:

```text
POST /api/documents
        ↓
file storage + Document = Uploaded
        ↓
in-process Channel queue
        ↓
BackgroundService + scoped processing service
        ↓
Python worker
        ↓
conditional native-text extraction / OCR
        ↓
automatic supplier document type detection
        ↓
deterministic quotation or invoice engine
        ↓
deterministic arithmetic validation
        ↓
.NET ExtractionResult persistence
        ↓
Processed / NeedsReview / Failed
```

## 2. Borderless supplier quotation support

The generic PDF layer still uses line-based table detection for explicit vector tables. Supplier quotation extraction now has a deterministic fallback for digital PDFs whose columns are visually aligned but have no drawn borders.

Implementation:

```text
src/DocFlow.Extraction.Worker/docflow_worker/engines/deterministic_supplier_quotation.py
```

The fallback:

- keeps explicit `TableContent` as the preferred source;
- reconstructs layout rows from text separated by stable multi-space column gaps when no line table is available;
- extracts metadata from those reconstructed rows;
- reconstructs an item-table shape and reuses the existing `_extract_items()` logic;
- does not duplicate arithmetic validation.

A real generated PDF with no table borders is verified by Automation E2E and finishes `Processed / Valid / confidence 1.0` with the same five line items and totals as the bordered baseline.

## 3. Supplier invoice support

New semantic model:

```text
src/DocFlow.Extraction.Worker/docflow_worker/supplier_invoice_models.py
```

New deterministic engine:

```text
src/DocFlow.Extraction.Worker/docflow_worker/engines/deterministic_supplier_invoice.py
```

Engine identity:

```text
engine = deterministic_supplier_invoice_v1
document_type = supplier_invoice
```

Invoice fields include:

- supplier name;
- invoice number;
- invoice date;
- due date;
- currency;
- customer reference;
- purchase-order number;
- line items;
- subtotal;
- VAT rate and amount;
- total;
- payment terms;
- notes.

New validator:

```text
src/DocFlow.Extraction.Worker/docflow_worker/validators/supplier_invoice.py
```

Invoices reuse the proven supplier-document arithmetic invariants:

```text
line_total = quantity × unit_price
subtotal = sum(line_totals)
vat_amount = subtotal × vat_rate
total = subtotal + vat_amount
```

Automation E2E verifies a generated supplier invoice end-to-end with:

```text
Invoice No: INV-2026-091
Invoice Date: 2026-09-30
Due Date: 2026-10-30
Currency: EUR
PO No: PO-78421
Subtotal: 1457.00
VAT 20%: 291.40
Total: 1748.40
Items: 5
Status: Processed
Validation: Valid
Confidence: 1.0
```

## 4. Automatic supported document-type detection

New detector:

```text
src/DocFlow.Extraction.Worker/docflow_worker/document_type_detector.py
```

Supported types:

```text
supplier_quotation
supplier_invoice
```

The worker CLI supports:

```text
--document-type auto
```

The .NET `PythonDocumentExtractionRunner` now calls the Python worker with `auto` instead of hard-coding supplier quotation.

The detector is deterministic and uses quotation/invoice markers such as document number/date, validity date and due date. Unknown/ambiguous documents fail explicitly instead of silently being assigned an unsupported type.

## 5. OCR for scanned PDFs

`PdfContentExtractor` now supports conditional OCR through PyMuPDF's Tesseract integration.

Behavior:

```text
page has native text
    → existing digital extraction path

page has no native text and OCR enabled
    → page.get_textpage_ocr(...)
    → extract OCR text, words and blocks
```

OCR is enabled by the production CLI and can be controlled with:

```text
--disable-ocr
--ocr-language eng
--ocr-dpi 300
--tessdata <path>
```

`PageContent` / `DocumentContent` expose whether OCR was applied and the OCR page numbers.

A dedicated GitHub Actions workflow:

```text
.github/workflows/scanned-ocr-e2e.yml
```

installs Tesseract, creates an image-only quotation PDF, verifies that it contains zero native text before processing, uploads it through the API, and verifies the full background pipeline through PostgreSQL.

The scanned quotation E2E passes with:

```text
Status: Processed
Document type: supplier_quotation
Validation: Valid
Confidence: 1.0
Items: 5
Subtotal: 1457.00
VAT: 291.40
Total: 1748.40
```

## 6. Supplier-format variability improvements

The item-table recognition gate now uses the same aliases already understood by `_extract_items()`.

Examples now recognized include:

```text
SKU / Description / Qty / Unit / Unit Price / Line Total
Part No. / Item Description / Quantity / UOM / Price / Amount
```

Unit coverage also verifies:

- `Quote Number` vs `Quotation No.`;
- `Quote Date` vs `Quotation Date`;
- `Valid Through` vs `Valid Until`;
- date format `30.09.2026`;
- numeric text such as `1,234.50`.

## 7. CI / E2E state

CI workflows now run on version branches matching:

```text
DocFlow/v_*
```

Verified on the final implementation head before documentation:

- Python Worker CI: success;
- Automation E2E: success;
- Scanned OCR E2E: success.

Automation E2E continues to cover:

1. valid supplier quotation;
2. repeated enqueue/idempotency;
3. arithmetic mismatch → `NeedsReview`;
4. technical Python failure → `Failed`;
5. borderless supplier quotation;
6. supplier invoice with automatic type detection.

Scanned OCR E2E separately covers an image-only supplier quotation with Tesseract installed.

## 8. Architectural decisions retained

- .NET still owns orchestration and PostgreSQL persistence.
- Python still returns structured JSON and does not write to PostgreSQL.
- OCR is conditional; digital PDFs do not pay OCR cost.
- Document-type detection is deterministic for the currently supported types.
- Borderless fallback is localized to supplier semantic extraction instead of making the generic PDF table detector guess arbitrary tables.
- RabbitMQ/Kafka/Redis remain deferred.
- ONNX/LLM fallback is not added yet because deterministic extraction should first be measured against real supplier documents.

## 9. Important limitation: real-world benchmark not completed

Version 1.1.1.3 verifies controlled synthetic PDFs representing several layout classes. It does **not** establish production accuracy on third-party supplier documents.

Not yet measured systematically:

- many real suppliers with different templates;
- poor scans, rotation, blur, compression artifacts and handwriting;
- multilingual documents;
- unusual VAT/tax structures;
- discounts, freight, surcharges and multiple totals;
- multi-page item tables;
- merged cells and highly irregular layouts;
- ambiguous quotation/invoice labels;
- OCR accuracy on noisy real scans.

Therefore there is not yet evidence to justify a specific ONNX or external-LLM fallback architecture.

## 10. Recommended next milestone

The next version should be a real-world benchmarking/corpus stage rather than immediately adding ML/LLM extraction.

Recommended branch:

```text
DocFlow/v_1.1.1.4_Benchmarking
```

Goals:

1. define a corpus/manifest format without committing private supplier PDFs;
2. run the current deterministic+OCR pipeline over a directory of documents;
3. compare extracted fields with expected JSON;
4. report field accuracy, document pass rate and validation outcomes;
5. classify failure modes by layout/OCR/document type;
6. only after measured failures decide whether rules, ONNX or LLM fallback is justified.

---

Version 1.1.1.3 closes the controlled robustness stage: bordered quotation, borderless quotation, supplier invoice, automatic quotation/invoice detection, scanned quotation OCR, failure routing and supplier header aliases are all covered. The next evidence gap is real-world accuracy, not basic orchestration.