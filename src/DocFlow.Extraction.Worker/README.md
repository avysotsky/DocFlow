# DocFlow Extraction Worker

Python worker responsible for document preprocessing and extraction-specific tasks.

## Current vertical slice

The worker can now:

1. resolve a PDF by the same local `StorageKey` that the .NET API stores in PostgreSQL;
2. prevent storage-key path traversal;
3. extract the embedded text layer with PyMuPDF;
4. report page count, pages containing text, empty pages and whether OCR is required;
5. optionally save extracted text as UTF-8.

OCR itself is the next step. At this stage `needsOcr=true` means that the PDF has pages but none contains extractable embedded text.

## Provider-agnostic structured extraction

`docflow_worker.engines.StructuredExtractionEngine` is the boundary for the later structured extraction stage. The pipeline will be able to plug in implementations such as:

- `OnnxExtractionEngine` for a local model;
- `LlmExtractionEngine` for an external LLM API;
- a hybrid engine that tries local extraction first and falls back to an LLM when confidence is insufficient.

The rest of DocFlow should depend on the abstraction and on `StructuredExtractionResult`, not on a specific AI provider.

## Local development

From `src/DocFlow.Extraction.Worker`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The .NET API currently stores local files under `src/DocFlow.Api/storage` unless `FileStorage:RootPath` is overridden.

Take a `StorageKey` from the `Documents` table and run, for example:

```powershell
python main.py `
  --storage-root ..\DocFlow.Api\storage `
  --storage-key "2026/09/<stored-file>.pdf" `
  --output-text extracted.txt
```

The command prints a JSON summary such as:

```json
{
  "storageKey": "2026/09/example.pdf",
  "pageCount": 2,
  "pagesWithText": 2,
  "emptyPageNumbers": [],
  "needsOcr": false,
  "textLength": 4281,
  "outputText": "extracted.txt"
}
```
