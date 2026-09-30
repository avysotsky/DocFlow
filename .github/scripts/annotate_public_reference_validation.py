#!/usr/bin/env python3
"""Add independently reviewed validation-status ground truth to public references.

The public-reference builder records independently transcribed business fields. This
small post-processing step adds the expected DocFlow validation status only for source
documents whose arithmetic structure has also been reviewed independently from the
benchmark output.

Documents not listed here remain intentionally unchecked for validation status instead
of silently copying the pipeline result into ground truth.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


# These expectations are based on the source document structure, not on DocFlow output.
#
# `valid` means the source visibly contains enough item/discount/tax arithmetic to
# establish its totals independently, even if the current DocFlow validator does not
# yet model every operation. `incomplete` means required arithmetic inputs are genuinely
# absent or not explicit enough in the source to be independent ground truth.
EXPECTED_VALIDATION_STATUS: dict[str, str] = {
    # VAT amount is present, but the VAT rate is not explicitly stated.
    "asar-proforma-pr-46039": "incomplete",

    # Vehicle/side-step amounts and VAT/total are present, but there is no explicit
    # quantity + unit-price item structure required for all validator checks.
    "hw-pickrell-proforma-hwi-2403005": "incomplete",

    # The source tables contain enough item pricing/tax arithmetic to verify totals.
    "trea-kids-proforma-1056": "valid",
    "hcc-solutions-invoice-inv-2180": "valid",
    "hugofox-invoice-inv-23226": "valid",
    "rainfords-farm-invoice-inv-0011": "valid",
    "mulberry-las-invoice-inv-1021": "valid",

    # Real discount hard cases. Their visible arithmetic is complete, but line totals
    # are discounted rather than simply quantity * undiscounted unit price.
    "town-house-publishing-invoice-0023902": "valid",
    "tomlinson-groundcare-invoice-139107": "valid",

    # The commercial invoice exposes subtotal and total but no VAT rate/amount; the
    # current validator therefore cannot independently complete its VAT/total checks.
    "jordan-customs-commercial-invoice-2019014782": "incomplete",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    annotated = 0
    unchecked: list[str] = []

    for document in manifest.get("documents", []):
        document_id = document.get("id")
        expected = document.setdefault("expected", {})
        status = EXPECTED_VALIDATION_STATUS.get(document_id)
        if status is None:
            unchecked.append(str(document_id))
            continue

        expected["validation_status"] = status
        annotated += 1

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "documents_total": len(manifest.get("documents", [])),
                "validation_status_annotated": annotated,
                "validation_status_unchecked": unchecked,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if annotated == 0:
        raise SystemExit("No reviewed public-reference validation status was applied.")


if __name__ == "__main__":
    main()
