using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using DocFlow.Domain.Entities;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Notifications;

public sealed class WebhookDeliveryHostedService : BackgroundService
{
    private const string EventType = "document.completed";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };

    private readonly IServiceScopeFactory _scopeFactory;
    private readonly WebhookDeliveryOptions _options;
    private readonly IReadOnlyDictionary<Guid, WebhookTarget> _targets;
    private readonly HttpClient _httpClient;
    private readonly ILogger<WebhookDeliveryHostedService> _logger;

    public WebhookDeliveryHostedService(
        IServiceScopeFactory scopeFactory,
        IOptions<WebhookDeliveryOptions> options,
        IHostEnvironment environment,
        ILogger<WebhookDeliveryHostedService> logger)
    {
        _scopeFactory = scopeFactory;
        _options = options.Value;
        _logger = logger;

        _targets = _options.Tenants.ToDictionary(
            tenant => tenant.CustomerId,
            tenant => new WebhookTarget(
                new Uri(tenant.Url, UriKind.Absolute),
                tenant.Secret));

        var allowPrivateNetworks =
            environment.IsDevelopment()
            && _options.DevelopmentAllowPrivateNetworks;

        var handler = new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            UseProxy = false,
            MaxResponseHeadersLength = 16,
            PooledConnectionLifetime = TimeSpan.FromMinutes(2),
            ConnectCallback = (context, cancellationToken) =>
                WebhookDestinationSecurity.ConnectAsync(
                    context,
                    allowPrivateNetworks,
                    cancellationToken)
        };

        _httpClient = new HttpClient(handler, disposeHandler: true)
        {
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (_targets.Count == 0)
        {
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
            }

            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            var processed = 0;

            try
            {
                processed = await DeliverDueBatchAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception exception)
            {
                _logger.LogError(exception, "Webhook delivery sweep failed.");
            }

            if (processed >= _options.BatchSize)
                continue;

            try
            {
                await Task.Delay(
                    TimeSpan.FromSeconds(_options.PollIntervalSeconds),
                    stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
        }
    }

    private async Task<int> DeliverDueBatchAsync(CancellationToken stoppingToken)
    {
        using var scope = _scopeFactory.CreateScope();
        var dbContext = scope.ServiceProvider.GetRequiredService<DocFlowDbContext>();
        var now = DateTimeOffset.UtcNow;
        var customerIds = _targets.Keys.ToArray();

        var events = await dbContext.DocumentCompletionEvents
            .Where(x =>
                customerIds.Contains(x.CustomerId)
                && x.DeliveredAt == null
                && x.DeliveryAbandonedAt == null
                && x.NextDeliveryAttemptAt != null
                && x.NextDeliveryAttemptAt <= now)
            .OrderBy(x => x.NextDeliveryAttemptAt)
            .ThenBy(x => x.OccurredAt)
            .Take(_options.BatchSize)
            .ToListAsync(stoppingToken);

        foreach (var completionEvent in events)
        {
            if (!_targets.TryGetValue(completionEvent.CustomerId, out var target))
                continue;

            var result = await SendAsync(
                completionEvent,
                target,
                stoppingToken);
            var completedAt = DateTimeOffset.UtcNow;

            if (result.Success)
            {
                completionEvent.MarkDelivered(completedAt);
                _logger.LogInformation(
                    "Delivered webhook event {EventId} for document {DocumentId}.",
                    completionEvent.Id,
                    completionEvent.DocumentId);
            }
            else
            {
                completionEvent.MarkDeliveryFailed(
                    completedAt,
                    result.ErrorSummary!,
                    _options.MaxAttempts,
                    _options.BaseRetryDelaySeconds,
                    _options.MaxRetryDelaySeconds);

                _logger.LogWarning(
                    "Webhook event {EventId} delivery attempt failed. Attempts={Attempts}, abandoned={Abandoned}.",
                    completionEvent.Id,
                    completionEvent.DeliveryAttempts,
                    completionEvent.DeliveryAbandonedAt is not null);
            }

            await dbContext.SaveChangesAsync(stoppingToken);
        }

        return events.Count;
    }

    private async Task<DeliveryResult> SendAsync(
        DocumentCompletionEvent completionEvent,
        WebhookTarget target,
        CancellationToken stoppingToken)
    {
        var payload = new WebhookPayload(
            completionEvent.Id,
            EventType,
            completionEvent.OccurredAt,
            completionEvent.DocumentId,
            completionEvent.CustomerId,
            completionEvent.Status.ToString(),
            completionEvent.DocumentType,
            completionEvent.ProcessingAttempts);

        var body = JsonSerializer.SerializeToUtf8Bytes(payload, JsonOptions);
        var signature = ComputeSignature(target.Secret, body);

        using var request = new HttpRequestMessage(HttpMethod.Post, target.Uri)
        {
            Content = new ByteArrayContent(body)
        };

        request.Content.Headers.ContentType =
            new MediaTypeHeaderValue("application/json")
            {
                CharSet = "utf-8"
            };

        request.Headers.TryAddWithoutValidation(
            "X-DocFlow-Event-Id",
            completionEvent.Id.ToString("D"));
        request.Headers.TryAddWithoutValidation(
            "X-DocFlow-Signature",
            $"sha256={signature}");
        request.Headers.TryAddWithoutValidation(
            "User-Agent",
            "DocFlow-Webhooks/1.0");

        using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(
            stoppingToken);
        timeoutCts.CancelAfter(
            TimeSpan.FromSeconds(_options.RequestTimeoutSeconds));

        try
        {
            using var response = await _httpClient.SendAsync(
                request,
                HttpCompletionOption.ResponseHeadersRead,
                timeoutCts.Token);

            if (response.IsSuccessStatusCode)
                return DeliveryResult.Succeeded;

            return DeliveryResult.Failed(
                $"Webhook endpoint returned HTTP {(int)response.StatusCode}.");
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            throw;
        }
        catch (OperationCanceledException)
        {
            return DeliveryResult.Failed("Webhook delivery timed out.");
        }
        catch (HttpRequestException)
        {
            return DeliveryResult.Failed(
                "Webhook delivery could not reach the configured destination.");
        }
        catch (Exception)
        {
            return DeliveryResult.Failed("Webhook delivery failed.");
        }
    }

    private static string ComputeSignature(string secret, byte[] body)
    {
        var secretBytes = Encoding.UTF8.GetBytes(secret);
        var hash = HMACSHA256.HashData(secretBytes, body);
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    public override void Dispose()
    {
        _httpClient.Dispose();
        base.Dispose();
    }

    private sealed record WebhookTarget(Uri Uri, string Secret);

    private sealed record WebhookPayload(
        Guid EventId,
        string EventType,
        DateTimeOffset OccurredAt,
        Guid DocumentId,
        Guid CustomerId,
        string Status,
        string? DocumentType,
        int ProcessingAttempts);

    private sealed record DeliveryResult(bool Success, string? ErrorSummary)
    {
        public static readonly DeliveryResult Succeeded = new(true, null);

        public static DeliveryResult Failed(string errorSummary) =>
            new(false, errorSummary);
    }
}
