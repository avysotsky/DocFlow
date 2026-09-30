from docflow_worker.invoice_identifiers import normalize_invoice_identifier


def test_strips_concatenated_payment_suffix() -> None:
    assert normalize_invoice_identifier("INV-23226PAYMENT") == "INV-23226"
    assert normalize_invoice_identifier("INV-0011PAYMENT") == "INV-0011"
    assert normalize_invoice_identifier("INV-1021PAYMENT") == "INV-1021"


def test_preserves_normal_invoice_identifier() -> None:
    assert normalize_invoice_identifier("INV-2026-091") == "INV-2026-091"
    assert normalize_invoice_identifier("2019014782") == "2019014782"
    assert normalize_invoice_identifier(None) is None
