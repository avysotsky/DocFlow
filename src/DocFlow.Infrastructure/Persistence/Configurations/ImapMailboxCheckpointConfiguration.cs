using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class ImapMailboxCheckpointConfiguration
    : IEntityTypeConfiguration<ImapMailboxCheckpoint>
{
    public void Configure(EntityTypeBuilder<ImapMailboxCheckpoint> builder)
    {
        builder.ToTable("ImapMailboxCheckpoints");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.MailboxKey)
            .HasMaxLength(ImapMailboxCheckpoint.MaxMailboxKeyLength)
            .IsRequired();

        builder.Property(x => x.FolderName)
            .HasMaxLength(ImapMailboxCheckpoint.MaxFolderNameLength)
            .IsRequired();

        builder.Property(x => x.UpdatedAt)
            .IsRequired();

        builder.HasIndex(x => new { x.CustomerId, x.MailboxKey, x.FolderName })
            .IsUnique();
    }
}
