using DocFlow.Api.Accounting;
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
using DocFlow.Infrastructure.Accounting.QuickBooksOnline;
using DocFlow.Infrastructure.Documents;
using DocFlow.Infrastructure.Export;
using DocFlow.Infrastructure.Mailbox;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using DocFlow.Infrastructure.Storage;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
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
    .AddOptions<AccountingPostingTargetsOptions>()
    .Bind(builder.Configuration.GetSection(AccountingPostingTargetsOptions.ConfigurationSection))
    .Validate(
        options => options.Targets.All(target =>
            target.CustomerId != Guid.Empty
            && !string.IsNullOrWhiteSpace(target.Key)
            && target.Key.Trim().Length <= 100
            && !string.IsNullOrWhiteSpace(target.Provider)
            && target.Provider.Trim().Length <= 64
            && !string.IsNullOrWhiteSpace(target.TargetAccount)
            && target.TargetAccount.Trim().Length <= 200),
        "Every accounting target must have valid tenant, key, provider and target account.")
    .Validate(
        options => options.Targets
            .Select(target => $"{target.CustomerId:N}:{target.Key.Trim().ToLowerInvariant()}")
            .Distinct(StringComparer.Ordinal)
            .Count() == options.Targets.Count,
        "Accounting target keys must be unique within each tenant.")
    .ValidateOnStart();

builder.Services
    .AddOptions<AccountingPostingWorkerOptions>()
    .Bind(builder.Configuration.GetSection(AccountingPostingWorkerOptions.ConfigurationSection))
    .Validate(
        options => options.PollIntervalSeconds is >= 1 and <= 3600,
        "Accounting posting PollIntervalSeconds must be between 1 and 3600.")
    .Validate(
        options => options.BatchSize is >= 1 and <= 500,
        "Accounting posting BatchSize must be between 1 and 500.")
    .Validate(
        options => options.InProgressTimeoutSeconds is >= 1 and <= 86400,
        "Accounting posting InProgressTimeoutSeconds must be between 1 and 86400.")
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
builder.Services.AddScoped<IAccountingBillPayloadFactory, AccountingBillPayloadFactory>();
builder.Services.AddSingleton<IAccountingPostingTargetResolver, ConfiguredAccountingPostingTargetResolver>();
var quickBooksMappings = builder.Configuration
    .GetSection(QuickBooksOnlineBillMappingOptions.ConfigurationSection)
    .Get<QuickBooksOnlineBillMappingOptions>()
    ?? new QuickBooksOnlineBillMappingOptions();

ValidateQuickBooksOnlineMappings(quickBooksMappings);

builder.Services.AddSingleton(quickBooksMappings);
builder.Services.AddSingleton<QuickBooksOnlineBillRequestBuilder>();

var quickBooksHttp = builder.Configuration
    .GetSection(QuickBooksOnlineHttpOptions.ConfigurationSection)
    .Get<QuickBooksOnlineHttpOptions>()
    ?? new QuickBooksOnlineHttpOptions();

ValidateQuickBooksOnlineHttpOptions(quickBooksHttp);

builder.Services.AddSingleton(quickBooksHttp);

var quickBooksOAuth = builder.Configuration
    .GetSection(QuickBooksOnlineOAuthOptions.ConfigurationSection)
    .Get<QuickBooksOnlineOAuthOptions>()
    ?? new QuickBooksOnlineOAuthOptions();

ValidateQuickBooksOnlineOAuthOptions(quickBooksOAuth);

builder.Services.AddSingleton(quickBooksOAuth);

var dataProtection = builder.Services
    .AddDataProtection()
    .SetApplicationName("DocFlow");

if (quickBooksOAuth.Enabled)
{
    dataProtection.PersistKeysToFileSystem(
        new DirectoryInfo(quickBooksOAuth.DataProtectionKeyRingPath));
}

builder.Services.AddSingleton<ISecretProtector, DataProtectionSecretProtector>();
builder.Services.AddHttpClient<IQuickBooksOnlineTokenClient, QuickBooksOnlineTokenClient>();
builder.Services.AddScoped<IQuickBooksOnlineOAuthService, QuickBooksOnlineOAuthService>();
builder.Services.AddScoped<IQuickBooksOnlineAccessTokenProvider, QuickBooksOnlineAccessTokenProvider>();

if (quickBooksOAuth.Enabled)
{
    builder.Services.AddHttpClient<QuickBooksOnlineAccountingAdapter>();
    builder.Services.AddScoped<IAccountingPostingAdapter>(
        serviceProvider =>
            serviceProvider.GetRequiredService<QuickBooksOnlineAccountingAdapter>());
}

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
builder.Services.AddHostedService<AccountingPostingHostedService>();
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

