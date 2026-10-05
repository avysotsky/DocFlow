using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class AccountingPostingRecordConfiguration
    : IEntityTypeConfiguration<AccountingPostingRecord>
{
    public void Configure(EntityTypeBuilder<AccountingPostingRecord> builder)
    {
        builder.ToTable("AccountingPostingRecords");

        builder.HasKey(x => x.Id);

        builder.Property(x => x.Provider)
            .HasMaxLength(AccountingPostingRecord.MaxProviderLength)
            .IsRequired();

        builder.Property(x => x.TargetAccount)
            .HasMaxLength(AccountingPostingRecord.MaxTargetAccountLength)
            .IsRequired();

        builder.Property(x => x.IdempotencyKey)
            .HasMaxLength(AccountingPostingRecord.MaxIdempotencyKeyLength)
            .IsRequired();

        builder.Property(x => x.PayloadJson)
            .HasColumnType("jsonb")
            .IsRequired();

        builder.Property(x => x.Status)
            .HasConversion<string>()
            .HasMaxLength(32)
            .IsRequired();

        builder.Property(x => x.ExternalReference)
            .HasMaxLength(AccountingPostingRecord.MaxExternalReferenceLength);

        builder.Property(x => x.LastError)
            .HasMaxLength(AccountingPostingRecord.MaxErrorLength);

        builder.HasIndex(x => new
            {
                x.CustomerId,
                x.Provider,
                x.TargetAccount,
                x.IdempotencyKey
            })
            .IsUnique()
            .HasDatabaseName("UX_AccountingPostingRecords_Idempotency");

        builder.HasIndex(x => x.DocumentId);
        builder.HasIndex(x => x.NextAttemptAt);

        // Intentionally no FK to Documents. A successful or failed accounting posting
        // is an integration audit record and must survive source-document deletion.
    }
}
