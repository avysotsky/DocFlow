using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class MailboxMessageRecordConfiguration
    : IEntityTypeConfiguration<MailboxMessageRecord>
{
    public void Configure(EntityTypeBuilder<MailboxMessageRecord> builder)
    {
        builder.ToTable("MailboxMessages");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.MessageIdentity)
            .HasMaxLength(MailboxMessageRecord.MaxIdentityLength)
            .IsRequired();

        builder.Property(x => x.RawMessageSha256)
            .HasMaxLength(MailboxMessageRecord.Sha256Length)
            .IsRequired();

        builder.Property(x => x.InternetMessageId)
            .HasMaxLength(MailboxMessageRecord.MaxInternetMessageIdLength);

        builder.Property(x => x.Sender)
            .HasMaxLength(MailboxMessageRecord.MaxSenderLength);

        builder.Property(x => x.Subject)
            .HasMaxLength(MailboxMessageRecord.MaxSubjectLength);

        builder.Property(x => x.CreatedAt)
            .IsRequired();

        builder.HasIndex(x => new { x.CustomerId, x.MessageIdentity })
            .IsUnique();

        builder.HasIndex(x => new { x.CustomerId, x.CreatedAt });
    }
}
