# DocFlow public-reference corpus

This benchmark layer sits between synthetic fixtures and a private customer corpus.

It uses **original third-party supplier PDF layouts** that are already publicly accessible on the web. The repository does not commit or redistribute those PDFs. GitHub Actions downloads them at runtime and, when a supplier document is embedded inside a larger public council/payment/report PDF, extracts only the page containing the supplier document.

## Why this exists

Synthetic PDFs are useful for deterministic regression tests, but they are too close to the assumptions of the extractor. Public-reference documents add independent layouts, currencies, VAT formats, labels and table structures before a confidential real customer corpus is available.

This benchmark is evidence, not a production-accuracy claim.

## Builder

```text
.github/scripts/build_public_reference_corpus.py
```

The builder:

1. downloads public source PDFs;
2. finds the supplier page by a stable text marker;
3. extracts that page without re-layout;
4. computes SHA-256;
5. records source/layout metadata;
6. creates a benchmark manifest with independently transcribed expected values.

Download failures are recorded per source. The build requires at least three successfully recovered supplier documents so one temporarily unavailable website does not make the entire evidence workflow useless.

## Current public sources

The runtime corpus currently targets:

- Asar Ltd — proforma invoice PR-46039;
- Gas-Tech Heating Services (Banbury) Ltd — tax invoice 77057631 embedded in a public parish-council finance pack;
- H.W. Pickrell Ltd — proforma HWI 2403005 embedded in a public town-council agenda pack;
- Trea Kids Danismanlik Anonim Sirketi — proforma invoice 1056 embedded in a municipal attachment;
- HCC Solutions Co Ltd — tax invoice INV-2180 embedded in a public payment PDF;
- Soft-Tech Consultants Ltd — legacy proforma `prof005` embedded in a public JICA report.

These sources cover GBP, EUR, USD and TZS; simple and multi-line invoices; VAT; borderless/table layouts; modern and legacy documents; and documents embedded in larger PDF packs.

## Workflow

```text
.github/workflows/public-reference-benchmark.yml
```

The workflow runs:

```text
public URLs
    ↓
runtime download
    ↓
original supplier page extraction
    ↓
SHA-pinned manifest
    ↓
real_corpus.py
    ↓
corpus inventory + audit + benchmark report
```

The benchmark step is deliberately measurement-oriented: semantic failures do not prevent report publication. Source-build and audit failures remain real workflow failures.

The workflow uploads only JSON reports/manifest metadata, not the downloaded third-party PDFs.

## Relationship to private RealCorpus

This public-reference layer does **not** replace the private RealCorpus completion criterion. Version `1.1.1.5_RealCorpus` still requires representative third-party documents supplied/approved for the actual product context before production-quality architectural conclusions are made.
