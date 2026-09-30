from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz


def add_text_page(doc: fitz.Document, title: str, supplier: str, number_label: str, number: str,
                  date: str, currency: str, sku0: str, sku1: str, sku2: str,
                  p0: float, p1: float, p2: float, tax_rate: float, total: float,
                  *, po: str | None = None, discount: float = 0.0, freight: float = 0.0,
                  compact: bool = False, table: bool = True) -> None:
    page = doc.new_page(width=595, height=842)
    y = 55
    page.insert_text((50, y), title, fontsize=17)
    y += 26
    page.insert_text((50, y), supplier, fontsize=12)
    y += 24
    page.insert_text((50, y), f"{number_label}: {number}", fontsize=11)
    y += 18
    page.insert_text((50, y), f"Date: {date}", fontsize=10)
    y += 18
    page.insert_text((50, y), f"Currency: {currency}", fontsize=10)
    y += 18
    page.insert_text((50, y), "Customer: Northwind Industrial Ltd.", fontsize=10)
    if po:
        y += 18
        page.insert_text((50, y), f"Purchase Order: {po}", fontsize=10)
    y += 30

    items = [
        (sku0, "Industrial sensor module", 2, p0),
        (sku1, "Shielded control cable 10m", 5, p1),
        (sku2, "Mounting kit", 1, p2),
    ]
    subtotal = sum(q * p for _, _, q, p in items)

    if compact:
        page.insert_text((50, y), "ITEMS / COMMERCIAL TERMS", fontsize=10)
        y += 19
        for sku, desc, qty, price in items:
            line_total = qty * price
            page.insert_text((50, y), f"{sku}  {desc}  Qty {qty} x {price:.2f} = {line_total:.2f}", fontsize=9)
            y += 18
    else:
        cols = [50, 135, 340, 390, 465]
        headers = ["SKU", "Description", "Qty", "Unit Price", "Line Total"]
        for x, h in zip(cols, headers):
            page.insert_text((x, y), h, fontsize=9)
        if table:
            page.draw_line((45, y + 5), (550, y + 5))
        y += 20
        for sku, desc, qty, price in items:
            vals = [sku, desc, str(qty), f"{price:.2f}", f"{qty*price:.2f}"]
            for x, val in zip(cols, vals):
                page.insert_text((x, y), val, fontsize=8.5)
            y += 19

    def row(label: str, value: float) -> None:
        nonlocal y
        page.insert_text((360, y), label, fontsize=9)
        page.insert_text((475, y), f"{value:.2f}", fontsize=9)
        y += 18

    y += 12
    row("Subtotal", subtotal)
    if discount:
        row("Discount", -discount)
    if freight:
        row("Freight", freight)
    taxable = subtotal - discount + freight
    tax = round(taxable * tax_rate, 2)
    row(f"Tax ({int(tax_rate*100)}%)", tax)
    row("TOTAL", total)
    y += 18
    footer = "Payment due within 30 days. Please reference invoice and PO on remittance." if po else "Offer valid for 21 days. Delivery 7-10 working days. Incoterm DAP."
    page.insert_text((50, y), footer, fontsize=8.5)


def add_continuation(doc: fitz.Document, title: str, number_label: str, number: str) -> None:
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 55), f"{title} — continuation", fontsize=15)
    page.insert_text((50, 85), f"{number_label}: {number}", fontsize=10)
    y = 125
    for i in range(1, 19):
        page.insert_text((50, y), f"Terms line {i}: supply, packing, delivery and warranty conditions apply.", fontsize=9)
        y += 26


def make_digital(path: Path, spec: dict) -> None:
    doc = fitz.open()
    add_text_page(doc, **spec)
    if spec.get("multi_page"):
        add_continuation(doc, spec["title"], spec["number_label"], spec["number"])
    doc.save(path)
    doc.close()


