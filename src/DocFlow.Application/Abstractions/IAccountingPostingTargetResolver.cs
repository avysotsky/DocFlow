namespace DocFlow.Application.Abstractions;

public sealed record AccountingPostingTarget(
    string Key,
    string Provider,
    string TargetAccount);

public interface IAccountingPostingTargetResolver
{
    AccountingPostingTarget? Resolve(Guid customerId, string targetKey);
}
