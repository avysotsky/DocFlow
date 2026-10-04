using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Xml;

namespace DocFlow.Infrastructure.Export;

internal sealed record PurchaseOrderBusinessExport(
    string Supplier,
    string PurchaseOrderNumber,
    string OrderDate,
    string Currency,
    string Subtotal,
    string TaxAmount,
    string Total,
    string ValidationStatus,
    string ReviewStatus,
    IReadOnlyList<PurchaseOrderBusinessLine> Items);

internal sealed record PurchaseOrderBusinessLine(
    string LineNumber,
    string SupplierReference,
    string Description,
    string NeedByDate,
    string Quantity,
    string Unit,
    string UnitPrice,
    string LineTotal);

internal static class PurchaseOrderBusinessExporter
{
    private const string SpreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private const string OfficeRelationshipsNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private const string PackageRelationshipsNamespace = "http://schemas.openxmlformats.org/package/2006/relationships";
    private const string ContentTypesNamespace = "http://schemas.openxmlformats.org/package/2006/content-types";

    private static readonly string[] CsvHeaders =
    [
        "Supplier",
        "PurchaseOrderNumber",
        "OrderDate",
        "Currency",
        "LineNumber",
        "SupplierReference",
        "Description",
        "NeedByDate",
        "Quantity",
        "Unit",
        "UnitPrice",
        "LineTotal",
        "Subtotal",
        "TaxAmount",
        "Total",
        "ValidationStatus",
        "ReviewStatus"
    ];

    private static readonly string[] ItemHeaders =
    [
        "LineNumber",
        "SupplierReference",
        "Description",
        "NeedByDate",
        "Quantity",
        "Unit",
        "UnitPrice",
        "LineTotal"
    ];

    public static PurchaseOrderBusinessExport Parse(
        string structuredDataJson,
        string validationStatus,
        bool hasHumanReview)
    {
        using var document = JsonDocument.Parse(structuredDataJson);
        var root = document.RootElement;

        var documentType = Read(root, "document_type");
        if (!string.Equals(documentType, "purchase_order", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "Business purchase-order export is only available for purchase_order documents.");
        }

        if (!root.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException("Purchase-order structured data is missing the data object.");

        var items = new List<PurchaseOrderBusinessLine>();
        if (data.TryGetProperty("items", out var itemArray)
            && itemArray.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in itemArray.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.Object)
                    continue;

                items.Add(new PurchaseOrderBusinessLine(
                    Read(item, "line_number"),
                    Read(item, "supplier_reference"),
                    Read(item, "description"),
                    Read(item, "need_by_date"),
                    Read(item, "quantity"),
                    Read(item, "unit"),
                    Read(item, "unit_price"),
                    Read(item, "line_total")));
            }
        }

