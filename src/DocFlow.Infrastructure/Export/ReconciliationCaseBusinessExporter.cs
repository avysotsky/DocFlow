using System.IO.Compression;
using System.Text;
using System.Xml;
using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Export;

internal sealed record ReconciliationBusinessCheck(
    string Scope,
    string InvoiceItemIndex,
    string PurchaseOrderItemIndex,
    string MatchMethod,
    string InvoiceSku,
    string PurchaseOrderReference,
    string Field,
    string CheckStatus,
    string InvoiceValue,
    string PurchaseOrderValue,
    string Delta,
    string Message);

internal static class ReconciliationCaseBusinessExporter
{
    private const string SpreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private const string OfficeRelationshipsNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private const string PackageRelationshipsNamespace = "http://schemas.openxmlformats.org/package/2006/relationships";
    private const string ContentTypesNamespace = "http://schemas.openxmlformats.org/package/2006/content-types";

    private static readonly string[] CsvHeaders =
    [
        "CaseId",
        "InvoiceDocumentId",
        "PurchaseOrderDocumentId",
        "ReconciliationStatus",
        "ReviewStatus",
        "CheckScope",
        "InvoiceItemIndex",
        "PurchaseOrderItemIndex",
        "MatchMethod",
        "InvoiceSku",
        "PurchaseOrderReference",
        "Field",
        "CheckStatus",
        "InvoiceValue",
        "PurchaseOrderValue",
        "Delta",
        "Message",
        "LatestAction",
        "LatestDecisionNote",
        "LatestReviewer",
        "LatestActionAt"
    ];

    private static readonly string[] CheckHeaders =
    [
        "CheckScope",
        "InvoiceItemIndex",
        "PurchaseOrderItemIndex",
        "MatchMethod",
        "InvoiceSku",
        "PurchaseOrderReference",
        "Field",
        "CheckStatus",
        "InvoiceValue",
        "PurchaseOrderValue",
        "Delta",
        "Message"
    ];

    private static readonly string[] AuditHeaders =
    [
        "Action",
        "PreviousStatus",
        "NewStatus",
        "Note",
        "PerformedByClient",
        "OccurredAt"
    ];

    public static byte[] ToCsv(ReconciliationCaseSnapshot snapshot)
    {
        var checks = FlattenChecks(snapshot);
        var latestAudit = snapshot.AuditHistory.LastOrDefault();

        using var stream = new MemoryStream();
        using (var writer = new StreamWriter(
                   stream,
                   new UTF8Encoding(encoderShouldEmitUTF8Identifier: true),
                   bufferSize: 1024,
                   leaveOpen: true))
        {
            writer.NewLine = "\r\n";
            WriteCsvRow(writer, CsvHeaders);

            if (checks.Count == 0)
                WriteCsvRow(writer, BuildCsvRow(snapshot, null, latestAudit));
            else
                foreach (var check in checks)
                    WriteCsvRow(writer, BuildCsvRow(snapshot, check, latestAudit));
        }

        return stream.ToArray();
    }

