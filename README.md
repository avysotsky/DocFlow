# DocFlow

DocFlow is a private commercial project for automated processing of business documents such as supplier quotations and invoices.

The system converts PDF/scanned documents into validated structured data that can be stored in PostgreSQL and exported to Excel/CSV or passed to external systems.

## Initial MVP

1. Upload a PDF.
2. Detect text PDF vs scan.
3. Extract text / OCR when required.
4. Produce structured JSON via an external LLM.
5. Run deterministic validation.
6. Persist metadata and extraction results in PostgreSQL.
7. Export structured data to Excel/CSV.

## Planned solution structure

```text
DocFlow.sln
src/
  DocFlow.Api/
  DocFlow.Application/
  DocFlow.Domain/
  DocFlow.Infrastructure/
  DocFlow.Extraction.Worker/
tests/
  DocFlow.UnitTests/
  DocFlow.IntegrationTests/
```

Production code remains private. A separate public portfolio repository may be created later.
