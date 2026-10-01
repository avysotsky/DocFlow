from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierInvoiceItem(BaseModel):
    sku: str | None = None
    description: str
    quantity: Decimal
    unit: str | None = None
    unit_price: Decimal | None = None
    discount_rate: Decimal | None = None
    line_total: Decimal | None = None


class SupplierInvoiceTaxBreakdown(BaseModel):
    category_code: str | None = None
    rate: Decimal
    taxable_amount: Decimal
    tax_amount: Decimal | None = None


class SupplierInvoiceData(BaseModel):
    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    customer_reference: str | None = None
    purchase_order_number: str | None = None
    items: list[SupplierInvoiceItem] = Field(default_factory=list)
    discount_amount: Decimal | None = None
    subtotal: Decimal | None = None
    vat_rate: Decimal | None = None
    vat_amount: Decimal | None = None
    tax_breakdown: list[SupplierInvoiceTaxBreakdown] = Field(default_factory=list)
    total: Decimal | None = None
    payment_terms: str | None = None
    notes: str | None = None
