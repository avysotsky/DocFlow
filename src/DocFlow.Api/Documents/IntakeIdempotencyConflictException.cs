namespace DocFlow.Api.Documents;

public sealed class IntakeIdempotencyConflictException : Exception
{
    public IntakeIdempotencyConflictException(string message)
        : base(message)
    {
    }
}
