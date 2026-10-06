using System.Text.Json;
using System.Text.Json.Serialization;

namespace DocFlow.Infrastructure.Accounting.QuickBooksOnline;

public sealed record QuickBooksOnlineReference(string Value);

public sealed record QuickBooksOnlineBillRequest(
    QuickBooksOnlineReference VendorRef,
    QuickBooksOnlineReference APAccountRef,
    string DocNumber,
    string? TxnDate,
    string? DueDate,
    QuickBooksOnlineReference CurrencyRef,
    IReadOnlyList<QuickBooksOnlineBillLine> Line,
    string? PrivateNote);

public sealed record QuickBooksOnlineBillLine(
    decimal Amount,
    string DetailType,
    string? Description,
    QuickBooksOnlineAccountBasedExpenseLineDetail AccountBasedExpenseLineDetail);

public sealed record QuickBooksOnlineAccountBasedExpenseLineDetail(
    QuickBooksOnlineReference AccountRef,
    QuickBooksOnlineReference? TaxCodeRef);

public static class QuickBooksOnlineBillRequestJson
{
    private static readonly JsonSerializerOptions Options = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public static string Serialize(QuickBooksOnlineBillRequest request)
        => JsonSerializer.Serialize(request, Options);
}
