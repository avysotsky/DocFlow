from __future__ import annotations


_LAYOUT_SUFFIXES = (
    "PAYMENTADVICE",
    "PAYMENT",
)


def normalize_invoice_identifier(value: str | None) -> str | None:
    """Remove known neighboring-column text concatenated to an invoice number.

    Some PDF generators expose a visual ``PAYMENT ADVICE`` column without a text
    separator, producing values such as ``INV-23226PAYMENT``. Keep the business
    identifier and discard only the confirmed layout suffix.
    """
    if value is None:
        return None

    normalized = value.strip()
    upper = normalized.upper().replace(" ", "")

    for suffix in _LAYOUT_SUFFIXES:
        position = upper.find(suffix)
        if position > 0:
            # The suffix lookup is length-preserving for the observed concatenated
            # tokens because the candidate itself contains no internal whitespace.
            normalized = normalized[:position].rstrip("._/- ")
            break

    return normalized or None
