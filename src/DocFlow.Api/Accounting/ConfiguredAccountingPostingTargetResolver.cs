using DocFlow.Application.Abstractions;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Accounting;

public sealed class ConfiguredAccountingPostingTargetResolver
    : IAccountingPostingTargetResolver
{
    private readonly IReadOnlyDictionary<string, AccountingPostingTarget> _targets;

    public ConfiguredAccountingPostingTargetResolver(
        IOptions<AccountingPostingTargetsOptions> options)
    {
        _targets = options.Value.Targets.ToDictionary(
            target => ComposeKey(target.CustomerId, target.Key),
            target => new AccountingPostingTarget(
                target.Key.Trim(),
                target.Provider.Trim().ToLowerInvariant(),
                target.TargetAccount.Trim()),
            StringComparer.OrdinalIgnoreCase);
    }

    public AccountingPostingTarget? Resolve(
        Guid customerId,
        string targetKey)
    {
        if (customerId == Guid.Empty || string.IsNullOrWhiteSpace(targetKey))
            return null;

        return _targets.TryGetValue(
            ComposeKey(customerId, targetKey),
            out var target)
            ? target
            : null;
    }

    private static string ComposeKey(Guid customerId, string targetKey)
        => $"{customerId:N}:{targetKey.Trim()}";
}
