using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace DocFlow.Normalization;

/// <summary>
/// Provider-free .NET port of DocFlow's deterministic text normalization and identity algorithm.
/// The Python implementation remains the reference until differential CI proves equivalence.
/// </summary>
public static class TextDocumentNormalizer
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        WriteIndented = false
    };

    public static JsonObject Normalize(JsonElement raw)
    {
        if (raw.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Document must be an object.");
        RequireKeys(raw, "title", "document_type", "source", "segments");
        var title = Required(GetRequiredString(raw, "title"), "title");
        var kind = Required(GetRequiredString(raw, "document_type"), "document_type");
        var sourceRaw = raw.GetProperty("source");
        RequireKeys(sourceRaw, "provider");
        var provider = Required(GetRequiredString(sourceRaw, "provider"), "provider");
        var uri = OptionalIdentifier(sourceRaw, "source_uri");
        var sourceId = OptionalIdentifier(sourceRaw, "source_document_id");
        if (uri is null && sourceId is null)
            throw new ArgumentException("Source identity is required.");
        var sourceTime = Date(sourceRaw, "source_timestamp");
        var published = Date(sourceRaw, "published_at");
        var retrieved = Date(sourceRaw, "retrieved_at");
        var timeline = new[] { sourceTime, published, retrieved };
        for (var i = 0; i < timeline.Length; i++)
            for (var j = i + 1; j < timeline.Length; j++)
                if (timeline[i] is not null && timeline[j] is not null &&
                    timeline[i]!.Value > timeline[j]!.Value)
                    throw new ArgumentException("Source timestamps out of order.");

        var source = new JsonObject
        {
            ["provider"] = provider,
            ["source_uri"] = uri,
            ["source_document_id"] = sourceId,
            ["source_timestamp"] = RenderDate(sourceTime),
            ["published_at"] = RenderDate(published),
            ["retrieved_at"] = RenderDate(retrieved)
        };
        var identity = new JsonObject
        {
            ["provider"] = provider,
            ["sourceDocumentId"] = sourceId,
            ["sourceUri"] = uri
        };
        var documentId = "textdoc:" + Hash(identity);

        var participants = new JsonArray();
        var participantIds = new HashSet<string>(StringComparer.Ordinal);
        if (raw.TryGetProperty("participants", out var rawParticipants) &&
            rawParticipants.ValueKind != JsonValueKind.Null)
        {
            if (rawParticipants.ValueKind != JsonValueKind.Array)
                throw new ArgumentException("Participants must be an array.");
            foreach (var p in rawParticipants.EnumerateArray())
            {
                RequireKeys(p, "participant_id", "display_name");
                var id = Identifier(GetRequiredString(p, "participant_id"), "participant_id");
                if (!participantIds.Add(id))
                    throw new ArgumentException("Duplicate participant ID.");
                participants.Add(new JsonObject
                {
                    ["participant_id"] = id,
                    ["display_name"] = Required(GetRequiredString(p, "display_name"), "display_name"),
                    ["role"] = Optional(p, "role"),
                    ["organization"] = Optional(p, "organization")
                });
            }
        }

        var rawSegments = raw.GetProperty("segments");
        if (rawSegments.ValueKind != JsonValueKind.Array || rawSegments.GetArrayLength() == 0)
            throw new ArgumentException("At least one text segment is required.");
        var sorted = new SortedDictionary<int, (string? Participant, string Text)>();
        foreach (var item in rawSegments.EnumerateArray())
        {
            RequireKeys(item, "sequence", "text");
            var sequence = item.GetProperty("sequence").GetInt32();
            if (sequence <= 0 || sorted.ContainsKey(sequence))
                throw new ArgumentException("Segment sequences must be distinct positive integers.");
            var participant = OptionalIdentifier(item, "participant_id");
            if (participant is not null && !participantIds.Contains(participant))
                throw new ArgumentException("Unknown participant ID.");
            sorted.Add(sequence, (participant, Required(GetRequiredString(item, "text"), "text")));
        }

        var segments = new JsonArray();
        foreach (var (sequence, item) in sorted)
        {
            var segmentIdentity = new JsonObject
            {
                ["documentId"] = documentId,
                ["sequence"] = sequence,
                ["participantId"] = item.Participant,
                ["text"] = item.Text
            };
            segments.Add(new JsonObject
            {
                ["sequence"] = sequence,
                ["participant_id"] = item.Participant,
                ["text"] = item.Text,
                ["segment_id"] = "textseg:" + Hash(segmentIdentity)
            });
        }

        var fpSource = new JsonObject
        {
            ["provider"] = provider,
            ["sourceUri"] = uri,
            ["sourceDocumentId"] = sourceId,
            ["sourceTimestamp"] = RenderDate(sourceTime),
            ["publishedAt"] = RenderDate(published),
            ["retrievedAt"] = RenderDate(retrieved)
        };
        var fpParticipants = new JsonArray();
        foreach (var node in participants)
        {
            var p = node!.AsObject();
            fpParticipants.Add(new JsonObject
            {
                ["participantId"] = p["participant_id"]!.GetValue<string>(),
                ["displayName"] = p["display_name"]!.GetValue<string>(),
                ["role"] = p["role"]?.GetValue<string>(),
                ["organization"] = p["organization"]?.GetValue<string>()
            });
        }
        var fpSegments = new JsonArray();
        foreach (var node in segments)
        {
            var s = node!.AsObject();
            fpSegments.Add(new JsonObject
            {
                ["sequence"] = s["sequence"]!.GetValue<int>(),
                ["participantId"] = s["participant_id"]?.GetValue<string>(),
                ["text"] = s["text"]!.GetValue<string>()
            });
        }
        var fingerprint = Hash(new JsonObject
        {
            ["title"] = title,
            ["documentType"] = kind,
            ["source"] = fpSource,
            ["participants"] = fpParticipants,
            ["segments"] = fpSegments
        });
        return new JsonObject
        {
            ["document_id"] = documentId,
            ["title"] = title,
            ["document_type"] = kind,
            ["source"] = source,
            ["participants"] = participants,
            ["segments"] = segments,
            ["fingerprint"] = fingerprint
        };
    }

    private static void RequireKeys(JsonElement obj, params string[] mandatory)
    {
        if (obj.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Expected JSON object.");
        foreach (var name in mandatory)
            if (!obj.TryGetProperty(name, out _))
                throw new ArgumentException("Missing field: " + name);
    }

    private static string GetRequiredString(JsonElement obj, string key)
    {
        var element = obj.GetProperty(key);
        return element.ValueKind == JsonValueKind.String
            ? element.GetString()!
            : throw new ArgumentException("Expected string: " + key);
    }

    private static string Required(string text, string name)
    {
        var normalized = text.Replace("\r\n", "\n").Replace("\r", "\n").Trim();
        if (normalized.Length == 0)
            throw new ArgumentException("Empty field: " + name);
        return normalized;
    }

    private static string Identifier(string text, string name)
    {
        var value = Required(text, name);
        if (value.Contains('\n'))
            throw new ArgumentException("Multiline identity: " + name);
        return value;
    }

    private static string? Optional(JsonElement obj, string key)
    {
        if (!obj.TryGetProperty(key, out var v) || v.ValueKind == JsonValueKind.Null)
            return null;
        if (v.ValueKind != JsonValueKind.String)
            throw new ArgumentException("Expected optional string: " + key);
        var text = v.GetString()!.Replace("\r\n", "\n").Replace("\r", "\n").Trim();
        return text.Length == 0 ? null : text;
    }

    private static string? OptionalIdentifier(JsonElement obj, string key)
    {
        var result = Optional(obj, key);
        if (result?.Contains('\n') == true)
            throw new ArgumentException("Multiline identity: " + key);
        return result;
    }

    private static DateTimeOffset? Date(JsonElement obj, string key)
    {
        if (!obj.TryGetProperty(key, out var v) || v.ValueKind == JsonValueKind.Null)
            return null;
        if (v.ValueKind != JsonValueKind.String)
            throw new ArgumentException("Invalid date: " + key);
        var input = v.GetString()!;
        if (!input.EndsWith("Z", StringComparison.OrdinalIgnoreCase) &&
            !System.Text.RegularExpressions.Regex.IsMatch(input, @"[+-]\d{2}:\d{2}$"))
            throw new ArgumentException("Timestamp requires offset.");
        return DateTimeOffset.Parse(input, CultureInfo.InvariantCulture,
            DateTimeStyles.None).ToUniversalTime();
    }

    private static string? RenderDate(DateTimeOffset? date) =>
        date?.ToString("yyyy-MM-dd'T'HH:mm:ss.FFFFFF'Z'", CultureInfo.InvariantCulture);

    private static string Hash(JsonNode value)
    {
        var canonical = Canonical(value);
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(canonical)));
    }

    private static string Canonical(JsonNode? node)
    {
        if (node is null) return "null";
        if (node is JsonObject obj)
            return "{" + string.Join(",", obj.OrderBy(x => x.Key, StringComparer.Ordinal)
                .Select(x => JsonSerializer.Serialize(x.Key, JsonOptions) + ":" + Canonical(x.Value))) + "}";
        if (node is JsonArray arr)
            return "[" + string.Join(",", arr.Select(Canonical)) + "]";
        return node.ToJsonString(JsonOptions);
    }
}
