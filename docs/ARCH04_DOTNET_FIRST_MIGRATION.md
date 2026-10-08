# ARCH-04 — .NET-first DocFlow migration and parity gate

## Decision
Prefer C#/.NET for DocFlow API, deterministic normalization, schemas, orchestration and provider integration **when semantics and quality are proven equivalent**. Keep Python for components with measurable technical advantage (specialized OCR / document ML or mature native tooling). Do not force embedded Python into a .NET monolith merely because it is technically possible.

## First delivered migration slice
- `src/DocFlow.Normalization` — framework-only .NET 8 deterministic text normalizer and canonical SHA-256 document/segment/fingerprint identities.
- `tools/DocFlow.Normalization.Cli` — standalone .NET CLI accepting raw JSON on stdin, producing normalized JSON on stdout; sanitized failures on stderr.
- `src/DocFlow.Extraction.Worker/tests/test_dotnet_normalization_parity.py` — 13 differential fixtures: 7 normalized-success variants (base, reversed segments, CRLF, Unicode, optional timestamps, timezone equivalence, source identity), 6 rejected input variants.
- `.github/workflows/dotnet-normalization-parity.yml` — builds native .NET 8 implementation and runs differential tests against original Python reference.
- Existing Python normalization, Groq/OpenAI backends and FastAPI host remain intact. No production cutover.

## Contract and parity
Python `docflow_worker.text_document_normalizer.TextDocumentNormalizer` remains authoritative until more extensive golden/negative fixtures confirm compatibility. The same SHA-256 hashes, normalized object members, UTC timestamps, canonical JSON and ordering are compared in CI. Difference in any identity or fingerprint is a compatibility failure.

The initial .NET port is a foundation, **not** a completed DocFlow.Api rewrite. Before using its normalized output in provider-backed workflows, expand parity with edge cases (control-character escaping, non-BMP Unicode, fractional seconds, invalid JSON member types, duplicate/unknown fields, timestamp parsing, long inputs), fuzz/property testing and full schema validation. Bound request sizes and depth at the HTTP layer.

## Updated target topology
- Keep repositories `avysotsky/DocFlow` and `avysotsky/TradeOps` independent.
- Standalone `DocFlow.Api` should eventually be a thin ASP.NET Core host atop the same native .NET application layer that a modular monolith calls directly.
- TradeOps retains its owned `IDocFlowExtractionPort`; ARCH-03 HTTP adapter continues to work and must not be removed until equivalent .NET-host and monolith adapters pass end-to-end parity.
- Python adapter is opt-in for components that outperform the .NET implementation; Python.NET embedding remains a validated experiment, **not** the default deployment architecture.
- No broker/account/order side effects are permitted within DocFlow.

## Quality gates for subsequent work
1. Extend .NET normalization to full strict Python contract and prove byte/semantic parity across comprehensive fixtures.
2. Implement .NET schema-driven application extraction behind transport-neutral abstractions; use established .NET HTTP clients to call LLM providers.
3. Implement secure .NET DocFlow.Api; preserve Python endpoint parity and provider contracts while migrating traffic by opt-in routing.
4. Implement TradeOps in-process adapter to native .NET DocFlow application only once versioned packaging and DI integration are demonstrable.
5. Complete ARCH-05 comparison of Python HTTP, .NET HTTP and native .NET in-process execution using synthetic deterministic backend.
6. Retain Python only when benchmarking or missing .NET capabilities justify it; record ADR for exceptions.

No cross-repository shared mutable source, monorepo, external-key test dependencies or public unauthenticated service deployment.
