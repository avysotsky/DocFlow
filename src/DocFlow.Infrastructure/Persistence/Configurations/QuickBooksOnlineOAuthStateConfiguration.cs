using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace DocFlow.Infrastructure.Persistence.Configurations;

public sealed class QuickBooksOnlineOAuthStateConfiguration
    : IEntityTypeConfiguration<QuickBooksOnlineOAuthState>
{
    public void Configure(EntityTypeBuilder<QuickBooksOnlineOAuthState> builder)
    {
        builder.ToTable("QuickBooksOnlineOAuthStates");
        builder.HasKey(x => x.Id);

        builder.Property(x => x.TargetKey)
            .HasMaxLength(QuickBooksOnlineOAuthState.MaxTargetKeyLength)
            .IsRequired();

        builder.Property(x => x.StateHash)
            .HasMaxLength(QuickBooksOnlineOAuthState.MaxStateHashLength)
            .IsRequired();

        builder.HasIndex(x => x.StateHash)
            .IsUnique()
            .HasDatabaseName("UX_QuickBooksOnlineOAuthStates_StateHash");

        builder.HasIndex(x => x.ExpiresAt);
    }
}
