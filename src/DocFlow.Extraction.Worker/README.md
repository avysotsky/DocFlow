# DocFlow Extraction Worker

Python worker responsible for document preprocessing and extraction-specific tasks.

## Current vertical slice

The worker can now:

1. resolve a PDF by the same local `StorageKey` that the .NET API stores in PostgreSQL;
2. prevent storage-key path traversal;
3. inspect digital PDFs with PyMuPDF;
4. extract page text, text blocks and individual words with bounding-box coordinates;
5. detect line-based tables and extract their rows/cells;
6. report page count, pages containing text, empty pages and whether OCR is required;
7. optionally save both plain UTF-8 text and the full layout-aware `DocumentContent` JSON.

OCR itself is a later stage. At this stage `needsOcr=true` means that the PDF has pages but none contains extractable embedded text.

## DocumentContent

`DocumentContent` is the provider-neutral representation passed to semantic extraction engines. It preserves information that a plain string would lose:

- page number and dimensions;
- page text;
- text blocks and their bounding boxes;
- words and their bounding boxes plus block/line/word indexes;
- detected tables, their bounding boxes and cell values.

Plain text is still available as a computed convenience field, but it is no longer the primary representation of a document.

## Provider-agnostic structured extraction

`docflow_worker.engines.StructuredExtractionEngine` accepts `DocumentContent` and returns `StructuredExtractionResult`.

The pipeline can later plug in implementations such as:

- deterministic supplier/document parsers;
- `OnnxExtractionEngine` for a local model;
- `LlmExtractionEngine` for an external LLM API;
- a hybrid router that tries deterministic/local extraction first and falls back to an LLM when confidence is insufficient.

The rest of DocFlow should depend on these abstractions rather than on a specific AI provider.

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
  --output-text extracted.txt `
  --output-json extracted-layout.json
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
  "wordCount": 642,
  "blockCount": 51,
  "tableCount": 2,
  "outputText": "extracted.txt",
  "outputJson": "extracted-layout.json"
}
```
