# DocFlow — active handoff for 1.1.1.7 DegradedOCR

Status: **ACTIVE**  
Working branch: `DocFlow/v_1.1.1.7_DegradedOCR`  
Started from completed milestone: `DocFlow/v_1.1.1.6_HardCases`

## 1. Starting evidence

Inherited green baseline from 1.1.1.6:

```text
Public Reference Benchmark #74
16/16 public documents passed
91/91 checked business fields matched
68 Python regression tests passed
Automation E2E #95: SUCCESS
Scanned OCR E2E #72: SUCCESS
```

Do not weaken or reinterpret this baseline while working on degraded OCR.

## 2. Purpose

Add measured evidence for real-world OCR degradation that is not represented strongly enough by the current corpus.

Target degradation classes:

```text
skew / rotation
low contrast / faded print
scan noise / compression artifacts
blur
broken punctuation around money values
mobile-camera-like perspective or illumination
```

The preferred source is an independently verifiable real/public supplier invoice. A clean scan is not enough merely because it is image-only.

## 3. Engineering loop

```text
find legitimate public source
-> visually verify degradation
-> independently transcribe ground truth
-> record source URL/hash/metadata
-> run current pipeline without production changes
-> inspect native text / OCR text / structured result
-> classify the measured failure
-> implement the smallest generic preprocessing/OCR/layout change
-> regression tests
-> one consolidated public benchmark
```

Do not create a production preprocessing stage before a measured source shows why it is required.

## 4. Candidate preprocessing techniques

These are investigation candidates, not pre-approved production changes:

- orientation detection / 90-degree rotation correction;
- deskew for small-angle rotation;
- grayscale normalization;
- contrast stretching;
- adaptive thresholding;
- denoise / morphology for compression speckle;
- render-DPI tuning;
- selective image-region OCR;
- conservative OCR re-run only when first-pass text quality is poor.

Every candidate must be evaluated for regression risk and runtime cost.

## 5. Acceptance criteria

A degraded-OCR case is useful only when:

1. the original public document is legitimate and traceable;
2. degradation is visible in the source, not synthetically claimed as real-world evidence;
3. business ground truth is transcribed independently of DocFlow output;
4. the current pipeline's failure or weakness is measured before code changes;
5. any production fix is generic to the degradation class;
6. clean digital/OCR regression cases stay green;
7. Public Reference Benchmark remains green after admission/fix.

If no suitable real/public source can be found, document that result explicitly. A synthetic degradation fixture may be used for engineering experiments, but it must be labelled synthetic and must not be counted as real-corpus evidence.

## 6. CI discipline

Do not trigger GitHub Actions during source search or each experiment.

Use `[skip ci]` for intermediate implementation/test commits and run one consolidated validation after a coherent block.

## 7. Model fallback rule

ONNX/LLM remains deferred.

Visual degradation should first be addressed, if justified, with image/OCR preprocessing. Only a measured semantic extraction failure that remains after adequate OCR/layout recovery can justify evaluating a model fallback.

## 8. Immediate next action

Find and visually inspect candidate public invoice PDFs, prioritizing council/public-body payment packs because they often contain scans of original paper invoices and provide independent payment schedules useful for ground-truth cross-checking.
