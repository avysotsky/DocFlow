# DocFlow — handoff v1.1.1.26 StorageKey Deprecation

Status: **ACTIVE**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`  
Base: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`

## Goal

Deprecate the legacy public `StorageKey` metadata field without a breaking API change.

## Confirmed scope

Inventory shows `StorageKey` is exposed only by:

```text
GET /api/documents/{id}
```

The document list, single-upload response, batch response, extraction result and review/export contracts do not expose it.

The supported source-file access path already exists:

```text
GET /api/documents/{id}/file
```

## Selected contract

Preserve the existing `storageKey` JSON property for compatibility.

Add a stable relative source-file link:

```json
"sourceFileUrl": "/api/documents/{id}/file"
```

Mark only `GetDocumentResponse.storageKey` as deprecated in generated OpenAPI. Add a concise description directing clients to `sourceFileUrl` / the `/file` endpoint.

Do not introduce a broad API-versioning framework for this field.

## Validation

Extend existing Automation E2E to verify:

- runtime `GET /api/documents/{id}` still contains `storageKey`;
- response also contains the correct `sourceFileUrl`;
- source-file URL resolves through the existing authenticated file endpoint;
- Swagger/OpenAPI still contains `storageKey` but marks it `deprecated: true`;
- OpenAPI exposes `sourceFileUrl` as the replacement.

Expected CI: .NET CI + Automation E2E only.
