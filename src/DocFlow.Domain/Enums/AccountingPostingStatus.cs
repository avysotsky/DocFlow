using System.Text.Json.Serialization;

namespace DocFlow.Domain.Enums;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum AccountingPostingStatus
{
    Pending,
    Posting,
    Posted,
    Failed
}
