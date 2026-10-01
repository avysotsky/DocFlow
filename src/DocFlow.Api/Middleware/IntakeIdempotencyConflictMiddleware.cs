using DocFlow.Api.Documents;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Middleware;

public sealed class IntakeIdempotencyConflictMiddleware
{
    private readonly RequestDelegate _next;

    public IntakeIdempotencyConflictMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        try
        {
            await _next(context);
        }
        catch (IntakeIdempotencyConflictException exception) when (!context.Response.HasStarted)
        {
            context.Response.StatusCode = StatusCodes.Status409Conflict;
            context.Response.ContentType = "application/problem+json";

            await context.Response.WriteAsJsonAsync(new ProblemDetails
            {
                Status = StatusCodes.Status409Conflict,
                Title = "Idempotency conflict.",
                Detail = exception.Message
            });
        }
    }
}
