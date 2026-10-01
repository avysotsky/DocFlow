using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class IntakeIdempotencyRecordConfiguration
    : IEntityTypeConfiguration<IntakeIdempotencyRecord>
{
    public void Configure(EntityTypeBuilder<IntakeIdempotencyRecord> builder)
    {
        builder.ToTable("IntakeIdempotencyRecords");

        builder.HasKey(x => new { x.CustomerId, x.Key });

        builder.Property(x => x.Key)
            .HasMaxLength(IntakeIdempotencyRecord.MaxKeyLength)
            .IsRequired();

        builder.Property(x => x.RequestFingerprint)
            .HasMaxLength(IntakeIdempotencyRecord.RequestFingerprintLength)
            .IsRequired();

        builder.Property(x => x.Outcome)
            .HasMaxLength(IntakeIdempotencyRecord.MaxOutcomeLength)
            .IsRequired();

        builder.Property(x => x.OriginalFileName)
            .HasMaxLength(IntakeIdempotencyRecord.MaxOriginalFileNameLength)
            .IsRequired();

        builder.Property(x => x.DocumentStatus)
            .HasMaxLength(IntakeIdempotencyRecord.MaxDocumentStatusLength);

        builder.Property(x => x.Error)
            .HasMaxLength(IntakeIdempotencyRecord.MaxErrorLength);

        builder.HasIndex(x => x.ExpiresAt);
    }
}
