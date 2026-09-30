using System.Diagnostics;
using System.Text.Json;
using DocFlow.Application.Abstractions;
using DocFlow.Domain.Enums;

namespace DocFlow.Infrastructure.Processing;

public sealed class PythonDocumentExtractionRunner : IDocumentExtractionRunner
{
    private readonly string _workerRootPath;
    private readonly string _storageRootPath;
    private readonly string _pythonExecutable;

    public PythonDocumentExtractionRunner(
        string workerRootPath,
        string storageRootPath,
        string? pythonExecutable = null)
    {
        if (string.IsNullOrWhiteSpace(workerRootPath))
            throw new ArgumentException("Worker root path is required.", nameof(workerRootPath));
        if (string.IsNullOrWhiteSpace(storageRootPath))
            throw new ArgumentException("Storage root path is required.", nameof(storageRootPath));

        _workerRootPath = Path.GetFullPath(workerRootPath);
        _storageRootPath = Path.GetFullPath(storageRootPath);
        _pythonExecutable = ResolvePythonExecutable(_workerRootPath, pythonExecutable);

        if (!File.Exists(Path.Combine(_workerRootPath, "main.py")))
            throw new DirectoryNotFoundException(
                $"Python worker main.py was not found under '{_workerRootPath}'.");
    }

    public async Task<DocumentExtractionResult> RunAsync(
        string storageKey,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(storageKey))
            throw new ArgumentException("Storage key is required.", nameof(storageKey));

        var outputFileName = $"automation-{Guid.NewGuid():N}.json";
        var outputPath = Path.Combine(_workerRootPath, "output", outputFileName);

        var startInfo = new ProcessStartInfo
        {
            FileName = _pythonExecutable,
            WorkingDirectory = _workerRootPath,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        startInfo.ArgumentList.Add("main.py");
        startInfo.ArgumentList.Add("--storage-root");
        startInfo.ArgumentList.Add(_storageRootPath);
        startInfo.ArgumentList.Add("--storage-key");
        startInfo.ArgumentList.Add(storageKey);
        startInfo.ArgumentList.Add("--document-type");
        startInfo.ArgumentList.Add("auto");
        startInfo.ArgumentList.Add("--output-structured-json");
        startInfo.ArgumentList.Add(outputFileName);

        using var process = new Process { StartInfo = startInfo };

        try
        {
            if (!process.Start())
                throw new InvalidOperationException("Python extraction worker could not be started.");

            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();

            try
            {
                await process.WaitForExitAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                if (!process.HasExited)
                    process.Kill(entireProcessTree: true);

                await Task.WhenAll(stdoutTask, stderrTask);
                throw;
            }

            var stdout = await stdoutTask;
            var stderr = await stderrTask;

            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException(
                    $"Python extraction worker failed with exit code {process.ExitCode}. " +
                    $"stderr: {stderr.Trim()} stdout: {stdout.Trim()}");
            }

            if (!File.Exists(outputPath))
            {
                throw new InvalidOperationException(
                    $"Python extraction worker completed without producing '{outputPath}'. " +
                    $"stdout: {stdout.Trim()} stderr: {stderr.Trim()}");
            }

            var structuredDataJson = await File.ReadAllTextAsync(outputPath, cancellationToken);
            return ParseStructuredResult(structuredDataJson);
        }
        finally
        {
            if (File.Exists(outputPath))
                File.Delete(outputPath);
        }
    }

    private static DocumentExtractionResult ParseStructuredResult(string structuredDataJson)
    {
        using var document = JsonDocument.Parse(structuredDataJson);
        var root = document.RootElement;

        if (root.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException("Structured extraction result must be a JSON object.");

        if (!TryGetRequiredString(root, "engine", out _))
            throw new InvalidOperationException("Structured extraction result does not contain a valid engine.");

        if (!TryGetRequiredString(root, "document_type", out var documentType))
            throw new InvalidOperationException("Structured extraction result does not contain a valid document_type.");

        if (!root.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException("Structured extraction result does not contain object-valued data.");

        if (!TryGetRequiredString(root, "validation_status", out var validationStatusText))
            throw new InvalidOperationException("Structured extraction result does not contain validation_status.");

        var validationStatus = validationStatusText.ToLowerInvariant() switch
        {
            "valid" => ValidationStatus.Valid,
            "invalid" => ValidationStatus.Invalid,
            "incomplete" => ValidationStatus.NeedsReview,
            _ => throw new InvalidOperationException(
                $"Unsupported validation_status '{validationStatusText}'.")
        };

        decimal? confidence = null;
        if (root.TryGetProperty("confidence", out var confidenceElement)
            && confidenceElement.ValueKind != JsonValueKind.Null)
        {
            if (confidenceElement.ValueKind != JsonValueKind.Number
                || !confidenceElement.TryGetDecimal(out var parsedConfidence)
                || parsedConfidence is < 0 or > 1)
            {
                throw new InvalidOperationException(
                    "Structured extraction confidence must be null or a number between 0 and 1.");
            }

            confidence = parsedConfidence;
        }

        return new DocumentExtractionResult(
            structuredDataJson,
            documentType,
            confidence,
            validationStatus);
    }

    private static bool TryGetRequiredString(
        JsonElement root,
        string propertyName,
        out string value)
    {
        value = string.Empty;

        if (!root.TryGetProperty(propertyName, out var element)
            || element.ValueKind != JsonValueKind.String)
        {
            return false;
        }

        var text = element.GetString();
        if (string.IsNullOrWhiteSpace(text))
            return false;

        value = text.Trim();
        return true;
    }

    private static string ResolvePythonExecutable(
        string workerRootPath,
        string? configuredExecutable)
    {
        if (!string.IsNullOrWhiteSpace(configuredExecutable))
        {
            var configured = configuredExecutable.Trim();

            if (Path.IsPathRooted(configured))
                return configured;

            if (configured.Contains(Path.DirectorySeparatorChar)
                || configured.Contains(Path.AltDirectorySeparatorChar))
            {
                return Path.GetFullPath(Path.Combine(workerRootPath, configured));
            }

            return configured;
        }

        var windowsVenv = Path.Combine(workerRootPath, ".venv", "Scripts", "python.exe");
        if (File.Exists(windowsVenv))
            return windowsVenv;

        var unixVenv = Path.Combine(workerRootPath, ".venv", "bin", "python");
        if (File.Exists(unixVenv))
            return unixVenv;

        return OperatingSystem.IsWindows() ? "python" : "python3";
    }
}
