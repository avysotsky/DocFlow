using System.Text.Json;
using System.Text.Json.Nodes;
using DocFlow.Domain.Entities;

namespace DocFlow.Infrastructure.Processing;

public static class ReviewedStructuredDataComposer
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = false
    };

    public static string Compose(
        string originalStructuredDataJson,
        DocumentReview? review)
    {
        if (review is null)
            return originalStructuredDataJson;

        var root = JsonNode.Parse(originalStructuredDataJson) as JsonObject
            ?? throw new InvalidOperationException(
                "Persisted extraction result must be a JSON object.");

        var correctedData = JsonNode.Parse(review.CorrectedDataJson) as JsonObject
            ?? throw new InvalidOperationException(
                "Persisted review data must be a JSON object.");

        root["data"] = correctedData;
        root["human_review"] = new JsonObject
        {
            ["review_id"] = review.Id.ToString(),
            ["reviewed_at"] = review.ReviewedAt.ToString("O"),
            ["reviewed_by_client"] = review.ReviewedByClient,
            ["note"] = review.Note
        };

        return root.ToJsonString(JsonOptions);
    }
}