        return new PurchaseOrderBusinessExport(
            Read(data, "supplier_name"),
            Read(data, "purchase_order_number"),
            Read(data, "order_date"),
            Read(data, "currency"),
            Read(data, "subtotal"),
            Read(data, "tax_amount"),
            Read(data, "total"),
            validationStatus,
            hasHumanReview ? "Reviewed" : "NotReviewed",
            items);
    }

    public static byte[] ToCsv(PurchaseOrderBusinessExport purchaseOrder)
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

            if (purchaseOrder.Items.Count == 0)
            {
                WriteCsvRow(writer, BuildCsvRow(purchaseOrder, null));
            }
            else
            {
                foreach (var item in purchaseOrder.Items)
                    WriteCsvRow(writer, BuildCsvRow(purchaseOrder, item));
            }
        }
        return stream.ToArray();
    }

    public static byte[] ToXlsx(PurchaseOrderBusinessExport purchaseOrder)
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
                writer => WriteSummaryWorksheet(writer, purchaseOrder));
            WriteXmlEntry(
                archive,
                "xl/worksheets/sheet2.xml",
                writer => WriteItemsWorksheet(writer, purchaseOrder.Items));
        }

        return stream.ToArray();
    }

    private static string[] BuildCsvRow(
        PurchaseOrderBusinessExport po,
        PurchaseOrderBusinessLine? item)
        =>
        [
            po.Supplier,
            po.PurchaseOrderNumber,
            po.OrderDate,
            po.Currency,
            item?.LineNumber ?? string.Empty,
            item?.SupplierReference ?? string.Empty,
            item?.Description ?? string.Empty,
            item?.NeedByDate ?? string.Empty,
            item?.Quantity ?? string.Empty,
            item?.Unit ?? string.Empty,
            item?.UnitPrice ?? string.Empty,
            item?.LineTotal ?? string.Empty,
            po.Subtotal,
            po.TaxAmount,
            po.Total,
            po.ValidationStatus,
            po.ReviewStatus
        ];

    private static string Read(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out var value)
            || value.ValueKind is JsonValueKind.Null or JsonValueKind.Undefined)
            return string.Empty;

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
        => writer.WriteLine(string.Join(",", values.Select(EscapeCsv)));

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
                Encoding = new UTF8Encoding(false),
                Indent = false,
                CloseOutput = false
            });
        write(writer);
    }

    private static void WriteContentTypes(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Types", ContentTypesNamespace);
        WriteDefault(writer, "rels", "application/vnd.openxmlformats-package.relationships+xml");
        WriteDefault(writer, "xml", "application/xml");
        WriteOverride(writer, "/xl/workbook.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml");
        WriteOverride(writer, "/xl/worksheets/sheet1.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
        WriteOverride(writer, "/xl/worksheets/sheet2.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteDefault(XmlWriter writer, string extension, string contentType)
    {
        writer.WriteStartElement("Default", ContentTypesNamespace);
        writer.WriteAttributeString("Extension", extension);
        writer.WriteAttributeString("ContentType", contentType);
        writer.WriteEndElement();
    }

    private static void WriteOverride(XmlWriter writer, string partName, string contentType)
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
        WriteRelationship(
            writer,
            "rId1",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            "xl/workbook.xml");
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorkbook(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("workbook", SpreadsheetNamespace);
        writer.WriteAttributeString("xmlns", "r", null, OfficeRelationshipsNamespace);
        writer.WriteStartElement("sheets", SpreadsheetNamespace);
        WriteSheet(writer, "Purchase Order", 1, "rId1");
        WriteSheet(writer, "Line Items", 2, "rId2");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteSheet(XmlWriter writer, string name, int sheetId, string relationshipId)
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
        WriteRelationship(
            writer,
            "rId1",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            "worksheets/sheet1.xml");
        WriteRelationship(
            writer,
            "rId2",
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
            "worksheets/sheet2.xml");
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteRelationship(
        XmlWriter writer,
        string id,
        string type,
        string target)
    {
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", id);
        writer.WriteAttributeString("Type", type);
        writer.WriteAttributeString("Target", target);
        writer.WriteEndElement();
    }

    private static void WriteSummaryWorksheet(XmlWriter writer, PurchaseOrderBusinessExport po)
    {
        var rows = new (string Field, string Value)[]
        {
            ("Supplier", po.Supplier),
            ("Purchase Order Number", po.PurchaseOrderNumber),
            ("Order Date", po.OrderDate),
            ("Currency", po.Currency),
            ("Subtotal", po.Subtotal),
            ("Tax Amount", po.TaxAmount),
            ("Total", po.Total),
            ("Validation Status", po.ValidationStatus),
            ("Review Status", po.ReviewStatus)
        };

        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(writer, (1, 30d), (2, 64d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteRow(writer, 1, ["Field", "Value"]);
        var rowNumber = 2;
        foreach (var row in rows)
            WriteRow(writer, rowNumber++, [row.Field, row.Value]);
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteItemsWorksheet(
        XmlWriter writer,
        IReadOnlyList<PurchaseOrderBusinessLine> items)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(
            writer,
            (1, 12d),
            (2, 20d),
            (3, 64d),
            (4, 16d),
            (5, 14d),
            (6, 14d),
            (7, 16d),
            (8, 16d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteRow(writer, 1, ItemHeaders);

        var rowNumber = 2;
        foreach (var item in items)
        {
            WriteRow(
                writer,
                rowNumber++,
                [
                    item.LineNumber,
                    item.SupplierReference,
                    item.Description,
                    item.NeedByDate,
                    item.Quantity,
                    item.Unit,
                    item.UnitPrice,
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

    private static void WriteRow(
        XmlWriter writer,
        int rowNumber,
        IReadOnlyList<string> values)
    {
        writer.WriteStartElement("row", SpreadsheetNamespace);
        writer.WriteAttributeString("r", rowNumber.ToString(System.Globalization.CultureInfo.InvariantCulture));
        for (var index = 0; index < values.Count; index++)
            WriteCell(writer, $"{ColumnName(index + 1)}{rowNumber}", values[index]);
        writer.WriteEndElement();
    }

    private static void WriteCell(XmlWriter writer, string reference, string value)
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
