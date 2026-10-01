using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Xml;

namespace DocFlow.Infrastructure.Export;

internal sealed record StructuredDataExportRow(string Path, string Value);

internal static class StructuredDataTabularExporter
{
    private const string SpreadsheetNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
    private const string OfficeRelationshipsNamespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    private const string PackageRelationshipsNamespace = "http://schemas.openxmlformats.org/package/2006/relationships";
    private const string ContentTypesNamespace = "http://schemas.openxmlformats.org/package/2006/content-types";

    public static IReadOnlyList<StructuredDataExportRow> Flatten(string structuredDataJson)
    {
        if (string.IsNullOrWhiteSpace(structuredDataJson))
            throw new ArgumentException("Structured data JSON is required.", nameof(structuredDataJson));

        using var document = JsonDocument.Parse(structuredDataJson);
        var rows = new List<StructuredDataExportRow>();
        FlattenElement(document.RootElement, string.Empty, rows);
        return rows;
    }

    public static byte[] ToCsv(IReadOnlyList<StructuredDataExportRow> rows)
    {
        using var stream = new MemoryStream();
        using (var writer = new StreamWriter(
                   stream,
                   new UTF8Encoding(encoderShouldEmitUTF8Identifier: true),
                   bufferSize: 1024,
                   leaveOpen: true))
        {
            writer.NewLine = "\r\n";
            writer.WriteLine("Path,Value");

            foreach (var row in rows)
            {
                writer.Write(EscapeCsv(row.Path));
                writer.Write(',');
                writer.Write(EscapeCsv(row.Value));
                writer.WriteLine();
            }
        }

        return stream.ToArray();
    }

    public static byte[] ToXlsx(IReadOnlyList<StructuredDataExportRow> rows)
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
                writer => WriteWorksheet(writer, rows));
        }

        return stream.ToArray();
    }

    private static void FlattenElement(
        JsonElement element,
        string path,
        ICollection<StructuredDataExportRow> rows)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var property in element
                             .EnumerateObject()
                             .OrderBy(x => x.Name, StringComparer.Ordinal))
                {
                    var childPath = string.IsNullOrEmpty(path)
                        ? property.Name
                        : $"{path}.{property.Name}";
                    FlattenElement(property.Value, childPath, rows);
                }
                break;

            case JsonValueKind.Array:
            {
                var index = 0;
                foreach (var item in element.EnumerateArray())
                {
                    var childPath = string.IsNullOrEmpty(path)
                        ? index.ToString(System.Globalization.CultureInfo.InvariantCulture)
                        : $"{path}.{index}";
                    FlattenElement(item, childPath, rows);
                    index++;
                }
                break;
            }

            case JsonValueKind.String:
                rows.Add(new StructuredDataExportRow(path, element.GetString() ?? string.Empty));
                break;

            case JsonValueKind.Number:
                rows.Add(new StructuredDataExportRow(path, element.GetRawText()));
                break;

            case JsonValueKind.True:
                rows.Add(new StructuredDataExportRow(path, "true"));
                break;

            case JsonValueKind.False:
                rows.Add(new StructuredDataExportRow(path, "false"));
                break;

            case JsonValueKind.Null:
            case JsonValueKind.Undefined:
                rows.Add(new StructuredDataExportRow(path, string.Empty));
                break;

            default:
                throw new InvalidOperationException($"Unsupported JSON value kind: {element.ValueKind}.");
        }
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

        writer.WriteStartElement("Default", ContentTypesNamespace);
        writer.WriteAttributeString("Extension", "rels");
        writer.WriteAttributeString("ContentType", "application/vnd.openxmlformats-package.relationships+xml");
        writer.WriteEndElement();

        writer.WriteStartElement("Default", ContentTypesNamespace);
        writer.WriteAttributeString("Extension", "xml");
        writer.WriteAttributeString("ContentType", "application/xml");
        writer.WriteEndElement();

        writer.WriteStartElement("Override", ContentTypesNamespace);
        writer.WriteAttributeString("PartName", "/xl/workbook.xml");
        writer.WriteAttributeString("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml");
        writer.WriteEndElement();

        writer.WriteStartElement("Override", ContentTypesNamespace);
        writer.WriteAttributeString("PartName", "/xl/worksheets/sheet1.xml");
        writer.WriteAttributeString("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml");
        writer.WriteEndElement();

        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WritePackageRelationships(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Relationships", PackageRelationshipsNamespace);
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", "rId1");
        writer.WriteAttributeString("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument");
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
        writer.WriteStartElement("sheet", SpreadsheetNamespace);
        writer.WriteAttributeString("name", "Extraction Result");
        writer.WriteAttributeString("sheetId", "1");
        writer.WriteAttributeString("r", "id", OfficeRelationshipsNamespace, "rId1");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorkbookRelationships(XmlWriter writer)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("Relationships", PackageRelationshipsNamespace);
        writer.WriteStartElement("Relationship", PackageRelationshipsNamespace);
        writer.WriteAttributeString("Id", "rId1");
        writer.WriteAttributeString("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet");
        writer.WriteAttributeString("Target", "worksheets/sheet1.xml");
        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteWorksheet(
        XmlWriter writer,
        IReadOnlyList<StructuredDataExportRow> rows)
    {
        writer.WriteStartDocument();
        writer.WriteStartElement("worksheet", SpreadsheetNamespace);

        writer.WriteStartElement("cols", SpreadsheetNamespace);
        WriteColumn(writer, min: 1, max: 1, width: 48);
        WriteColumn(writer, min: 2, max: 2, width: 64);
        writer.WriteEndElement();

        writer.WriteStartElement("sheetData", SpreadsheetNamespace);
        WriteWorksheetRow(writer, 1, "Path", "Value");

        var rowNumber = 2;
        foreach (var row in rows)
        {
            WriteWorksheetRow(writer, rowNumber, row.Path, row.Value);
            rowNumber++;
        }

        writer.WriteEndElement();
        writer.WriteEndElement();
        writer.WriteEndDocument();
    }

    private static void WriteColumn(XmlWriter writer, int min, int max, double width)
    {
        writer.WriteStartElement("col", SpreadsheetNamespace);
        writer.WriteAttributeString("min", min.ToString(System.Globalization.CultureInfo.InvariantCulture));
        writer.WriteAttributeString("max", max.ToString(System.Globalization.CultureInfo.InvariantCulture));
        writer.WriteAttributeString("width", width.ToString(System.Globalization.CultureInfo.InvariantCulture));
        writer.WriteAttributeString("customWidth", "1");
        writer.WriteEndElement();
    }

    private static void WriteWorksheetRow(
        XmlWriter writer,
        int rowNumber,
        string path,
        string value)
    {
        writer.WriteStartElement("row", SpreadsheetNamespace);
        writer.WriteAttributeString("r", rowNumber.ToString(System.Globalization.CultureInfo.InvariantCulture));
        WriteInlineStringCell(writer, $"A{rowNumber}", path);
        WriteInlineStringCell(writer, $"B{rowNumber}", value);
        writer.WriteEndElement();
    }

    private static void WriteInlineStringCell(XmlWriter writer, string reference, string value)
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
}
