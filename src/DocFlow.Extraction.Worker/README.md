# DocFlow Extraction Worker

Python worker responsible for document preprocessing and extraction-specific tasks.

Initial responsibilities:

- detect whether a PDF contains extractable text;
- parse text-based PDFs;
- run OCR for scanned/image documents when required;
- call an external LLM extraction service;
- return structured extraction data to the DocFlow backend.