static void ValidateQuickBooksOnlineOAuthOptions(
    QuickBooksOnlineOAuthOptions options)
{
    if (options.StateLifetimeMinutes is < 1 or > 30)
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth StateLifetimeMinutes must be between 1 and 30.");
    }

    if (options.AccessTokenRefreshSkewSeconds is < 0 or > 600)
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth AccessTokenRefreshSkewSeconds must be between 0 and 600.");
    }

    if (!options.Enabled)
        return;

    if (string.IsNullOrWhiteSpace(options.ClientId)
        || string.IsNullOrWhiteSpace(options.ClientSecret))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth ClientId and ClientSecret are required when OAuth is enabled.");
    }

    if (!Uri.TryCreate(
            options.RedirectUri,
            UriKind.Absolute,
            out var redirectUri)
        || !string.Equals(
            redirectUri.Scheme,
            Uri.UriSchemeHttps,
            StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth RedirectUri must be an absolute HTTPS URL.");
    }

    if (!Uri.TryCreate(
            options.AuthorizationUrl,
            UriKind.Absolute,
            out var authorizationUri)
        || !string.Equals(
            authorizationUri.Scheme,
            Uri.UriSchemeHttps,
            StringComparison.OrdinalIgnoreCase)
        || !string.Equals(
            authorizationUri.Host,
            "appcenter.intuit.com",
            StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth AuthorizationUrl must use the official Intuit authorization host.");
    }

    if (!Uri.TryCreate(
            options.TokenUrl,
            UriKind.Absolute,
            out var tokenUri)
        || !string.Equals(
            tokenUri.Scheme,
            Uri.UriSchemeHttps,
            StringComparison.OrdinalIgnoreCase)
        || !string.Equals(
            tokenUri.Host,
            "oauth.platform.intuit.com",
            StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth TokenUrl must use the official Intuit token host.");
    }

    if (!options.Scope
        .Split(
            ' ',
            StringSplitOptions.RemoveEmptyEntries
                | StringSplitOptions.TrimEntries)
        .Contains(
            "com.intuit.quickbooks.accounting",
            StringComparer.Ordinal))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth scope must include com.intuit.quickbooks.accounting.");
    }

    if (string.IsNullOrWhiteSpace(options.DataProtectionKeyRingPath))
    {
        throw new InvalidOperationException(
            "QuickBooks Online OAuth requires a persistent DataProtectionKeyRingPath.");
    }
}

static void ValidateQuickBooksOnlineHttpOptions(
    QuickBooksOnlineHttpOptions options)
{
    if (options.RequestTimeoutSeconds is < 1 or > 120)
    {
        throw new InvalidOperationException(
            "QuickBooks Online HTTP RequestTimeoutSeconds must be between 1 and 120.");
    }

    if (!Uri.TryCreate(options.BaseUrl, UriKind.Absolute, out var baseUri)
        || !string.Equals(baseUri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "QuickBooks Online HTTP BaseUrl must be an absolute HTTPS URL.");
    }

    if (!string.Equals(
            baseUri.Host,
            "sandbox-quickbooks.api.intuit.com",
            StringComparison.OrdinalIgnoreCase)
        && !string.Equals(
            baseUri.Host,
            "quickbooks.api.intuit.com",
            StringComparison.OrdinalIgnoreCase))
    {
        throw new InvalidOperationException(
            "QuickBooks Online HTTP BaseUrl must use an official Intuit API host.");
    }
}

static void ValidateQuickBooksOnlineMappings(
    QuickBooksOnlineBillMappingOptions options)
{
    foreach (var target in options.Targets)
    {
        if (target.CustomerId == Guid.Empty
            || string.IsNullOrWhiteSpace(target.TargetKey)
            || string.IsNullOrWhiteSpace(target.ApAccountId)
            || string.IsNullOrWhiteSpace(target.DefaultExpenseAccountId))
        {
            throw new InvalidOperationException(
                "Every QuickBooks Online mapping requires customer, target key, AP account and default expense account.");
        }

        if (target.Vendors.Count == 0
            || target.Vendors.Any(item =>
                string.IsNullOrWhiteSpace(item.SupplierName)
                || string.IsNullOrWhiteSpace(item.VendorId)))
        {
            throw new InvalidOperationException(
                "Every QuickBooks Online mapping requires valid supplier-to-vendor mappings.");
        }

        if (target.Vendors
            .Select(item => item.SupplierName.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Count() != target.Vendors.Count)
        {
            throw new InvalidOperationException(
                "QuickBooks Online supplier mappings must be unique within a target.");
        }

        if (target.ExpenseAccounts.Any(item =>
                string.IsNullOrWhiteSpace(item.Sku)
                || string.IsNullOrWhiteSpace(item.AccountId))
            || target.ExpenseAccounts
                .Select(item => item.Sku.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Count() != target.ExpenseAccounts.Count)
        {
            throw new InvalidOperationException(
                "QuickBooks Online SKU expense-account mappings must be valid and unique within a target.");
        }

        if (target.TaxCodes.Any(item => string.IsNullOrWhiteSpace(item.TaxCodeId))
            || target.TaxCodes
                .Select(item => item.Rate)
                .Distinct()
                .Count() != target.TaxCodes.Count)
        {
            throw new InvalidOperationException(
                "QuickBooks Online tax-code mappings must be valid and unique by rate within a target.");
        }
    }

    if (options.Targets
        .Select(target => $"{target.CustomerId:N}:{target.TargetKey.Trim()}")
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .Count() != options.Targets.Count)
    {
        throw new InvalidOperationException(
            "QuickBooks Online target mappings must be unique within each tenant.");
    }
}
