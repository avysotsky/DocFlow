using DocFlow.Domain.Entities;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class MailboxAttachmentRecordTests
{
    [Fact]
    public void AttachDocument_IsIdempotentButCannotBeRepointed()
    {
        var attachment = new MailboxAttachmentRecord(
            Guid.NewGuid(),
            0,
            "invoice.pdf",
            "application/pdf",
            123,
            new string('a', 64));

        var documentId = Guid.NewGuid();
        attachment.AttachDocument(documentId);
        attachment.AttachDocument(documentId);

        Assert.Equal(documentId, attachment.DocumentId);

        var exception = Assert.Throws<InvalidOperationException>(
            () => attachment.AttachDocument(Guid.NewGuid()));

        Assert.Contains("already linked", exception.Message);
    }
}
