namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public interface IQuickBooksOnlineAccessTokenProvider
{
    Task<string?> GetAccessTokenAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default);
}
