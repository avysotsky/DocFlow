using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class DocumentConfiguration : IEntityTypeConfiguration<Document>
{
    public void Configure(EntityTypeBuilder<Document> builder)
    {
        builder.ToTable("Documents");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.OriginalFileName)
            .HasMaxLength(512)
            .IsRequired();

        builder.Property(x => x.ContentType)
            .HasMaxLength(100)
            .IsRequired();

        builder.Property(x => x.StorageKey)
            .HasMaxLength(1024)
            .IsRequired();

        builder.Property(x => x.DocumentType)
            .HasMaxLength(100);

        builder.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(32)
            .IsRequired();

        builder.Property(x => x.Size)
            .IsRequired();

        builder.Property(x => x.CreatedAt)
            .IsRequired();

        builder.Property(x => x.ProcessingAttempts)
            .IsRequired();

        builder.Property(x => x.LastProcessingError)
            .HasMaxLength(Document.MaxProcessingErrorLength);

        builder.HasIndex(x => x.StorageKey)
            .IsUnique();

        builder.HasIndex(x => new { x.CustomerId, x.CreatedAt });

        builder.HasIndex(x => x.Status);
    }
}
