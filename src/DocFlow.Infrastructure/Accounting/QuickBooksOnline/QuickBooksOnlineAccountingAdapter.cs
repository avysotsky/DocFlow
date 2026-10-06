using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using DocFlow.Application.Abstractions;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed class QuickBooksOnlineAccountingAdapter
    : IAccountingPostingAdapter
{
    public const string ProviderName = "quickbooks-online";

    private readonly HttpClient _httpClient;
    private readonly QuickBooksOnlineBillRequestBuilder _requestBuilder;
    private readonly IQuickBooksOnlineAccessTokenProvider _accessTokenProvider;
    private readonly QuickBooksOnlineHttpOptions _options;

    public QuickBooksOnlineAccountingAdapter(
        HttpClient httpClient,
        QuickBooksOnlineBillRequestBuilder requestBuilder,
        IQuickBooksOnlineAccessTokenProvider accessTokenProvider,
        QuickBooksOnlineHttpOptions options)
    {
        _httpClient = httpClient;
        _requestBuilder = requestBuilder;
        _accessTokenProvider = accessTokenProvider;
        _options = options;
    }

    public string Provider => ProviderName;

    public async Task<AccountingPostingAdapterResult> PostAsync(
        AccountingPostingRequest request,
        CancellationToken cancellationToken = default)
    {
        var build = _requestBuilder.Build(request);
        if (build.Outcome != QuickBooksOnlineBillBuildOutcome.Completed
            || build.Request is null)
        {
            return PermanentFailure(
                build.Error ?? "QuickBooks Online bill mapping failed.");
        }

        var accessToken = await _accessTokenProvider.GetAccessTokenAsync(
            request.CustomerId,
            request.TargetKey,
            cancellationToken);

        if (string.IsNullOrWhiteSpace(accessToken))
        {
            return PermanentFailure(
                "QuickBooks Online access token is not available for this target.");
        }

        if (string.IsNullOrWhiteSpace(request.TargetAccount))
        {
            return PermanentFailure(
                "QuickBooks Online realm id is not configured for this target.");
        }

        using var httpRequest = new HttpRequestMessage(
            HttpMethod.Post,
            CreateBillUri(request.TargetAccount));

        httpRequest.Headers.Authorization =
            new AuthenticationHeaderValue("Bearer", accessToken.Trim());
        httpRequest.Headers.Accept.Add(
            new MediaTypeWithQualityHeaderValue("application/json"));
        httpRequest.Content = new StringContent(
            QuickBooksOnlineBillRequestJson.Serialize(build.Request),
            Encoding.UTF8,
            "application/json");

        using var timeoutSource =
            CancellationTokenSource.CreateLinkedTokenSource(
                cancellationToken);
        timeoutSource.CancelAfter(
            TimeSpan.FromSeconds(_options.RequestTimeoutSeconds));

        HttpResponseMessage response;
        try
        {
            response = await _httpClient.SendAsync(
                httpRequest,
                HttpCompletionOption.ResponseHeadersRead,
                timeoutSource.Token);
        }
        catch (OperationCanceledException)
            when (!cancellationToken.IsCancellationRequested)
        {
            return new AccountingPostingAdapterResult(
                AccountingPostingAdapterOutcome.RetryableFailure,
                ErrorSummary: "QuickBooks Online request timed out.");
        }
        catch (HttpRequestException exception)
        {
            return new AccountingPostingAdapterResult(
                AccountingPostingAdapterOutcome.RetryableFailure,
                ErrorSummary:
                    $"QuickBooks Online transport failure: {exception.Message}");
        }

        using (response)
        {
            var responseJson = await response.Content.ReadAsStringAsync(
                cancellationToken);

            if (response.IsSuccessStatusCode)
            {
                var billId = TryReadBillId(responseJson);
                if (!string.IsNullOrWhiteSpace(billId))
                {
                    return new AccountingPostingAdapterResult(
                        AccountingPostingAdapterOutcome.Posted,
                        ExternalReference: billId);
                }

                return new AccountingPostingAdapterResult(
                    AccountingPostingAdapterOutcome.RetryableFailure,
                    ErrorSummary:
                        "QuickBooks Online returned success without a Bill id.");
            }

            var errorSummary = BuildErrorSummary(
                response.StatusCode,
                responseJson);

            if (IsRetryable(response.StatusCode))
            {
                return new AccountingPostingAdapterResult(
                    AccountingPostingAdapterOutcome.RetryableFailure,
                    ErrorSummary: errorSummary,
                    RetryAfterSeconds:
                        ResolveRetryAfterSeconds(response));
            }

            return PermanentFailure(errorSummary);
        }
    }

    private Uri CreateBillUri(string realmId)
    {
        var baseUri = new Uri(
            _options.BaseUrl.TrimEnd('/') + "/",
            UriKind.Absolute);

        return new Uri(
            baseUri,
            $"v3/company/{Uri.EscapeDataString(realmId.Trim())}/bill");
    }

    private static string? TryReadBillId(string responseJson)
    {
        if (string.IsNullOrWhiteSpace(responseJson))
            return null;

        try
        {
            using var document = JsonDocument.Parse(responseJson);
            if (!document.RootElement.TryGetProperty(
                    "Bill",
                    out var bill)
                || bill.ValueKind != JsonValueKind.Object
                || !bill.TryGetProperty("Id", out var id))
            {
                return null;
            }

            return id.ValueKind == JsonValueKind.String
                ? id.GetString()
                : id.ToString();
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static string BuildErrorSummary(
        HttpStatusCode statusCode,
        string responseJson)
    {
        var fallback =
            $"QuickBooks Online HTTP {(int)statusCode} ({statusCode}).";

        if (string.IsNullOrWhiteSpace(responseJson))
            return fallback;

        try
        {
            using var document = JsonDocument.Parse(responseJson);
            var root = document.RootElement;

            if (!root.TryGetProperty("Fault", out var fault)
                || fault.ValueKind != JsonValueKind.Object)
            {
                return fallback;
            }

            var faultType = fault.TryGetProperty("type", out var type)
                ? type.GetString()
                : null;

            if (!fault.TryGetProperty("Error", out var errors)
                || errors.ValueKind != JsonValueKind.Array
                || errors.GetArrayLength() == 0)
            {
                return string.IsNullOrWhiteSpace(faultType)
                    ? fallback
                    : $"{fallback} Fault={faultType}.";
            }

            var error = errors[0];
            var code = error.TryGetProperty("code", out var codeProperty)
                ? codeProperty.GetString()
                : null;
            var message = error.TryGetProperty(
                "Message",
                out var messageProperty)
                ? messageProperty.GetString()
                : null;
            var detail = error.TryGetProperty(
                "Detail",
                out var detailProperty)
                ? detailProperty.GetString()
                : null;

            return string.Join(
                " ",
                new[]
                {
                    fallback,
                    string.IsNullOrWhiteSpace(faultType)
                        ? null
                        : $"Fault={faultType}.",
                    string.IsNullOrWhiteSpace(code)
                        ? null
                        : $"Code={code}.",
                    string.IsNullOrWhiteSpace(message)
                        ? null
                        : message,
                    string.IsNullOrWhiteSpace(detail)
                        ? null
                        : detail
                }.Where(value => value is not null));
        }
        catch (JsonException)
        {
            return fallback;
        }
    }

    private static bool IsRetryable(HttpStatusCode statusCode)
    {
        var code = (int)statusCode;
        return statusCode is HttpStatusCode.Unauthorized
            or HttpStatusCode.RequestTimeout
            or HttpStatusCode.TooManyRequests
            || code == 425
            || code >= 500;
    }

    private static int? ResolveRetryAfterSeconds(
        HttpResponseMessage response)
    {
        var retryAfter = response.Headers.RetryAfter;
        if (retryAfter?.Delta is TimeSpan delta)
            return Math.Max(1, (int)Math.Ceiling(delta.TotalSeconds));

        if (retryAfter?.Date is DateTimeOffset retryDate)
        {
            var seconds = (int)Math.Ceiling(
                (retryDate - DateTimeOffset.UtcNow).TotalSeconds);
            return Math.Max(1, seconds);
        }

        return response.StatusCode == HttpStatusCode.TooManyRequests
            ? 60
            : null;
    }

    private static AccountingPostingAdapterResult PermanentFailure(
        string error)
        => new(
            AccountingPostingAdapterOutcome.PermanentFailure,
            ErrorSummary: error);
}
