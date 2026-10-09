# DocFlow v1 — Public Engineering Snapshot

## Status
**PUBLIC / APPLICATION DEVELOPMENT FROZEN.** Archive/read-only status is controlled by GitHub repository settings, not this static report.

This repository is a stable public portfolio snapshot of the DocFlow document extraction prototype and its .NET migration proof. It will remain available at `https://github.com/avysotsky/DocFlow` with unchanged GitHub paths and historical PR/commit links. Proprietary further development is private.

- **Frozen production source commit:** [`602346f90aed9ca9f940ac38ad1847249e3c81df`](https://github.com/avysotsky/DocFlow/tree/602346f90aed9ca9f940ac38ad1847249e3c81df)
- **Public Python Worker CI:** [`37810185511`](https://github.com/avysotsky/DocFlow/actions/runs/37810185511) **SUCCESS**, **120 passed / 13 skipped**. Skipped tests require separately built .NET parity CLI.
- **Public .NET CI:** [`37810185224`](https://github.com/avysotsky/DocFlow/actions/runs/37810185224) **SUCCESS**, 0 build warnings/errors.
- **Public Python ↔ native .NET normalization parity:** [`37809980079`](https://github.com/avysotsky/DocFlow/actions/runs/37809980079) **SUCCESS**, **13 / 13 passed**.
- Logs and artifacts may expire under GitHub Actions retention. This report is frozen historical evidence, not a future-service guarantee.

## Public architecture and engineering evidence
- Python 3.11 structured text extraction pipeline, Pydantic models, JSON Schema validation, generic Groq/OpenAI provider backends (no API keys supplied).
- Versioned, separately deployable Python FastAPI host: `POST /api/v1/extractions`, `GET /health/live`, `GET /health/ready`.
- Bounded request bodies, provider-exception redaction, deterministic synthetic fixtures and tests for invalid requests.
- Native .NET 8 `DocFlow.Normalization` library and CLI (first verified stage of C#-first migration) preserving canonical SHA-256 document/segment IDs and fingerprints on differential fixtures.
- Public unit tests and pull requests for regression and engineering review; synthetic samples only.

## Scope and limitations
- This is not a complete production DocFlow API or enterprise document-processing deployment.
- There is no promise of live LLM provider availability or real-credential E2E in this public snapshot.
- The Python/.NET differential suite proves the listed 13 fixtures, not universal equivalence across every possible document or schema.
- Do not expose unauthenticated internal extraction endpoints to the public internet.
- Source availability does not automatically grant permission to reuse/distribute code; consult applicable licenses.

## Link permanence
This repository is intentionally not renamed, deleted, or made private. GitHub Archive read-only mode can preserve links to the repository, files, pull requests, commits and issues:
- [Repository](https://github.com/avysotsky/DocFlow)
- [Frozen code](https://github.com/avysotsky/DocFlow/tree/602346f90aed9ca9f940ac38ad1847249e3c81df)
- [Historical PRs](https://github.com/avysotsky/DocFlow/pulls)
- [CI evidence](https://github.com/avysotsky/DocFlow/actions/runs/37809980079)

The owner controls archived/read-only status in GitHub repository settings; this static document does not control repository visibility or lifecycle.
