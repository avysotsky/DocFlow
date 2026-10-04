using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Xml;

namespace DocFlow.Infrastructure.Export;

internal sealed record SupplierInvoiceBusinessExport(
    string Supplier,
    string InvoiceNumber,
    string InvoiceDate,
    string DueDate,
    string Currency,
    string CustomerReference,
    string PurchaseOrderNumber,
    string Subtotal,
    string VatRate,
    string VatAmount,
    string Total,
    string DuplicateStatus,
    string DuplicateOfDocumentId,
    string ValidationStatus,
    string ReviewStatus,
    IReadOnlyList<SupplierInvoiceBusinessLine> Items);

internal sealed record SupplierInvoiceBusinessLine(
    string Sku,
    string Description,
    string Quantity,
    string Unit,
    string UnitPrice,
    string DiscountRate,
    string LineTotal);

internal static class SupplierInvoiceBusinessExporter
{
    private const string SpreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private const string OfficeRelationshipsNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private const string PackageRelationshipsNamespace = "http://schemas.openxmlformats.org/package/2006/relationships";
    private const string ContentTypesNamespace = "http://schemas.openxmlformats.org/package/2006/content-types";

    private static readonly string[] CsvHeaders =
    [
        "Supplier",
        "InvoiceNumber",
        "InvoiceDate",
        "DueDate",
        "Currency",
        "CustomerReference",
        "PurchaseOrderNumber",
        "SKU",
        "Description",
        "Quantity",
        "Unit",
        "UnitPrice",
        "DiscountRate",
        "LineTotal",
        "Subtotal",
        "VATRate",
        "VATAmount",
        "Total",
        "DuplicateStatus",
        "DuplicateOfDocumentId",
        "ValidationStatus",
        "ReviewStatus"
    ];

    private static readonly string[] ItemHeaders =
    [
        "SKU",
        "Description",
        "Quantity",
        "Unit",
        "UnitPrice",
        "DiscountRate",
        "LineTotal"
    ];

    public static SupplierInvoiceBusinessExport Parse(
        string structuredDataJson,
        string validationStatus,
        bool hasHumanReview)
    {
        if (string.IsNullOrWhiteSpace(structuredDataJson))
            throw new ArgumentException("Structured data JSON is required.", nameof(structuredDataJson));

        using var document = JsonDocument.Parse(structuredDataJson);
        var root = document.RootElement;

        var documentType = Read(root, "document_type");
        if (!string.Equals(documentType, "supplier_invoice", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "Business invoice export is only available for supplier_invoice documents.");
        }

        if (!root.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException("Supplier invoice structured data is missing the data object.");

        var items = new List<SupplierInvoiceBusinessLine>();
        if (data.TryGetProperty("items", out var itemArray)
            && itemArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in itemArray.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object)
                    continue;

                items.Add(new SupplierInvoiceBusinessLine(
                    Read(item, "sku"),
                    Read(item, "description"),
                    Read(item, "quantity"),
                    Read(item, "unit"),
                    Read(item, "unit_price"),
                    Read(item, "discount_rate"),
                    Read(item, "line_total")));
            }
        }

        var duplicateStatus = string.Empty;
        var duplicateOfDocumentId = string.Empty;
        if (root.TryGetProperty("business_checks", out var businessChecks)
            && businessChecks.ValueKind == JsonValueKind.Object
            && businessChecks.TryGetProperty("duplicate_check", out var duplicateCheck)
            && duplicateCheck.ValueKind == JsonValueKind.Object)
        {
            duplicateStatus = Read(duplicateCheck, "status");
            duplicateOfDocumentId = Read(duplicateCheck, "duplicate_of_document_id");
        }

