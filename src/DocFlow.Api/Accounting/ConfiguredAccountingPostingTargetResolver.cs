using DocFlow.Application.Abstractions;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Accounting;

public sealed class ConfiguredAccountingPostingTargetResolver
    : IAccountingPostingTargetResolver
{
    private readonly IReadOnlyDictionary<string, AccountingPostingTarget> _targets;
    private readonly IReadOnlyDictionary<Guid, AccountingPostingTarget[]> _targetsByCustomer;

    public ConfiguredAccountingPostingTargetResolver(
        IOptions<AccountingPostingTargetsOptions> options)
    {
        var configuredTargets = options.Value.Targets
            .Select(target => new
            {
                target.CustomerId,
                Target = new AccountingPostingTarget(
                    target.Key.Trim(),
                    target.Provider.Trim().ToLowerInvariant(),
                    target.TargetAccount.Trim())
            })
            .ToArray();

        _targets = configuredTargets.ToDictionary(
            item => ComposeKey(item.CustomerId, item.Target.Key),
            item => item.Target,
            StringComparer.OrdinalIgnoreCase);

        _targetsByCustomer = configuredTargets
            .GroupBy(item => item.CustomerId)
            .ToDictionary(
                group => group.Key,
                group => group
                    .Select(item => item.Target)
                    .OrderBy(item => item.Key, StringComparer.OrdinalIgnoreCase)
                    .ToArray());
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

    public IReadOnlyList<AccountingPostingTarget> GetAvailable(Guid customerId)
        => _targetsByCustomer.TryGetValue(customerId, out var targets)
            ? targets
            : [];

    private static string ComposeKey(Guid customerId, string targetKey)
        => $"{customerId:N}:{targetKey.Trim()}";
}
