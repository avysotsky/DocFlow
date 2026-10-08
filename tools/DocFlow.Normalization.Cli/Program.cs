using System.Text.Json;
using DocFlow.Normalization;

try
{
    using var input = JsonDocument.Parse(await Console.In.ReadToEndAsync());
    var normalized = TextDocumentNormalizer.Normalize(input.RootElement);
    Console.WriteLine(normalized.ToJsonString());
    return 0;
}
catch (Exception error) when (error is ArgumentException or JsonException or InvalidOperationException)
{
    Console.Error.WriteLine("Invalid document.");
    return 2;
}
