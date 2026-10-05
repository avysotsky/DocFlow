using System.Security.Cryptography;
using System.Text;
using DocFlow.Infrastructure.Mailbox;

namespace DocFlow.Infrastructure.Tests;

public sealed class MimeMailboxMessageParserTests
{
    [Fact]
    public async Task ParseAsync_ExtractsOnlyValidatedPdfAttachmentsAndMetadata()
    {
        var pdf = Encoding.ASCII.GetBytes("%PDF-1.4\nminimal-test-pdf\n%%EOF");
        var raw = BuildMultipartMessage(
            "<Invoice-123@Example.COM>",
            pdf,
            "application/octet-stream",
            "../../invoice.pdf",
            includeTextAttachment: true);

        var parser = new MimeMailboxMessageParser();
        await using var stream = new MemoryStream(raw);

        var result = await parser.ParseAsync(stream);

        Assert.Equal("message-id:invoice-123@example.com", result.MessageIdentity);
        Assert.Equal("Invoice-123@Example.COM", result.InternetMessageId);
        Assert.Equal("billing@example.com", result.Sender);
        Assert.Equal("October invoice", result.Subject);
        Assert.NotNull(result.ReceivedAt);

        var attachment = Assert.Single(result.PdfAttachments);
        Assert.Equal(0, attachment.Ordinal);
        Assert.Equal("invoice.pdf", attachment.FileName);
        Assert.Equal("application/pdf", attachment.ContentType);
        Assert.Equal(pdf.LongLength, attachment.Size);
        Assert.Equal(
            Convert.ToHexString(SHA256.HashData(pdf)).ToLowerInvariant(),
            attachment.Sha256);
        Assert.Equal(pdf, attachment.Content);
    }

    [Fact]
    public async Task ParseAsync_WithoutMessageId_UsesRawSha256Identity()
    {
        var pdf = Encoding.ASCII.GetBytes("%PDF-1.7\nfallback-identity\n%%EOF");
        var raw = BuildMultipartMessage(
            null,
            pdf,
            "application/pdf",
            "invoice.pdf",
            includeTextAttachment: false);

        var expectedHash = Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant();
        var parser = new MimeMailboxMessageParser();

        await using var stream = new MemoryStream(raw);
        var result = await parser.ParseAsync(stream);

        Assert.Null(result.InternetMessageId);
        Assert.Equal($"sha256:{expectedHash}", result.MessageIdentity);
        Assert.Equal(expectedHash, result.RawMessageSha256);
        Assert.Single(result.PdfAttachments);
    }

    [Fact]
    public async Task ParseAsync_PdfNamedAttachmentWithInvalidSignature_IsRejected()
    {
        var raw = BuildMultipartMessage(
            "<bad-pdf@example.com>",
            Encoding.UTF8.GetBytes("this is not a pdf"),
            "application/octet-stream",
            "fake.pdf",
            includeTextAttachment: false);

        var parser = new MimeMailboxMessageParser();
        await using var stream = new MemoryStream(raw);

        var exception = await Assert.ThrowsAsync<InvalidDataException>(
            () => parser.ParseAsync(stream));

        Assert.Contains("valid PDF signature", exception.Message);
    }

    [Fact]
    public async Task ParseAsync_NonPdfAttachments_AreIgnored()
    {
        var rawText = """
From: Billing <billing@example.com>
To: ap@example.com
Date: Sun, 05 Oct 2026 14:00:00 +0300
Message-ID: <text-only@example.com>
Subject: No invoice
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="docflow-boundary"

--docflow-boundary
Content-Type: text/plain; charset=utf-8

Hello.
--docflow-boundary
Content-Type: text/csv
Content-Disposition: attachment; filename="data.csv"
Content-Transfer-Encoding: base64

YSxiCjEsMgo=
--docflow-boundary--
""";
        var parser = new MimeMailboxMessageParser();
        await using var stream = new MemoryStream(Encoding.UTF8.GetBytes(rawText));

        var result = await parser.ParseAsync(stream);

        Assert.Empty(result.PdfAttachments);
    }

    private static byte[] BuildMultipartMessage(
        string? messageId,
        byte[] pdf,
        string pdfContentType,
        string fileName,
        bool includeTextAttachment)
    {
        var messageIdHeader = messageId is null ? string.Empty : $"Message-ID: {messageId}\n";
        var extraAttachment = includeTextAttachment
            ? """
--docflow-boundary
Content-Type: text/plain
Content-Disposition: attachment; filename="notes.txt"
Content-Transfer-Encoding: base64

bm90ZXM=
"""
            : string.Empty;

        var raw = $"""
From: Billing <billing@example.com>
To: ap@example.com
Date: Sun, 05 Oct 2026 14:00:00 +0300
{messageIdHeader}Subject: October invoice
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="docflow-boundary"

--docflow-boundary
Content-Type: text/plain; charset=utf-8

Please process the attached invoice.
{extraAttachment}--docflow-boundary
Content-Type: {pdfContentType}; name="{fileName}"
Content-Disposition: attachment; filename="{fileName}"
Content-Transfer-Encoding: base64

{Convert.ToBase64String(pdf)}
--docflow-boundary--
""";

        return Encoding.UTF8.GetBytes(raw);
    }
}
