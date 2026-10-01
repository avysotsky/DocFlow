using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class BatchIntakeIdempotencyRecordConfiguration
    : IEntityTypeConfiguration<BatchIntakeIdempotencyRecord>
{
    public void Configure(EntityTypeBuilder<BatchIntakeIdempotencyRecord> builder)
    {
        builder.ToTable("BatchIntakeIdempotencyRecords");

        builder.HasKey(x => new { x.CustomerId, x.Key });

        builder.Property(x => x.Key)
            .HasMaxLength(BatchIntakeIdempotencyRecord.MaxKeyLength)
            .IsRequired();

        builder.Property(x => x.RequestFingerprint)
            .HasMaxLength(BatchIntakeIdempotencyRecord.RequestFingerprintLength)
            .IsRequired();

        builder.Property(x => x.ResponseJson)
            .HasColumnType("jsonb");

        builder.HasIndex(x => x.ExpiresAt);
    }
}
