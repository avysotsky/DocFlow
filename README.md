> **Public DocFlow v1 — engineering portfolio snapshot (October 2026).** This repository's application code is frozen at [commit `602346f`](https://github.com/avysotsky/DocFlow/tree/602346f90aed9ca9f940ac38ad1847249e3c81df). Further development is private. This repository will remain **public at its original GitHub URL** and become read-only once GitHub Archive is enabled. See [Snapshot evidence](ENGINEERING_SNAPSHOT_V1.md).\n\n# DocFlow

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

This public v1 is a historical engineering portfolio snapshot. Active production development is private; no separate showcase repository is required.
