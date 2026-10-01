using DocFlow.Api.Authentication;
using DocFlow.Api.BackgroundServices;
using DocFlow.Api.Documents;
using DocFlow.Api.Observability;
using DocFlow.Api.Retention;
using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using DocFlow.Infrastructure.Documents;
using DocFlow.Infrastructure.Export;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using DocFlow.Infrastructure.Storage;
using Microsoft.AspNetCore.Authentication;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var apiKeyOptions = builder.Services
    .AddOptions<ApiKeyAuthenticationOptions>()
    .Bind(builder.Configuration.GetSection(ApiKeyAuthenticationDefaults.ConfigurationSection));

if (!builder.Environment.IsDevelopment())
{
    apiKeyOptions
        .Validate(
            options => options.Clients.Count > 0,
            "At least one API-key client must be configured outside Development.")
        .Validate(
            options => options.Clients.All(client =>
                client.CustomerId != Guid.Empty && !string.IsNullOrWhiteSpace(client.ApiKey)),
            "Every API-key client must have a non-empty CustomerId and ApiKey.")
        .Validate(
            options => options.Clients
                .Select(client => client.ApiKey)
                .Distinct(StringComparer.Ordinal)
                .Count() == options.Clients.Count,
            "API keys must be unique.")
        .ValidateOnStart();
}

builder.Services
    .AddOptions<DocumentProcessingRetryOptions>()
    .Bind(builder.Configuration.GetSection(DocumentProcessingRetryOptions.ConfigurationSection))
    .Validate(
        options => options.MaxAttempts is >= 1 and <= 10,
        "Processing retry MaxAttempts must be between 1 and 10.")
    .Validate(
        options => options.RetryDelayMilliseconds is >= 0 and <= 60000,
        "Processing retry RetryDelayMilliseconds must be between 0 and 60000.")
    .ValidateOnStart();

builder.Services
    .AddOptions<DocumentRetentionOptions>()
    .Bind(builder.Configuration.GetSection(DocumentRetentionOptions.ConfigurationSection))
    .Validate(
        options => options.DefaultRetentionDays is >= 1 and <= 3650,
        "Retention DefaultRetentionDays must be between 1 and 3650.")
    .Validate(
        options => options.SweepIntervalSeconds is >= 1 and <= 86400,
        "Retention SweepIntervalSeconds must be between 1 and 86400.")
    .Validate(
        options => options.BatchSize is >= 1 and <= 1000,
        "Retention BatchSize must be between 1 and 1000.")
    .ValidateOnStart();

builder.Services
    .AddOptions<OperationalMetricsOptions>()
    .Bind(builder.Configuration.GetSection(OperationalMetricsOptions.ConfigurationSection))
    .Validate(
        options => !options.Enabled || !string.IsNullOrWhiteSpace(options.ApiKey),
        "Operations metrics ApiKey is required when metrics are enabled.")
    .Validate(
        options => !options.Enabled || options.ApiKey.Length <= 512,
        "Operations metrics ApiKey must not exceed 512 characters.")
    .ValidateOnStart();

builder.Services
    .AddAuthentication(ApiKeyAuthenticationDefaults.Scheme)
    .AddScheme<AuthenticationSchemeOptions, ApiKeyAuthenticationHandler>(
        ApiKeyAuthenticationDefaults.Scheme,
        _ => { });
builder.Services.AddAuthorization();

var connectionString = builder.Configuration.GetConnectionString("DocFlowDbContext")
    ?? throw new InvalidOperationException("Connection string 'DocFlowDbContext' was not found.");

builder.Services.AddDbContext<DocFlowDbContext>(options =>
    options.UseNpgsql(connectionString));

builder.Services.AddSingleton<OperationalMetrics>();
builder.Services.AddScoped<DocumentIntakeService>();
builder.Services.AddScoped<IExtractionResultService, ExtractionResultService>();
builder.Services.AddScoped<IExtractionResultExportService, ExtractionResultExportService>();
builder.Services.AddScoped<IDocumentReviewService, DocumentReviewService>();
builder.Services.AddScoped<IDocumentDeletionService, DocumentDeletionService>();
builder.Services.AddScoped<IDocumentProcessingService, DocumentProcessingService>();
builder.Services.AddSingleton<IDocumentProcessingQueue, DocumentProcessingQueue>();

// Hosted services start in registration order. Recovery enqueues persisted orphaned work
// before the normal single-reader queue consumer begins processing. Retention runs after
// processing startup and only considers terminal documents.
builder.Services.AddHostedService<DocumentProcessingRecoveryHostedService>();
builder.Services.AddHostedService<DocumentProcessingBackgroundService>();
builder.Services.AddHostedService<DocumentRetentionHostedService>();

var storageRoot = builder.Configuration["FileStorage:RootPath"] ?? "storage";
if (!Path.IsPathRooted(storageRoot))
    storageRoot = Path.Combine(builder.Environment.ContentRootPath, storageRoot);

builder.Services.AddSingleton<IFileStorage>(new LocalFileStorage(storageRoot));

var workerRoot = builder.Configuration["ExtractionWorker:RootPath"]
    ?? "../DocFlow.Extraction.Worker";
if (!Path.IsPathRooted(workerRoot))
    workerRoot = Path.Combine(builder.Environment.ContentRootPath, workerRoot);

var pythonExecutable = builder.Configuration["ExtractionWorker:PythonExecutable"];

builder.Services.AddSingleton<IDocumentExtractionRunner>(
    new PythonDocumentExtractionRunner(
        workerRoot,
        storageRoot,
        pythonExecutable));

var app = builder.Build();

if (builder.Configuration.GetValue<bool>("Database:ApplyMigrationsOnStartup"))
{
    await using var scope = app.Services.CreateAsyncScope();
    var dbContext = scope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
    await dbContext.Database.MigrateAsync();
}

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

app.Run();
