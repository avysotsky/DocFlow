using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class MailboxAttachmentRecordConfiguration
    : IEntityTypeConfiguration<MailboxAttachmentRecord>
{
    public void Configure(EntityTypeBuilder<MailboxAttachmentRecord> builder)
    {
        builder.ToTable("MailboxAttachments");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.FileName)
            .HasMaxLength(MailboxAttachmentRecord.MaxFileNameLength)
            .IsRequired();

        builder.Property(x => x.ContentType)
            .HasMaxLength(MailboxAttachmentRecord.MaxContentTypeLength)
            .IsRequired();

        builder.Property(x => x.Sha256)
            .HasMaxLength(MailboxAttachmentRecord.Sha256Length)
            .IsRequired();

        builder.Property(x => x.CreatedAt)
            .IsRequired();

        builder.HasOne<MailboxMessageRecord>()
            .WithMany()
            .HasForeignKey(x => x.MailboxMessageId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasIndex(x => new { x.MailboxMessageId, x.Ordinal })
            .IsUnique();
    }
}
