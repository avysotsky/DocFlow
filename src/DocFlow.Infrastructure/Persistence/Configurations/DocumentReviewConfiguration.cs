using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class DocumentReviewConfiguration : IEntityTypeConfiguration<DocumentReview>
{
    public void Configure(EntityTypeBuilder<DocumentReview> builder)
    {
        builder.ToTable("DocumentReviews");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.CorrectedDataJson)
            .HasColumnType("jsonb")
            .IsRequired();

        builder.Property(x => x.Note)
            .HasMaxLength(2000);

        builder.Property(x => x.ReviewedAt)
            .IsRequired();

        builder.Property(x => x.ReviewedByClient)
            .HasMaxLength(DocumentReview.MaxReviewedByClientLength);

        builder.HasOne<Document>()
            .WithOne()
            .HasForeignKey<DocumentReview>(x => x.DocumentId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasIndex(x => x.DocumentId)
            .IsUnique();

        builder.HasIndex(x => x.ExtractionResultId)
            .IsUnique();
    }
}
