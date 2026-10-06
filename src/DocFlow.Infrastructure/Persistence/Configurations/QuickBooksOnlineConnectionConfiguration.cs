using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class QuickBooksOnlineConnectionConfiguration
    : IEntityTypeConfiguration<QuickBooksOnlineConnection>
{
    public void Configure(EntityTypeBuilder<QuickBooksOnlineConnection> builder)
    {
        builder.ToTable("QuickBooksOnlineConnections");
        builder.HasKey(x => x.Id);

        builder.Property(x => x.TargetKey)
            .HasMaxLength(QuickBooksOnlineConnection.MaxTargetKeyLength)
            .IsRequired();

        builder.Property(x => x.RealmId)
            .HasMaxLength(QuickBooksOnlineConnection.MaxRealmIdLength)
            .IsRequired();

        builder.Property(x => x.ProtectedAccessToken)
            .HasMaxLength(QuickBooksOnlineConnection.MaxProtectedTokenLength)
            .IsRequired();

        builder.Property(x => x.ProtectedRefreshToken)
            .HasMaxLength(QuickBooksOnlineConnection.MaxProtectedTokenLength)
            .IsRequired();

        builder.HasIndex(x => new { x.CustomerId, x.TargetKey })
            .IsUnique()
            .HasDatabaseName("UX_QuickBooksOnlineConnections_TenantTarget");
    }
}
