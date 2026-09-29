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
}
