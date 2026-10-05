using DocFlow.Api.Authentication;
using DocFlow.Api.BackgroundServices;
using DocFlow.Api.Documents;
using DocFlow.Api.Middleware;
using DocFlow.Api.Observability;
using DocFlow.Api.Notifications;
using DocFlow.Api.OpenApi;
using DocFlow.Api.Retention;
using DocFlow.Application.Abstractions;
using DocFlow.Application.Observability;
using DocFlow.Infrastructure.Documents;
using DocFlow.Infrastructure.Export;
using DocFlow.Infrastructure.Mailbox;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using DocFlow.Infrastructure.Storage;
using Microsoft.AspNetCore.Authentication;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(options =>
    options.SchemaFilter<DocumentContractSchemaFilter>());
builder.Services.AddHttpContextAccessor();

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
    .Validate(
        options => options.TenantOverrides.All(tenant => tenant.CustomerId != Guid.Empty),
        "Every retention tenant override must have a non-empty CustomerId.")
    .Validate(
        options => options.TenantOverrides
            .Select(tenant => tenant.CustomerId)
            .Distinct()
            .Count() == options.TenantOverrides.Count,
        "Retention tenant override CustomerIds must be unique.")
    .Validate(
        options => options.TenantOverrides.All(tenant =>
            tenant.RetentionDays is null or >= 1 and <= 3650),
        "Retention tenant override RetentionDays must be null or between 1 and 3650.")
    .Validate(
        options => options.TenantOverrides.All(tenant =>
            tenant.Enabled.HasValue || tenant.RetentionDays.HasValue),
        "Every retention tenant override must override Enabled, RetentionDays, or both.")
    .ValidateOnStart();

builder.Services
    .AddOptions<DocumentIntakeIdempotencyOptions>()
    .Bind(builder.Configuration.GetSection(DocumentIntakeIdempotencyOptions.ConfigurationSection))
    .Validate(
        options => options.RetentionHours is >= 1 and <= 720,
        "Intake idempotency RetentionHours must be between 1 and 720.")
    .Validate(
        options => options.CleanupIntervalSeconds is >= 1 and <= 86400,
        "Intake idempotency CleanupIntervalSeconds must be between 1 and 86400.")
    .Validate(
        options => options.CleanupBatchSize is >= 1 and <= 5000,
        "Intake idempotency CleanupBatchSize must be between 1 and 5000.")
    .ValidateOnStart();

builder.Services
    .AddOptions<ImapMailboxPollingOptions>()
    .Bind(builder.Configuration.GetSection(ImapMailboxPollingOptions.ConfigurationSection))
    .Validate(
        options => options.PollIntervalSeconds is >= 1 and <= 3600,
        "Mailbox IMAP PollIntervalSeconds must be between 1 and 3600.")
    .Validate(
        options => options.BatchSize is >= 1 and <= 500,
        "Mailbox IMAP BatchSize must be between 1 and 500.")
    .Validate(
        options => !options.Enabled || options.Accounts.Count > 0,
        "At least one IMAP account is required when mailbox polling is enabled.")
    .Validate(
        options => !options.Enabled || options.Accounts.All(account =>
            !string.IsNullOrWhiteSpace(account.Name)
            && account.Name.Length <= 100
            && account.CustomerId != Guid.Empty
            && !string.IsNullOrWhiteSpace(account.Host)
            && account.Port is >= 1 and <= 65535
            && !string.IsNullOrWhiteSpace(account.Username)
            && !string.IsNullOrWhiteSpace(account.Password)
            && !string.IsNullOrWhiteSpace(account.Folder)
            && account.Folder.Length <= 255),
        "Every enabled IMAP account must have valid name, customer, endpoint, credentials and folder.")
    .Validate(
        options => !options.Enabled
            || options.Accounts
                .Select(account => (account.CustomerId, Name: account.Name.Trim(), Folder: account.Folder.Trim()))
                .Distinct()
                .Count() == options.Accounts.Count,
        "IMAP account CustomerId/Name/Folder combinations must be unique.")
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

