namespace DocFlow.Application.Abstractions;

public enum AccountingBillPayloadBuildOutcome
{
    Completed,
    InvalidJson,
    MissingRequiredField
}

public sealed record AccountingBillPayloadBuildResult(
    AccountingBillPayloadBuildOutcome Outcome,
    AccountingBillPayload? Payload = null,
    string? Error = null);

public interface IAccountingBillPayloadFactory
{
    AccountingBillPayloadBuildResult Build(string structuredDataJson);
}