    public static byte[] ToXlsx(ReconciliationCaseSnapshot snapshot)
    {
        var checks = FlattenChecks(snapshot);

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
                writer => WriteCaseWorksheet(writer, snapshot));
            WriteXmlEntry(
                archive,
                "xl/worksheets/sheet2.xml",
                writer => WriteChecksWorksheet(writer, checks));
            WriteXmlEntry(
                archive,
                "xl/worksheets/sheet3.xml",
                writer => WriteAuditWorksheet(writer, snapshot.AuditHistory));
        }

        return stream.ToArray();
    }

    private static IReadOnlyList<ReconciliationBusinessCheck> FlattenChecks(
        ReconciliationCaseSnapshot snapshot)
    {
        var result = new List<ReconciliationBusinessCheck>();

        foreach (var check in snapshot.Report.DocumentChecks)
        {
            result.Add(new ReconciliationBusinessCheck(
                "Document",
                string.Empty,
                string.Empty,
                string.Empty,
                string.Empty,
                string.Empty,
                check.Field,
                check.Status.ToString(),
                check.InvoiceValue ?? string.Empty,
                check.PurchaseOrderValue ?? string.Empty,
                check.Delta ?? string.Empty,
                check.Message));
        }

        foreach (var item in snapshot.Report.InvoiceItems)
        {
            foreach (var check in item.Checks)
            {
                result.Add(new ReconciliationBusinessCheck(
                    "InvoiceItem",
                    item.InvoiceItemIndex.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    item.PurchaseOrderItemIndex?.ToString(System.Globalization.CultureInfo.InvariantCulture) ?? string.Empty,
                    item.MatchMethod,
                    item.InvoiceSku ?? string.Empty,
                    item.PurchaseOrderReference ?? string.Empty,
                    check.Field,
                    check.Status.ToString(),
                    check.InvoiceValue ?? string.Empty,
                    check.PurchaseOrderValue ?? string.Empty,
                    check.Delta ?? string.Empty,
                    check.Message));
            }
        }

        return result;
    }

    private static string[] BuildCsvRow(
        ReconciliationCaseSnapshot snapshot,
        ReconciliationBusinessCheck? check,
        ReconciliationCaseAuditEntry? latestAudit)
        =>
        [
            snapshot.Id.ToString("D"),
            snapshot.InvoiceDocumentId.ToString("D"),
            snapshot.PurchaseOrderDocumentId.ToString("D"),
            snapshot.ReconciliationStatus,
            snapshot.ReviewStatus,
            check?.Scope ?? string.Empty,
            check?.InvoiceItemIndex ?? string.Empty,
            check?.PurchaseOrderItemIndex ?? string.Empty,
            check?.MatchMethod ?? string.Empty,
            check?.InvoiceSku ?? string.Empty,
            check?.PurchaseOrderReference ?? string.Empty,
            check?.Field ?? string.Empty,
            check?.CheckStatus ?? string.Empty,
            check?.InvoiceValue ?? string.Empty,
            check?.PurchaseOrderValue ?? string.Empty,
            check?.Delta ?? string.Empty,
            check?.Message ?? string.Empty,
            latestAudit?.Action ?? string.Empty,
            latestAudit?.Note ?? string.Empty,
            latestAudit?.PerformedByClient ?? string.Empty,
            latestAudit?.OccurredAt.ToString("O") ?? string.Empty
        ];

    private static void WriteCaseWorksheet(
        XmlWriter writer,
        ReconciliationCaseSnapshot snapshot)
    {
        var latestAudit = snapshot.AuditHistory.LastOrDefault();
        var rows = new (string Field, string Value)[]
        {
            ("Case Id", snapshot.Id.ToString("D")),
            ("Invoice Document Id", snapshot.InvoiceDocumentId.ToString("D")),
            ("Purchase Order Document Id", snapshot.PurchaseOrderDocumentId.ToString("D")),
            ("Reconciliation Status", snapshot.ReconciliationStatus),
            ("Review Status", snapshot.ReviewStatus),
            ("Passed Checks", snapshot.Report.PassedChecks.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("Needs Review Checks", snapshot.Report.NeedsReviewChecks.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("Skipped Checks", snapshot.Report.SkippedChecks.ToString(System.Globalization.CultureInfo.InvariantCulture)),
            ("Created At", snapshot.CreatedAt.ToString("O")),
            ("Updated At", snapshot.UpdatedAt.ToString("O")),
            ("Created By Client", snapshot.CreatedByClient),
            ("Latest Action", latestAudit?.Action ?? string.Empty),
            ("Latest Decision Note", latestAudit?.Note ?? string.Empty),
            ("Latest Reviewer", latestAudit?.PerformedByClient ?? string.Empty),
            ("Latest Action At", latestAudit?.OccurredAt.ToString("O") ?? string.Empty)
        };

        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(writer, (1, 30d), (2, 80d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteRow(writer, 1, ["Field", "Value"]);
        var rowNumber = 2;
        foreach (var row in rows)
            WriteRow(writer, rowNumber++, [row.Field, row.Value]);
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteChecksWorksheet(
        XmlWriter writer,
        IReadOnlyList<ReconciliationBusinessCheck> checks)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(
            writer,
            (1, 16d), (2, 16d), (3, 20d), (4, 20d),
            (5, 20d), (6, 24d), (7, 20d), (8, 18d),
            (9, 24d), (10, 24d), (11, 16d), (12, 80d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteRow(writer, 1, CheckHeaders);

        var rowNumber = 2;
        foreach (var check in checks)
        {
            WriteRow(
                writer,
                rowNumber++,
                [
                    check.Scope,
                    check.InvoiceItemIndex,
                    check.PurchaseOrderItemIndex,
                    check.MatchMethod,
                    check.InvoiceSku,
                    check.PurchaseOrderReference,
                    check.Field,
                    check.CheckStatus,
                    check.InvoiceValue,
                    check.PurchaseOrderValue,
                    check.Delta,
                    check.Message
                ]);
        }

        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteAuditWorksheet(
        XmlWriter writer,
        IReadOnlyList<ReconciliationCaseAuditEntry> auditHistory)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);
        WriteColumns(
            writer,
            (1, 16d), (2, 18d), (3, 18d),
            (4, 80d), (5, 24d), (6, 32d));
        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteRow(writer, 1, AuditHeaders);

        var rowNumber = 2;
        foreach (var entry in auditHistory)
        {
            WriteRow(
                writer,
                rowNumber++,
                [
                    entry.Action,
                    entry.PreviousStatus ?? string.Empty,
                    entry.NewStatus,
                    entry.Note ?? string.Empty,
                    entry.PerformedByClient,
                    entry.OccurredAt.ToString("O")
                ]);
        }

        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
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
        WriteOverride(writer, "/xl/worksheets/sheet3.xml", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
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
        WriteSheet(writer, "Case", 1, "rId1");
        WriteSheet(writer, "Checks", 2, "rId2");
        WriteSheet(writer, "Audit History", 3, "rId3");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorkbookRelationships(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Relationships", PackageRelationshipsNamespace);
        WriteRelationship(writer, "rId1", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "worksheets/sheet1.xml");
        WriteRelationship(writer, "rId2", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "worksheets/sheet2.xml");
        WriteRelationship(writer, "rId3", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "worksheets/sheet3.xml");
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

    private static void WriteRelationship(XmlWriter writer, string id, string type, string target)
    {
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", id);
        writer.WriteAttributeString("Type", type);
        writer.WriteAttributeString("Target", target);
        writer.WriteEndElement();
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