        return new SupplierInvoiceBusinessExport(
            Read(data, "supplier_name"),
            Read(data, "invoice_number"),
            Read(data, "invoice_date"),
            Read(data, "due_date"),
            Read(data, "currency"),
            Read(data, "customer_reference"),
            Read(data, "purchase_order_number"),
            Read(data, "subtotal"),
            Read(data, "vat_rate"),
            Read(data, "vat_amount"),
            Read(data, "total"),
            duplicateStatus,
            duplicateOfDocumentId,
            validationStatus,
            hasHumanReview ? "Reviewed" : "NotReviewed",
            items);
    }

    public static byte[] ToCsv(SupplierInvoiceBusinessExport invoice)
    {
        using var stream = new MemoryStream();
        using (var writer = new StreamWriter(
                   stream,
                   new UTF8Encoding(encoderShouldEmitUTF8Identifier: true),
                   bufferSize: 1024,
                   leaveOpen: true))
        {
            writer.NewLine = "\r\n";
            WriteCsvRow(writer, CsvHeaders);

            if (invoice.Items.Count == 0)
            {
                WriteCsvRow(writer, BuildCsvRow(invoice, null));
            }
            else
            {
                foreach (var item in invoice.Items)
                    WriteCsvRow(writer, BuildCsvRow(invoice, item));
            }
        }

        return stream.ToArray();
    }

    public static byte[] ToXlsx(SupplierInvoiceBusinessExport invoice)
    {
        using var stream = new MemoryStream();

        using (var archive = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: true))
        {
            WriteXmlEntry(archive, "[Content_Types].xml", WriteContentTypes);
            WriteXmlEntry(archive, "_rels/.rels", WritePackageRelationships);
            WriteXmlEntry(archive, "xl/workbook.xml", WriteWorkbook);
            WriteXmlEntry(archive, "xl/_rels/workbook.xml.rels", WriteWorkbookRelationships);
            WriteXmlEntry(
                archive,
                "xl/worksheets/sheet1.xml",
                writer => WriteSummaryWorksheet(writer, invoice));
            WriteXmlEntry(
                archive,
                "xl/worksheets/sheet2.xml",
                writer => WriteItemsWorksheet(writer, invoice.Items));
        }

        return stream.ToArray();
    }

    private static string[] BuildCsvRow(
        SupplierInvoiceBusinessExport invoice,
        SupplierInvoiceBusinessLine? item)
    {
        return
        [
            invoice.Supplier,
            invoice.InvoiceNumber,
            invoice.InvoiceDate,
            invoice.DueDate,
            invoice.Currency,
            invoice.CustomerReference,
            invoice.PurchaseOrderNumber,
            item?.Sku ?? string.Empty,
            item?.Description ?? string.Empty,
            item?.Quantity ?? string.Empty,
            item?.Unit ?? string.Empty,
            item?.UnitPrice ?? string.Empty,
            item?.DiscountRate ?? string.Empty,
            item?.LineTotal ?? string.Empty,
            invoice.Subtotal,
            invoice.VatRate,
            invoice.VatAmount,
            invoice.Total,
            invoice.DuplicateStatus,
            invoice.DuplicateOfDocumentId,
            invoice.ValidationStatus,
            invoice.ReviewStatus
        ];
    }

    private static string Read(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value)
            || value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
        {
            return string.Empty;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString() ?? string.Empty,
            JsonValueKind.Number => value.GetRawText(),
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            _ => value.GetRawText()
        };
    }

    private static void WriteCsvRow(TextWriter writer, IEnumerable<string> values)
    {
        writer.WriteLine(string.Join(",", values.Select(EscapeCsv)));
    }

    private static string EscapeCsv(string value)
        => $"\"{value.Replace("\"", "\"\"")}\"";

    private static void WriteXmlEntry(
        ZipArchive archive,
        string path,
        Action<XmlWriter> write)
    {
        var entry = archive.CreateEntry(path, CompressionLevel.Optimal);
        using var entryStream = entry.Open();
        using var writer = XmlWriter.Create(
            entryStream,
            new XmlWriterSettings
            {
                Encoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
                Indent = false,
                CloseOutput = false
            });
        write(writer);
    }

    private static void WriteContentTypes(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Types", ContentTypesNamespace);
        WriteContentTypeDefault(writer, "rels", "application/vnd.openxmlformats-package.relationships+xml");
        WriteContentTypeDefault(writer, "xml", "application/xml");
        WriteContentTypeOverride(
            writer,
            "/xl/workbook.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml");
        WriteContentTypeOverride(
            writer,
            "/xl/worksheets/sheet1.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
        WriteContentTypeOverride(
            writer,
            "/xl/worksheets/sheet2.xml",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteContentTypeDefault(
        XmlWriter writer,
        string extension,
        string contentType)
    {
        writer.WriteStartElement("Default", ContentTypesNamespace);
        writer.WriteAttributeString("Extension", extension);
        writer.WriteAttributeString("ContentType", contentType);
        writer.WriteEndElement();
    }

    private static void WriteContentTypeOverride(
        XmlWriter writer,
        string partName,
        string contentType)
    {
        writer.WriteStartElement("Override", ContentTypesNamespace);
        writer.WriteAttributeString("PartName", partName);
        writer.WriteAttributeString("ContentType", contentType);
        writer.WriteEndElement();
    }

    private static void WritePackageRelationships(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Relationships", PackageRelationshipsNamespace);
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", "rId1");
        writer.WriteAttributeString(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument");
        writer.WriteAttributeString("Target", "xl/workbook.xml");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorkbook(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("workbook", SpreadsheetNamespace);
        writer.WriteAttributeString("xmlns", "r", null, OfficeRelationshipsNamespace);
        writer.WriteStartElement("sheets", SpreadsheetNamespace);
        WriteSheet(writer, "Invoice", 1, "rId1");
        WriteSheet(writer, "Line Items", 2, "rId2");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteSheet(
        XmlWriter writer,
        string name,
        int sheetId,
        string relationshipId)
    {
        writer.WriteStartElement("sheet", SpreadsheetNamespace);
        writer.WriteAttributeString("name", name);
        writer.WriteAttributeString("sheetId", sheetId.ToString(System.Globalization.CultureInfo.InvariantCulture));
        writer.WriteAttributeString("r", "id", OfficeRelationshipsNamespace, relationshipId);
        writer.WriteEndElement();
    }

    private static void WriteWorkbookRelationships(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Relationships", PackageRelationshipsNamespace);
        WriteWorksheetRelationship(writer, "rId1", "worksheets/sheet1.xml");
        WriteWorksheetRelationship(writer, "rId2", "worksheets/sheet2.xml");
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorksheetRelationship(
        XmlWriter writer,
        string id,
        string target)
    {
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", id);
        writer.WriteAttributeString(
            "Type",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet");
        writer.WriteAttributeString("Target", target);
        writer.WriteEndElement();
    }

    private static void WriteSummaryWorksheet(
        XmlWriter writer,
        SupplierInvoiceBusinessExport invoice)
    {
        var rows = new (string Field, string Value)[]
        {
            ("Supplier", invoice.Supplier),
            ("Invoice Number", invoice.InvoiceNumber),
            ("Invoice Date", invoice.InvoiceDate),
            ("Due Date", invoice.DueDate),
            ("Currency", invoice.Currency),
            ("Customer Reference", invoice.CustomerReference),
            ("Purchase Order Number", invoice.PurchaseOrderNumber),
            ("Subtotal", invoice.Subtotal),
            ("VAT Rate", invoice.VatRate),
            ("VAT Amount", invoice.VatAmount),
            ("Total", invoice.Total),
            ("Duplicate Status", invoice.DuplicateStatus),
            ("Duplicate Of Document Id", invoice.DuplicateOfDocumentId),
            ("Validation Status", invoice.ValidationStatus),
            ("Review Status", invoice.ReviewStatus)
        };

        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(writer, (1, 28d), (2, 60d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteWorksheetRow(writer, 1, ["Field", "Value"]);
        var rowNumber = 2;
        foreach (var row in rows)
        {
            WriteWorksheetRow(writer, rowNumber++, [row.Field, row.Value]);
        }
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteItemsWorksheet(
        XmlWriter writer,
        IReadOnlyList<SupplierInvoiceBusinessLine> items)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(
            writer,
            (1, 18d),
            (2, 64d),
            (3, 14d),
            (4, 12d),
            (5, 16d),
            (6, 16d),
            (7, 16d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteWorksheetRow(writer, 1, ItemHeaders);

        var rowNumber = 2;
        foreach (var item in items)
        {
            WriteWorksheetRow(
                writer,
                rowNumber++,
                [
                    item.Sku,
                    item.Description,
                    item.Quantity,
                    item.Unit,
                    item.UnitPrice,
                    item.DiscountRate,
                    item.LineTotal
                ]);
        }

        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteColumns(
        XmlWriter writer,
        params (int Column, double Width)[] columns)
    {
        writer.WriteStartElement("cols", SpreadsheetNamespace);
        foreach (var column in columns)
        {
            writer.WriteStartElement("col", SpreadsheetNamespace);
            writer.WriteAttributeString("min", column.Column.ToString(System.Globalization.CultureInfo.InvariantCulture));
            writer.WriteAttributeString("max", column.Column.ToString(System.Globalization.CultureInfo.InvariantCulture));
            writer.WriteAttributeString("width", column.Width.ToString(System.Globalization.CultureInfo.InvariantCulture));
            writer.WriteAttributeString("customWidth", "1");
            writer.WriteEndElement();
        }
        writer.WriteEndElement();
    }

    private static void WriteWorksheetRow(
        XmlWriter writer,
        int rowNumber,
        IReadOnlyList<string> values)
    {
        writer.WriteStartElement("row", SpreadsheetNamespace);
        writer.WriteAttributeString("r", rowNumber.ToString(System.Globalization.CultureInfo.InvariantCulture));

        for (var index = 0; index < values.Count; index++)
        {
            WriteInlineStringCell(
                writer,
                $"{ColumnName(index + 1)}{rowNumber}",
                values[index]);
        }

        writer.WriteEndElement();
    }

    private static void WriteInlineStringCell(
        XmlWriter writer,
        string reference,
        string value)
    {
        writer.WriteStartElement("c", SpreadsheetNamespace);
        writer.WriteAttributeString("r", reference);
        writer.WriteAttributeString("t", "inlineStr");
        writer.WriteStartElement("is", SpreadsheetNamespace);
        writer.WriteStartElement("t", SpreadsheetNamespace);
        writer.WriteAttributeString("xml", "space", "http://www.w3.org/XML/1998/namespace", "preserve");
        writer.WriteString(value);
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndElement();
    }

    private static string ColumnName(int index)
    {
        var value = index;
        var builder = new StringBuilder();
        while (value > 0)
        {
            value--;
            builder.Insert(0, (char)('A' + value % 26));
            value /= 26;
        }
        return builder.ToString();
    }
}