var webhookOptions = builder.Services
    .AddOptions<WebhookDeliveryOptions>()
    .Bind(builder.Configuration.GetSection(WebhookDeliveryOptions.ConfigurationSection))
    .Validate(options => options.PollIntervalSeconds is >= 1 and <= 3600, "Webhook PollIntervalSeconds must be between 1 and 3600.")
    .Validate(options => options.RequestTimeoutSeconds is >= 1 and <= 60, "Webhook RequestTimeoutSeconds must be between 1 and 60.")
    .Validate(options => options.MaxAttempts is >= 1 and <= 10, "Webhook MaxAttempts must be between 1 and 10.")
    .Validate(options => options.BaseRetryDelaySeconds is >= 1 and <= 3600, "Webhook BaseRetryDelaySeconds must be between 1 and 3600.")
    .Validate(options => options.MaxRetryDelaySeconds is >= 1 and <= 86400 && options.MaxRetryDelaySeconds >= options.BaseRetryDelaySeconds, "Webhook MaxRetryDelaySeconds must be between BaseRetryDelaySeconds and 86400.")
    .Validate(options => options.BatchSize is >= 1 and <= 100, "Webhook BatchSize must be between 1 and 100.")
    .Validate(options => options.Tenants.All(tenant => tenant.CustomerId != Guid.Empty), "Every webhook tenant must have a non-empty CustomerId.")
    .Validate(options => options.Tenants.Select(tenant => tenant.CustomerId).Distinct().Count() == options.Tenants.Count, "Webhook tenant CustomerIds must be unique.")
    .Validate(
        options => options.Tenants.All(tenant =>
            !string.IsNullOrWhiteSpace(tenant.Secret)
            && tenant.Secret.Length <= 512
            && tenant.Secret.Length >= (builder.Environment.IsDevelopment() ? 16 : 32)),
        "Webhook secrets must satisfy the environment-specific length requirement.")
    .Validate(
        options => options.Tenants.All(tenant =>
        {
            if (string.IsNullOrWhiteSpace(tenant.Url)
                || tenant.Url.Length > 2048
                || !Uri.TryCreate(tenant.Url, UriKind.Absolute, out var uri)
                || !string.IsNullOrEmpty(uri.UserInfo)
                || !string.IsNullOrEmpty(uri.Fragment))
            {
                return false;
            }

            if (uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
                return true;

            return builder.Environment.IsDevelopment()
                && options.DevelopmentAllowInsecureHttp
                && uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase);
        }),
        "Webhook URLs must be valid absolute HTTPS URLs; Development may explicitly allow HTTP.")
    .Validate(
        options => options.Tenants.All(tenant =>
        {
            if (!Uri.TryCreate(tenant.Url, UriKind.Absolute, out var uri)
                || !System.Net.IPAddress.TryParse(uri.Host, out var address))
            {
                return true;
            }

            return WebhookDestinationSecurity.IsPublicAddress(address)
                || (builder.Environment.IsDevelopment()
                    && options.DevelopmentAllowPrivateNetworks);
        }),
        "Webhook IP-literal destinations must use permitted network ranges.");

if (!builder.Environment.IsDevelopment())
{
    webhookOptions.Validate(
        options => !options.DevelopmentAllowInsecureHttp
            && !options.DevelopmentAllowPrivateNetworks,
        "Webhook DevelopmentAllow* options cannot be enabled outside Development.");
}

webhookOptions.ValidateOnStart();

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
builder.Services.AddScoped<IInternalDocumentIntakeService, InternalDocumentIntakeService>();
builder.Services.AddScoped<DocumentBatchIntakeService>();
builder.Services.AddScoped<IExtractionResultService, ExtractionResultService>();
builder.Services.AddScoped<IExtractionResultExportService, ExtractionResultExportService>();
builder.Services.AddScoped<IDocumentReviewService, DocumentReviewService>();
builder.Services.AddScoped<IInvoicePurchaseOrderReconciliationService, InvoicePurchaseOrderReconciliationService>();
builder.Services.AddScoped<IReconciliationCaseService, ReconciliationCaseService>();
builder.Services.AddScoped<IReconciliationCaseExportService, ReconciliationCaseExportService>();
builder.Services.AddScoped<IAccountingPostingService, AccountingPostingService>();
if (builder.Environment.IsDevelopment())
{
    builder.Services.AddSingleton<IAccountingPostingAdapter, LocalDeterministicAccountingPostingAdapter>();
}

builder.Services.AddScoped<IMailboxMessageParser, MimeMailboxMessageParser>();
builder.Services.AddScoped<IMailboxMessageIngestionService, MailboxMessageIngestionService>();
builder.Services.AddScoped<ImapMailboxPoller>();
builder.Services.AddScoped<IDocumentDeletionService, DocumentDeletionService>();
builder.Services.AddScoped<IDocumentProcessingService, DocumentProcessingService>();
builder.Services.AddSingleton<IDocumentProcessingQueue, DocumentProcessingQueue>();

// Hosted services start in registration order. Recovery enqueues persisted orphaned work
// before the normal single-reader queue consumer begins processing. Document retention and
// idempotency cleanup are independent periodic lifecycle jobs after processing startup.
builder.Services.AddHostedService<DocumentProcessingRecoveryHostedService>();
builder.Services.AddHostedService<DocumentProcessingBackgroundService>();
builder.Services.AddHostedService<DocumentRetentionHostedService>();
builder.Services.AddHostedService<IntakeIdempotencyCleanupHostedService>();
builder.Services.AddHostedService<ImapMailboxPollingHostedService>();
builder.Services.AddHostedService<WebhookDeliveryHostedService>();

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

app.UseMiddleware<IntakeIdempotencyConflictMiddleware>();
app.UseHttpsRedirection();
app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();

app.Run();
