using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class ReconciliationCaseConfiguration : IEntityTypeConfiguration<ReconciliationCase>
{
    public void Configure(EntityTypeBuilder<ReconciliationCase> builder)
    {
        builder.ToTable("ReconciliationCases");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.ReconciliationStatus)
            .HasMaxLength(ReconciliationCase.MaxStatusLength)
            .IsRequired();

        builder.Property(x => x.ReviewStatus)
            .HasMaxLength(ReconciliationCase.MaxStatusLength)
            .IsRequired();

        builder.Property(x => x.ReportJson)
            .HasColumnType("jsonb")
            .IsRequired();

        builder.Property(x => x.CreatedAt)
            .IsRequired();

        builder.Property(x => x.UpdatedAt)
            .IsRequired();

        builder.Property(x => x.CreatedByClient)
            .HasMaxLength(ReconciliationCase.MaxClientNameLength)
            .IsRequired();

        builder.HasOne<Document>()
            .WithMany()
            .HasForeignKey(x => x.InvoiceDocumentId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasOne<Document>()
            .WithMany()
            .HasForeignKey(x => x.PurchaseOrderDocumentId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasIndex(x => new { x.CustomerId, x.CreatedAt });
        builder.HasIndex(x => x.InvoiceDocumentId);
        builder.HasIndex(x => x.PurchaseOrderDocumentId);
    }
}
