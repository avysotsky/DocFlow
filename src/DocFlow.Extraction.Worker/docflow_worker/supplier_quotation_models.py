from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierQuotationItem(BaseModel):
    sku: str
    description: str
    quantity: Decimal
    unit: str | None = None
    unit_price: Decimal | None = None
    lead_time_days: int | None = None
    line_total: Decimal | None = None


class SupplierQuotationData(BaseModel):
    supplier_name: str | None = None
    quotation_number: str | None = None
    quotation_date: date | None = None
    valid_until: date | None = None
    currency: str | None = None
    customer_reference: str | None = None
    incoterms: str | None = None
    items: list[SupplierQuotationItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_amount: Decimal | None = None
    total: Decimal | None = None
    payment_terms: str | None = None
    delivery: str | None = None
    warranty: str | None = None
    notes: str | None = None
    prepared_by: str | None = None
    quote_status: str | None = None
