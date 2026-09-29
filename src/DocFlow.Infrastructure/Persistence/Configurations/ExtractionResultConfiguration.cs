using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class ExtractionResultConfiguration : IEntityTypeConfiguration<ExtractionResult>
{
    public void Configure(EntityTypeBuilder<ExtractionResult> builder)
    {
        builder.ToTable("ExtractionResults");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.StructuredDataJson)
            .HasColumnType("jsonb")
            .IsRequired();

        builder.Property(x => x.Confidence)
            .HasPrecision(5, 4);

        builder.Property(x => x.ValidationStatus)
            .HasConversion<string>()
            .HasMaxLength(32)
            .IsRequired();

        builder.Property(x => x.CreatedAt)
            .IsRequired();

        builder.HasOne<Document>()
            .WithOne()
            .HasForeignKey<ExtractionResult>(x => x.DocumentId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasIndex(x => x.DocumentId)
            .IsUnique();
    }
}
