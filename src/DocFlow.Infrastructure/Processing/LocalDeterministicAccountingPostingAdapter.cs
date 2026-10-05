using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Processing;

public sealed class LocalDeterministicAccountingPostingAdapter
    : IAccountingPostingAdapter
{
    public const string ProviderName = "local-test";

    public string Provider => ProviderName;

    public Task<AccountingPostingAdapterResult> PostAsync(
        AccountingPostingRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        var externalReference = $"local-posting:{request.PostingId:N}";
        return Task.FromResult(
            new AccountingPostingAdapterResult(
                AccountingPostingAdapterOutcome.Posted,
                externalReference));
    }
}
