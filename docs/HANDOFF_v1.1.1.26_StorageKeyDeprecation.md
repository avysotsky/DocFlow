# DocFlow — handoff v1.1.1.26 StorageKey Deprecation

Status: **COMPLETED**  
Repository: `avysotsky/DocFlow`  
Branch: `DocFlow/v_1.1.1.26_StorageKeyDeprecation`  
Base: `DocFlow/v_1.1.1.25_BatchResumeFaultInjection`

## Goal

Deprecate the legacy public `StorageKey` metadata field without breaking existing clients.

## Implementation

Primary implementation commit:

```text
dc9c71d7fb02671a19c8821f85f1bdadd997fe01
Deprecate StorageKey in document metadata contract
```

Test-harness fix:

```text
19b3141a8cc8a61872b227c3c8453c883f88a630
Fix binary source-file compatibility assertion
```

The only API response that exposed `StorageKey` was:

```text
GET /api/documents/{id}
```

That response still contains `storageKey` for compatibility and now also contains:

```json
"sourceFileUrl": "/api/documents/{id}/file"
```

The value is a stable relative API path, not a filesystem/storage locator.

## OpenAPI contract

A narrow `DocumentContractSchemaFilter` marks only:

```text
GetDocumentResponse.storageKey
```

as:

```text
deprecated: true
```

The description directs clients to `sourceFileUrl` / `GET /api/documents/{id}/file`.

No API-versioning framework or new package was introduced.

## Validation

Authoritative validation:

```text
.NET CI #40 -> success (run 36989497543)
Automation E2E #121 -> success (run 36989710997)
```

Automation E2E verifies:

- `storageKey` remains present at runtime;
- `sourceFileUrl` is present and correct;
- the returned source-file URL resolves through the existing authenticated PDF endpoint;
- Swagger/OpenAPI keeps `storageKey` but marks it deprecated;
- Swagger/OpenAPI exposes `sourceFileUrl` as a string replacement;
- all existing intake, batch-idempotency, review, restart and retention regression still passes.

## Diagnostic run

```text
Automation E2E #120 -> failure
```

The failure was in the new test helper: it attempted to UTF-8-decode binary PDF bytes through the JSON/text parser and raised `UnicodeDecodeError`.

The product endpoint itself returned the PDF correctly. The helper was changed to a status-only request for the binary `/file` endpoint; no C# production code changed after the already-green .NET CI #40.

## Compatibility boundary

Do not silently remove `storageKey` from the current response. Existing clients may still depend on it.

New clients should depend on:

```text
sourceFileUrl
GET /api/documents/{id}/file
```

A future removal of `storageKey` should be done only with an explicit breaking/versioned API decision.
