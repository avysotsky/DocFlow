using System.Security.Cryptography;
using System.Text;
using DocFlow.Api.Observability;
using DocFlow.Application.Observability;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace DocFlow.Api.Controllers;

[ApiController]
[AllowAnonymous]
[Route("operations/metrics")]
public sealed class OperationalMetricsController : ControllerBase
{
    private readonly OperationalMetrics _metrics;
    private readonly OperationalMetricsOptions _options;

    public OperationalMetricsController(
        OperationalMetrics metrics,
        IOptions<OperationalMetricsOptions> options)
    {
        _metrics = metrics;
        _options = options.Value;
    }

    [HttpGet]
    [ProducesResponseType(typeof(OperationalMetricsSnapshot), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<OperationalMetricsSnapshot> Get()
    {
        if (!_options.Enabled)
            return NotFound();

        if (!Request.Headers.TryGetValue(OperationalMetricsOptions.HeaderName, out var values)
            || values.Count != 1
            || !FixedTimeEquals(_options.ApiKey, values[0]))
        {
            return Unauthorized();
        }

        return Ok(_metrics.Snapshot());
    }

    private static bool FixedTimeEquals(string expected, string actual)
    {
        if (string.IsNullOrEmpty(expected) || string.IsNullOrEmpty(actual))
            return false;

        var expectedBytes = Encoding.UTF8.GetBytes(expected);
        var actualBytes = Encoding.UTF8.GetBytes(actual);

        return expectedBytes.Length == actualBytes.Length
            && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
    }
}
