using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class DocumentCompletionEventConfiguration
    : IEntityTypeConfiguration<DocumentCompletionEvent>
{
    public void Configure(EntityTypeBuilder<DocumentCompletionEvent> builder)
    {
        builder.ToTable("DocumentCompletionOutbox");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(32)
            .IsRequired();

        builder.Property(x => x.DocumentType)
            .HasMaxLength(100);

        builder.Property(x => x.ProcessingAttempts)
            .IsRequired();

        builder.Property(x => x.OccurredAt)
            .IsRequired();

        builder.HasIndex(x => new { x.DocumentId, x.Status, x.ProcessingAttempts })
            .IsUnique();

        builder.HasIndex(x => new { x.CustomerId, x.OccurredAt });

        // Intentionally no foreign key to Documents. Completion events must survive
        // explicit document deletion/retention until a future delivery policy handles them.
    }
}