def rasterize_document(src: Path, dst: Path, *, mixed: bool) -> None:
    source = fitz.open(src)
    out = fitz.open()
    for index, page in enumerate(source):
        if mixed and index == 0:
            out.insert_pdf(source, from_page=index, to_page=index)
            continue
        pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
    out.save(dst)
    out.close()
    source.close()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    args = parser.parse_args()
    root = Path(args.output).resolve()
    corpus = root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)

    specs = [
        ("generated-quotation-01-digital.pdf", "generated-quotation-01", "aster-controls-gmbh", "digital", "single-page-table", "supplier_quotation", "QT-2026-101", "EUR", "AX-101", "475.80", None, dict(title="SALES QUOTATION",supplier="Aster Controls GmbH",number_label="Document No.",number="QT-2026-101",date="03/09/2026",currency="EUR",sku0="AX-101",sku1="CB-102",sku2="MT-103",p0=128,p1=19.5,p2=43,tax_rate=.20,total=475.80,table=True)),
        ("generated-quotation-02-digital.pdf", "generated-quotation-02", "baltic-automation-ou", "digital", "single-page-borderless", "supplier_quotation", "QT-2026-102", "EUR", "AX-201", "490.20", None, dict(title="SALES QUOTATION",supplier="Baltic Automation OU",number_label="Document No.",number="QT-2026-102",date="04/09/2026",currency="EUR",sku0="AX-201",sku1="CB-202",sku2="MT-203",p0=131,p1=20.5,p2=44,tax_rate=.20,total=490.20,table=False)),
        ("generated-quotation-03-digital.pdf", "generated-quotation-03", "pacific-components-llc", "digital", "single-page-compact", "supplier_quotation", "QT-2026-103", "USD", "AX-301", "477.92", None, dict(title="SALES QUOTATION",supplier="Pacific Components LLC",number_label="Document No.",number="QT-2026-103",date="05/09/2026",currency="USD",sku0="AX-301",sku1="CB-302",sku2="MT-303",p0=134,p1=21.5,p2=45,tax_rate=.10,total=477.92,discount=21.03,freight=35,compact=True)),
        ("generated-quotation-04-digital.pdf", "generated-quotation-04", "northstar-measurement-ltd", "digital", "multi-page-table", "supplier_quotation", "QT-2026-104", "GBP", "AX-401", "504.90", None, dict(title="SALES QUOTATION",supplier="Northstar Measurement Ltd",number_label="Document No.",number="QT-2026-104",date="06/09/2026",currency="GBP",sku0="AX-401",sku1="CB-402",sku2="MT-403",p0=137,p1=22.5,p2=46,tax_rate=.08,total=504.90,freight=35,table=True,multi_page=True)),
        ("generated-quotation-05-scanned.pdf", "generated-quotation-05", "delta-process-systems", "scanned", "single-page-table", "supplier_quotation", "QT-2026-105", "USD", "AX-501", "488.95", None, dict(title="SALES QUOTATION",supplier="Delta Process Systems",number_label="Document No.",number="QT-2026-105",date="07/09/2026",currency="USD",sku0="AX-501",sku1="CB-502",sku2="MT-503",p0=140,p1=23.5,p2=47,tax_rate=.10,total=488.95,table=True)),
        ("generated-quotation-06-mixed.pdf", "generated-quotation-06", "orion-instrumentation-bv", "mixed", "multi-page-borderless", "supplier_quotation", "QT-2026-106", "EUR", "AX-601", "547.80", None, dict(title="SALES QUOTATION",supplier="Orion Instrumentation BV",number_label="Document No.",number="QT-2026-106",date="08/09/2026",currency="EUR",sku0="AX-601",sku1="CB-602",sku2="MT-603",p0=143,p1=24.5,p2=48,tax_rate=.20,total=547.80,table=False,multi_page=True)),
        ("generated-invoice-07-digital.pdf", "generated-invoice-07", "helios-industrial-supply", "digital", "single-page-table", "supplier_invoice", "INV-2026-207", "EUR", "AX-701", "562.20", "PO-8007", dict(title="SUPPLIER INVOICE",supplier="Helios Industrial Supply",number_label="Document No.",number="INV-2026-207",date="09/09/2026",currency="EUR",sku0="AX-701",sku1="CB-702",sku2="MT-703",p0=146,p1=25.5,p2=49,tax_rate=.20,total=562.20,po="PO-8007",table=True)),
        ("generated-invoice-08-digital.pdf", "generated-invoice-08", "vector-parts-inc", "digital", "single-page-borderless", "supplier_invoice", "INV-2026-208", "USD", "AX-801", "528.55", "PO-8008", dict(title="SUPPLIER INVOICE",supplier="Vector Parts Inc.",number_label="Document No.",number="INV-2026-208",date="10/09/2026",currency="USD",sku0="AX-801",sku1="CB-802",sku2="MT-803",p0=149,p1=26.5,p2=50,tax_rate=.10,total=528.55,po="PO-8008",table=False)),
        ("generated-invoice-09-digital.pdf", "generated-invoice-09", "atlas-engineering-spares", "digital", "single-page-compact", "supplier_invoice", "INV-2026-209", "GBP", "AX-901", "505.31", "PO-8009", dict(title="SUPPLIER INVOICE",supplier="Atlas Engineering Spares",number_label="Document No.",number="INV-2026-209",date="11/09/2026",currency="GBP",sku0="AX-901",sku1="CB-902",sku2="MT-903",p0=152,p1=27.5,p2=51,tax_rate=.08,total=505.31,po="PO-8009",discount=24.62,compact=True)),
        ("generated-invoice-10-digital.pdf", "generated-invoice-10", "meridian-sensors-sa", "digital", "multi-page-table", "supplier_invoice", "INV-2026-210", "EUR", "AX-1001", "647.40", "PO-8010", dict(title="SUPPLIER INVOICE",supplier="Meridian Sensors SA",number_label="Document No.",number="INV-2026-210",date="12/09/2026",currency="EUR",sku0="AX-1001",sku1="CB-1002",sku2="MT-1003",p0=155,p1=28.5,p2=52,tax_rate=.20,total=647.40,po="PO-8010",freight=35,table=True,multi_page=True)),
        ("generated-invoice-11-scanned.pdf", "generated-invoice-11", "ridgeway-controls-llc", "scanned", "single-page-table", "supplier_invoice", "INV-2026-211", "USD", "AX-1101", "568.15", "PO-8011", dict(title="SUPPLIER INVOICE",supplier="Ridgeway Controls LLC",number_label="Document No.",number="INV-2026-211",date="13/09/2026",currency="USD",sku0="AX-1101",sku1="CB-1102",sku2="MT-1103",p0=158,p1=29.5,p2=53,tax_rate=.10,total=568.15,po="PO-8011",table=True)),
        ("generated-invoice-12-mixed.pdf", "generated-invoice-12", "nova-process-equipment-bv", "mixed", "multi-page-borderless", "supplier_invoice", "INV-2026-212", "EUR", "AX-1201", "634.20", "PO-8012", dict(title="SUPPLIER INVOICE",supplier="Nova Process Equipment BV",number_label="Document No.",number="INV-2026-212",date="14/09/2026",currency="EUR",sku0="AX-1201",sku1="CB-1202",sku2="MT-1203",p0=161,p1=30.5,p2=54,tax_rate=.20,total=634.20,po="PO-8012",table=False,multi_page=True)),
    ]

    documents = []
    for filename, doc_id, supplier, source_kind, layout, doc_type, number, currency, sku, total, po, spec in specs:
        target = corpus / filename
        temp = corpus / ("tmp-" + filename)
        make_digital(temp if source_kind in {"scanned", "mixed"} else target, spec)
        if source_kind == "scanned":
            rasterize_document(temp, target, mixed=False)
            temp.unlink()
        elif source_kind == "mixed":
            rasterize_document(temp, target, mixed=True)
            temp.unlink()
        fields = {
            ("data.invoice_number" if doc_type == "supplier_invoice" else "data.quotation_number"): number,
            "data.currency": currency,
            "data.items.0.sku": sku,
            "data.total": total,
        }
        if po:
            fields["data.purchase_order_number"] = po
        documents.append({
            "id": doc_id,
            "file": f"corpus/{filename}",
            "sha256": sha256(target),
            "metadata": {"supplier": supplier, "source_kind": source_kind, "layout_class": layout, "language": "en", "tags": [doc_type.split("_")[-1], layout]},
            "document_type": "auto",
            "expected": {"document_type": doc_type, "validation_status": "valid", "fields": fields},
        })

    (root / "manifest.local.json").write_text(json.dumps({"version": 1, "documents": documents}, indent=2), encoding="utf-8")
    print(json.dumps({"documents": len(documents), "manifest": str(root / "manifest.local.json")}, indent=2))


if __name__ == "__main__":
    main()
