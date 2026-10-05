namespace DocFlow.Domain.Entities;

public sealed class ReconciliationCaseAuditEvent
{
    public const int MaxActionLength = 32;
    public const int MaxStatusLength = 32;
    public const int MaxClientNameLength = 200;
    public const int MaxNoteLength = 2000;

    public Guid Id { get; private set; }
    public Guid ReconciliationCaseId { get; private set; }
    public string Action { get; private set; } = string.Empty;
    public string? PreviousStatus { get; private set; }
    public string NewStatus { get; private set; } = string.Empty;
    public string? Note { get; private set; }
    public string PerformedByClient { get; private set; } = string.Empty;
    public DateTimeOffset OccurredAt { get; private set; }

    private ReconciliationCaseAuditEvent()
    {
    }

    public ReconciliationCaseAuditEvent(
        Guid reconciliationCaseId,
        string action,
        string? previousStatus,
        string newStatus,
        string? note,
        string performedByClient)
    {
        if (reconciliationCaseId == Guid.Empty)
            throw new ArgumentException("Reconciliation case id is required.", nameof(reconciliationCaseId));
        if (string.IsNullOrWhiteSpace(action))
            throw new ArgumentException("Audit action is required.", nameof(action));
        if (string.IsNullOrWhiteSpace(newStatus))
            throw new ArgumentException("New review status is required.", nameof(newStatus));
        if (string.IsNullOrWhiteSpace(performedByClient))
            throw new ArgumentException("Client attribution is required.", nameof(performedByClient));

        var normalizedAction = action.Trim();
        var normalizedPrevious = string.IsNullOrWhiteSpace(previousStatus) ? null : previousStatus.Trim();
        var normalizedNew = newStatus.Trim();
        var normalizedNote = string.IsNullOrWhiteSpace(note) ? null : note.Trim();
        var normalizedClient = performedByClient.Trim();

        if (normalizedAction.Length > MaxActionLength)
            throw new ArgumentOutOfRangeException(nameof(action));
        if (normalizedPrevious?.Length > MaxStatusLength)
            throw new ArgumentOutOfRangeException(nameof(previousStatus));
        if (normalizedNew.Length > MaxStatusLength)
            throw new ArgumentOutOfRangeException(nameof(newStatus));
        if (normalizedNote?.Length > MaxNoteLength)
            throw new ArgumentOutOfRangeException(nameof(note));
        if (normalizedClient.Length > MaxClientNameLength)
            throw new ArgumentOutOfRangeException(nameof(performedByClient));

        Id = Guid.NewGuid();
        ReconciliationCaseId = reconciliationCaseId;
        Action = normalizedAction;
        PreviousStatus = normalizedPrevious;
        NewStatus = normalizedNew;
        Note = normalizedNote;
        PerformedByClient = normalizedClient;
        OccurredAt = DateTimeOffset.UtcNow;
    }
}
