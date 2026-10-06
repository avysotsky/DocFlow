using System.Net;
using System.Text;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Accounting.QuickBooksOnline;
using Xunit;

namespace DocFlow.Infrastructure.Tests;

public sealed class QuickBooksOnlineAccountingAdapterTests
{
    private static readonly Guid CustomerId =
        Guid.Parse("11111111-1111-1111-1111-111111111111");

    [Fact]
    public async Task PostAsync_SendsBillAndReturnsCreatedBillId()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.OK,
                """{"Bill":{"Id":"987","SyncToken":"0"}}"""));
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(AccountingPostingAdapterOutcome.Posted, result.Outcome);
        Assert.Equal("987", result.ExternalReference);
        Assert.Null(result.ErrorSummary);

        var request = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal(
            "https://sandbox-quickbooks.api.intuit.com/v3/company/realm-123/bill?requestid=aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa",
            request.Uri);
        Assert.Equal("Bearer", request.AuthorizationScheme);
        Assert.Equal("test-access-token", request.AuthorizationParameter);
        Assert.Contains(
            "\"VendorRef\":{\"value\":\"vendor-41\"}",
            request.Body,
            StringComparison.Ordinal);
        Assert.Contains(
            "\"APAccountRef\":{\"value\":\"ap-33\"}",
            request.Body,
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task PostAsync_ReusesStableProviderRequestIdForSamePosting()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.OK,
                """{"Bill":{"Id":"987","SyncToken":"0"}}"""));
        var adapter = CreateAdapter(handler);
        var posting = CreatePosting();

        await adapter.PostAsync(posting);
        await adapter.PostAsync(posting);

        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal(handler.Requests[0].Uri, handler.Requests[1].Uri);
        Assert.EndsWith(
            "?requestid=aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa",
            handler.Requests[0].Uri,
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task PostAsync_MapsValidationFaultToPermanentFailure()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.BadRequest,
                """
                {
                  "Fault": {
                    "Error": [
                      {
                        "Message": "Invalid Number",
                        "Detail": "Invalid account reference",
                        "code": "2090"
                      }
                    ],
                    "type": "ValidationFault"
                  }
                }
                """));
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(
            AccountingPostingAdapterOutcome.PermanentFailure,
            result.Outcome);
        Assert.Contains("ValidationFault", result.ErrorSummary);
        Assert.Contains("2090", result.ErrorSummary);
        Assert.Contains("Invalid Number", result.ErrorSummary);
        Assert.Null(result.RetryAfterSeconds);
    }

    [Fact]
    public async Task PostAsync_MapsThrottlingToRetryableSixtySecondDelay()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(
                HttpStatusCode.TooManyRequests,
                """{"Fault":{"Error":[],"type":"SystemFault"}}"""));
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(
            AccountingPostingAdapterOutcome.RetryableFailure,
            result.Outcome);
        Assert.Equal(60, result.RetryAfterSeconds);
    }

    [Fact]
    public async Task PostAsync_UsesRetryAfterHeaderWhenPresent()
    {
        var handler = new RecordingHandler(_ =>
        {
            var response = JsonResponse(
                HttpStatusCode.TooManyRequests,
                """{"Fault":{"Error":[],"type":"SystemFault"}}""");
            response.Headers.RetryAfter =
                new System.Net.Http.Headers.RetryConditionHeaderValue(
                    TimeSpan.FromSeconds(45));
            return response;
        });
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(
            AccountingPostingAdapterOutcome.RetryableFailure,
            result.Outcome);
        Assert.Equal(45, result.RetryAfterSeconds);
    }

    [Theory]
    [InlineData(HttpStatusCode.Unauthorized)]
    [InlineData(HttpStatusCode.RequestTimeout)]
    [InlineData(HttpStatusCode.InternalServerError)]
    [InlineData(HttpStatusCode.ServiceUnavailable)]
    public async Task PostAsync_MapsTransientHttpStatusesToRetryable(
        HttpStatusCode statusCode)
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(statusCode, "{}"));
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(
            AccountingPostingAdapterOutcome.RetryableFailure,
            result.Outcome);
    }

    [Fact]
    public async Task PostAsync_DoesNotCallHttpWhenVendorMappingIsMissing()
    {
        var handler = new RecordingHandler(_ =>
            throw new InvalidOperationException(
                "HTTP must not be called for mapping failure."));
        var adapter = CreateAdapter(handler);
        var posting = CreatePosting() with
        {
            Payload = CreatePosting().Payload with
            {
                SupplierName = "Unknown Supplier"
            }
        };

        var result = await adapter.PostAsync(posting);

        Assert.Equal(
            AccountingPostingAdapterOutcome.PermanentFailure,
            result.Outcome);
        Assert.Empty(handler.Requests);
    }

    [Fact]
    public async Task PostAsync_MapsSuccessWithoutBillIdToRetryable()
    {
        var handler = new RecordingHandler(_ =>
            JsonResponse(HttpStatusCode.OK, """{"Bill":{}}"""));
        var adapter = CreateAdapter(handler);

        var result = await adapter.PostAsync(CreatePosting());

        Assert.Equal(
            AccountingPostingAdapterOutcome.RetryableFailure,
            result.Outcome);
        Assert.Contains("without a Bill id", result.ErrorSummary);
    }

    private static QuickBooksOnlineAccountingAdapter CreateAdapter(
        RecordingHandler handler)
    {
        var httpClient = new HttpClient(handler);

        return new QuickBooksOnlineAccountingAdapter(
            httpClient,
            CreateBuilder(),
            new StaticTokenProvider("test-access-token"),
            new QuickBooksOnlineHttpOptions
            {
                BaseUrl =
                    "https://sandbox-quickbooks.api.intuit.com",
                RequestTimeoutSeconds = 30
            });
    }

    private static QuickBooksOnlineBillRequestBuilder CreateBuilder()
        => new(
            new QuickBooksOnlineBillMappingOptions
            {
                Targets =
                [
                    new QuickBooksOnlineTargetMappingOptions
                    {
                        CustomerId = CustomerId,
                        TargetKey = "primary-ledger",
                        ApAccountId = "ap-33",
                        DefaultExpenseAccountId = "expense-default",
                        Vendors =
                        [
                            new QuickBooksOnlineVendorMappingOptions
                            {
                                SupplierName = "ACME Components Ltd.",
                                VendorId = "vendor-41"
                            }
                        ],
                        ExpenseAccounts =
                        [
                            new QuickBooksOnlineExpenseAccountMappingOptions
                            {
                                Sku = "AX-100",
                                AccountId = "expense-components"
                            }
                        ],
                        TaxCodes =
                        [
                            new QuickBooksOnlineTaxCodeMappingOptions
                            {
                                Rate = 20m,
                                TaxCodeId = "vat-20"
                            }
                        ]
                    }
                ]
            });

    private static AccountingPostingRequest CreatePosting()
        => new(
            Guid.Parse("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            CustomerId,
            Guid.Parse("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            "primary-ledger",
            "realm-123",
            "posting-key-1",
            new AccountingBillPayload(
                AccountingBillPayload.CurrentSchemaVersion,
                "ACME Components Ltd.",
                "INV-2026-091",
                new DateOnly(2026, 9, 30),
                new DateOnly(2026, 10, 30),
                "EUR",
                null,
                "PO-78421",
                [
                    new AccountingBillLine(
                        "AX-100",
                        "Sensor bracket",
                        20m,
                        "pcs",
                        12.50m,
                        null,
                        250.00m)
                ],
                null,
                false,
                250.00m,
                20m,
                50.00m,
                300.00m,
                [],
                "Net 30",
                "Supplier note"));

    private static HttpResponseMessage JsonResponse(
        HttpStatusCode statusCode,
        string json)
        => new(statusCode)
        {
            Content = new StringContent(
                json,
                Encoding.UTF8,
                "application/json")
        };

    private sealed class StaticTokenProvider
        : IQuickBooksOnlineAccessTokenProvider
    {
        private readonly string? _token;

        public StaticTokenProvider(string? token)
        {
            _token = token;
        }

        public Task<string?> GetAccessTokenAsync(
            Guid customerId,
            string targetKey,
            CancellationToken cancellationToken = default)
            => Task.FromResult(_token);
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

        public RecordingHandler(
            Func<HttpRequestMessage, HttpResponseMessage> handler)
        {
            _handler = handler;
        }

        public List<RecordedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Requests.Add(
                new RecordedRequest(
                    request.Method,
                    request.RequestUri!.ToString(),
                    request.Headers.Authorization?.Scheme,
                    request.Headers.Authorization?.Parameter,
                    request.Content is null
                        ? string.Empty
                        : await request.Content.ReadAsStringAsync(
                            cancellationToken)));

            return _handler(request);
        }
    }

    private sealed record RecordedRequest(
        HttpMethod Method,
        string Uri,
        string? AuthorizationScheme,
        string? AuthorizationParameter,
        string Body);
}
