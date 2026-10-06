using System.Net.Http.Headers;
using System.Text.Json;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed record QuickBooksOnlineReferenceCatalog(
    IReadOnlyList<QuickBooksOnlineVendorReference> Vendors,
    IReadOnlyList<QuickBooksOnlineAccountReference> Accounts,
    IReadOnlyList<QuickBooksOnlineTaxCodeReference> TaxCodes);

public sealed record QuickBooksOnlineVendorReference(
    string Id,
    string DisplayName,
    bool Active);

public sealed record QuickBooksOnlineAccountReference(
    string Id,
    string Name,
    string? FullyQualifiedName,
    string? AccountType,
    string? AccountSubType,
    bool Active);

public sealed record QuickBooksOnlineTaxCodeReference(
    string Id,
    string Name,
    bool Active);

public sealed class QuickBooksOnlineReferenceDiscoveryService
{
    private readonly HttpClient _httpClient;
    private readonly DocFlowDbContext _dbContext;
    private readonly IQuickBooksOnlineAccessTokenProvider _accessTokenProvider;
    private readonly QuickBooksOnlineHttpOptions _options;

    public QuickBooksOnlineReferenceDiscoveryService(
        HttpClient httpClient,
        DocFlowDbContext dbContext,
        IQuickBooksOnlineAccessTokenProvider accessTokenProvider,
        QuickBooksOnlineHttpOptions options)
    {
        _httpClient = httpClient;
        _dbContext = dbContext;
        _accessTokenProvider = accessTokenProvider;
        _options = options;
    }

    public async Task<QuickBooksOnlineReferenceCatalog?> DiscoverAsync(
        Guid customerId,
        string targetKey,
        CancellationToken cancellationToken = default)
    {
        if (customerId == Guid.Empty || string.IsNullOrWhiteSpace(targetKey))
            return null;

        var normalizedTargetKey = targetKey.Trim();

        var connection = await _dbContext.QuickBooksOnlineConnections
            .AsNoTracking()
            .SingleOrDefaultAsync(
                item => item.CustomerId == customerId
                    && item.TargetKey == normalizedTargetKey
                    && item.DisconnectedAt == null,
                cancellationToken);

        if (connection is null)
            return null;

        var accessToken = await _accessTokenProvider.GetAccessTokenAsync(
            customerId,
            normalizedTargetKey,
            cancellationToken);

        if (string.IsNullOrWhiteSpace(accessToken))
            return null;

        var vendors = await QueryAsync(
            connection.RealmId,
            accessToken,
            "select * from Vendor maxresults 1000",
            "Vendor",
            ParseVendors,
            cancellationToken);

        var accounts = await QueryAsync(
            connection.RealmId,
            accessToken,
            "select * from Account maxresults 1000",
            "Account",
            ParseAccounts,
            cancellationToken);

        var taxCodes = await QueryAsync(
            connection.RealmId,
            accessToken,
            "select * from TaxCode maxresults 1000",
            "TaxCode",
            ParseTaxCodes,
            cancellationToken);

        return new QuickBooksOnlineReferenceCatalog(
            vendors,
            accounts,
            taxCodes);
    }

    private async Task<IReadOnlyList<T>> QueryAsync<T>(
        string realmId,
        string accessToken,
        string query,
        string entityName,
        Func<JsonElement, IReadOnlyList<T>> parser,
        CancellationToken cancellationToken)
    {
        var baseUri = new Uri(
            _options.BaseUrl.TrimEnd('/') + "/",
            UriKind.Absolute);
        var uri = new Uri(
            baseUri,
            $"v3/company/{Uri.EscapeDataString(realmId.Trim())}/query"
            + $"?query={Uri.EscapeDataString(query)}");

        using var request = new HttpRequestMessage(HttpMethod.Get, uri);
        request.Headers.Authorization =
            new AuthenticationHeaderValue("Bearer", accessToken.Trim());
        request.Headers.Accept.Add(
            new MediaTypeWithQualityHeaderValue("application/json"));

        using var timeoutSource =
            CancellationTokenSource.CreateLinkedTokenSource(
                cancellationToken);
        timeoutSource.CancelAfter(
            TimeSpan.FromSeconds(_options.RequestTimeoutSeconds));

        using var response = await _httpClient.SendAsync(
            request,
            HttpCompletionOption.ResponseHeadersRead,
            timeoutSource.Token);

        var body = await response.Content.ReadAsStringAsync(
            timeoutSource.Token);

        if (!response.IsSuccessStatusCode)
        {
            throw new HttpRequestException(
                $"QuickBooks Online {entityName} discovery returned HTTP {(int)response.StatusCode}.",
                inner: null,
                response.StatusCode);
        }

        using var document = JsonDocument.Parse(body);

        if (!document.RootElement.TryGetProperty(
                "QueryResponse",
                out var queryResponse)
            || queryResponse.ValueKind != JsonValueKind.Object)
        {
            return [];
        }

        return parser(queryResponse);
    }

    private static IReadOnlyList<QuickBooksOnlineVendorReference> ParseVendors(
        JsonElement queryResponse)
    {
        if (!queryResponse.TryGetProperty("Vendor", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items.EnumerateArray()
            .Select(item => new QuickBooksOnlineVendorReference(
                ReadRequiredString(item, "Id"),
                ReadDisplayName(item),
                ReadBoolean(item, "Active", defaultValue: true)))
            .OrderBy(item => item.DisplayName, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IReadOnlyList<QuickBooksOnlineAccountReference> ParseAccounts(
        JsonElement queryResponse)
    {
        if (!queryResponse.TryGetProperty("Account", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items.EnumerateArray()
            .Select(item => new QuickBooksOnlineAccountReference(
                ReadRequiredString(item, "Id"),
                ReadRequiredString(item, "Name"),
                ReadOptionalString(item, "FullyQualifiedName"),
                ReadOptionalString(item, "AccountType"),
                ReadOptionalString(item, "AccountSubType"),
                ReadBoolean(item, "Active", defaultValue: true)))
            .OrderBy(item => item.FullyQualifiedName ?? item.Name, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IReadOnlyList<QuickBooksOnlineTaxCodeReference> ParseTaxCodes(
        JsonElement queryResponse)
    {
        if (!queryResponse.TryGetProperty("TaxCode", out var items)
            || items.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return items.EnumerateArray()
            .Select(item => new QuickBooksOnlineTaxCodeReference(
                ReadRequiredString(item, "Id"),
                ReadRequiredString(item, "Name"),
                ReadBoolean(item, "Active", defaultValue: true)))
            .OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string ReadDisplayName(JsonElement item)
        => ReadOptionalString(item, "DisplayName")
            ?? ReadOptionalString(item, "CompanyName")
            ?? ReadOptionalString(item, "PrintOnCheckName")
            ?? ReadRequiredString(item, "Id");

    private static string ReadRequiredString(
        JsonElement item,
        string propertyName)
        => ReadOptionalString(item, propertyName)
            ?? throw new InvalidOperationException(
                $"QuickBooks Online reference is missing '{propertyName}'.");

    private static string? ReadOptionalString(
        JsonElement item,
        string propertyName)
    {
        if (!item.TryGetProperty(propertyName, out var value)
            || value.ValueKind is JsonValueKind.Null
                or JsonValueKind.Undefined)
        {
            return null;
        }

        return value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : value.ToString();
    }

    private static bool ReadBoolean(
        JsonElement item,
        string propertyName,
        bool defaultValue)
        => item.TryGetProperty(propertyName, out var value)
            && value.ValueKind is JsonValueKind.True or JsonValueKind.False
                ? value.GetBoolean()
                : defaultValue;
}
