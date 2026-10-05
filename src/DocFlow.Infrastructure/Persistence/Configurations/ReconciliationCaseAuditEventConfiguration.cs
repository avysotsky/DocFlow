using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class ReconciliationCaseAuditEventConfiguration
    : IEntityTypeConfiguration<ReconciliationCaseAuditEvent>
{
    public void Configure(EntityTypeBuilder<ReconciliationCaseAuditEvent> builder)
    {
        builder.ToTable("ReconciliationCaseAuditEvents");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.Action)
            .HasMaxLength(ReconciliationCaseAuditEvent.MaxActionLength)
            .IsRequired();

        builder.Property(x => x.PreviousStatus)
            .HasMaxLength(ReconciliationCaseAuditEvent.MaxStatusLength);

        builder.Property(x => x.NewStatus)
            .HasMaxLength(ReconciliationCaseAuditEvent.MaxStatusLength)
            .IsRequired();

        builder.Property(x => x.Note)
            .HasMaxLength(ReconciliationCaseAuditEvent.MaxNoteLength);

        builder.Property(x => x.PerformedByClient)
            .HasMaxLength(ReconciliationCaseAuditEvent.MaxClientNameLength)
            .IsRequired();

        builder.Property(x => x.OccurredAt)
            .IsRequired();

        builder.HasOne<ReconciliationCase>()
            .WithMany()
            .HasForeignKey(x => x.ReconciliationCaseId)
            .OnDelete(DeleteBehavior.Cascade);

        builder.HasIndex(x => new { x.ReconciliationCaseId, x.OccurredAt });
    }
}
