from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class PurchaseOrderItem(BaseModel):
    line_number: str | None = None
    supplier_reference: str | None = None
    description: str
    need_by_date: date | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class PurchaseOrderData(BaseModel):
    supplier_name: str | None = None
    purchase_order_number: str | None = None
    order_date: date | None = None
    currency: str | None = None
    items: list[PurchaseOrderItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total: Decimal | None = None
    payment_terms: str | None = None
    notes: str | None = None
