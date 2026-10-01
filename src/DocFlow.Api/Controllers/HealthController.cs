using DocFlow.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DocFlow.Api.Controllers;

[ApiController]
[AllowAnonymous]
[Route("health")]
public sealed class HealthController : ControllerBase
{
    private readonly DocFlowDbContext _dbContext;
    private readonly IConfiguration _configuration;
    private readonly IWebHostEnvironment _environment;
    private readonly ILogger<HealthController> _logger;

    public HealthController(
        DocFlowDbContext dbContext,
        IConfiguration configuration,
        IWebHostEnvironment environment,
        ILogger<HealthController> logger)
    {
        _dbContext = dbContext;
        _configuration = configuration;
        _environment = environment;
        _logger = logger;
    }

    [HttpGet("live")]
    [ProducesResponseType(typeof(HealthResponse), StatusCodes.Status200OK)]
    public ActionResult<HealthResponse> Live()
    {
        return Ok(new HealthResponse("Healthy"));
    }

    [HttpGet("ready")]
    [ProducesResponseType(typeof(HealthResponse), StatusCodes.Status200OK)]
    [ProducesResponseType(typeof(HealthResponse), StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<HealthResponse>> Ready(CancellationToken cancellationToken)
    {
        try
        {
            if (!await _dbContext.Database.CanConnectAsync(cancellationToken))
                return StatusCode(StatusCodes.Status503ServiceUnavailable, new HealthResponse("Unhealthy"));

            var storageRoot = ResolvePath("FileStorage:RootPath", "storage");
            if (!Directory.Exists(storageRoot))
                return StatusCode(StatusCodes.Status503ServiceUnavailable, new HealthResponse("Unhealthy"));

            var workerRoot = ResolvePath(
                "ExtractionWorker:RootPath",
                "../DocFlow.Extraction.Worker");
            if (!System.IO.File.Exists(Path.Combine(workerRoot, "main.py")))
                return StatusCode(StatusCodes.Status503ServiceUnavailable, new HealthResponse("Unhealthy"));

            var pythonExecutable = _configuration["ExtractionWorker:PythonExecutable"];
            if (!string.IsNullOrWhiteSpace(pythonExecutable)
                && Path.IsPathRooted(pythonExecutable)
                && !System.IO.File.Exists(pythonExecutable))
            {
                return StatusCode(StatusCodes.Status503ServiceUnavailable, new HealthResponse("Unhealthy"));
            }

            return Ok(new HealthResponse("Healthy"));
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception)
        {
            _logger.LogWarning(exception, "DocFlow readiness probe failed.");
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new HealthResponse("Unhealthy"));
        }
    }

    private string ResolvePath(string configurationKey, string fallback)
    {
        var configured = _configuration[configurationKey];
        var path = string.IsNullOrWhiteSpace(configured) ? fallback : configured.Trim();

        return Path.IsPathRooted(path)
            ? Path.GetFullPath(path)
            : Path.GetFullPath(Path.Combine(_environment.ContentRootPath, path));
    }

    public sealed record HealthResponse(string Status);
}
