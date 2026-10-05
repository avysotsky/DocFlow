using DocFlow.Domain.Entities;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Persistence;

public sealed class DocFlowDbContext : DbContext
{
    public DocFlowDbContext(DbContextOptions<DocFlowDbContext> options)
        : base(options)
    {
    }

    public DbSet<Document> Documents => Set<Document>();
    public DbSet<ExtractionResult> ExtractionResults => Set<ExtractionResult>();
    public DbSet<DocumentReview> DocumentReviews => Set<DocumentReview>();
    public DbSet<IntakeIdempotencyRecord> IntakeIdempotencyRecords => Set<IntakeIdempotencyRecord>();
    public DbSet<BatchIntakeIdempotencyRecord> BatchIntakeIdempotencyRecords => Set<BatchIntakeIdempotencyRecord>();
    public DbSet<DocumentCompletionEvent> DocumentCompletionEvents => Set<DocumentCompletionEvent>();
    public DbSet<ReconciliationCase> ReconciliationCases => Set<ReconciliationCase>();
    public DbSet<ReconciliationCaseAuditEvent> ReconciliationCaseAuditEvents => Set<ReconciliationCaseAuditEvent>();
    public DbSet<MailboxMessageRecord> MailboxMessages => Set<MailboxMessageRecord>();
    public DbSet<MailboxAttachmentRecord> MailboxAttachments => Set<MailboxAttachmentRecord>();
    public DbSet<ImapMailboxCheckpoint> ImapMailboxCheckpoints => Set<ImapMailboxCheckpoint>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.ApplyConfigurationsFromAssembly(typeof(DocFlowDbContext).Assembly);
    }
}
