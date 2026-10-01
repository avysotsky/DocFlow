using DocFlow.Api.Authentication;
using DocFlow.Api.BackgroundServices;
using DocFlow.Application.Abstractions;
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
    .AddAuthentication(ApiKeyAuthenticationDefaults.Scheme)
    .AddScheme<AuthenticationSchemeOptions, ApiKeyAuthenticationHandler>(
        ApiKeyAuthenticationDefaults.Scheme,
        _ => { });
builder.Services.AddAuthorization();

var connectionString = builder.Configuration.GetConnectionString("DocFlowDbContext")
    ?? throw new InvalidOperationException("Connection string 'DocFlowDbContext' was not found.");

builder.Services.AddDbContext<DocFlowDbContext>(options =>
    options.UseNpgsql(connectionString));

builder.Services.AddScoped<IExtractionResultService, ExtractionResultService>();
builder.Services.AddScoped<IExtractionResultExportService, ExtractionResultExportService>();
builder.Services.AddScoped<IDocumentReviewService, DocumentReviewService>();
builder.Services.AddScoped<IDocumentProcessingService, DocumentProcessingService>();
builder.Services.AddSingleton<IDocumentProcessingQueue, DocumentProcessingQueue>();
builder.Services.AddHostedService<DocumentProcessingBackgroundService>();

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
