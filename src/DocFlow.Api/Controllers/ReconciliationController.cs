using DocFlow.Api.Authentication;
using DocFlow.Application.Abstractions;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DocFlow.Api.Controllers;

[ApiController]
[Authorize]
[Route("api/reconciliation")]
public sealed class ReconciliationController : ControllerBase
{
    private readonly IInvoicePurchaseOrderReconciliationService _service;

    public ReconciliationController(
        IInvoicePurchaseOrderReconciliationService service)
    {
        _service = service;
    }

    [HttpPost("invoice-po")]
    [Consumes("application/json")]
    [ProducesResponseType(typeof(InvoicePoReconciliationReport), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<InvoicePoReconciliationReport>> ReconcileInvoiceToPo(
        [FromBody] InvoicePoReconciliationRequest request,
        CancellationToken cancellationToken)
    {
        if (request.InvoiceDocumentId == Guid.Empty)
            return BadRequest("Invoice document id is required.");
        if (request.PurchaseOrderDocumentId == Guid.Empty)
            return BadRequest("Purchase-order document id is required.");
        if (request.InvoiceDocumentId == request.PurchaseOrderDocumentId)
            return BadRequest("Invoice and purchase-order document ids must be different.");

        var result = await _service.ReconcileAsync(
            User.GetRequiredCustomerId(),
            request.InvoiceDocumentId,
            request.PurchaseOrderDocumentId,
            cancellationToken);

        return result.Outcome switch
        {
            InvoicePoReconciliationOutcome.Completed => Ok(result.Report!),
            InvoicePoReconciliationOutcome.InvoiceNotFound => NotFound(
                "Invoice document was not found for the authenticated tenant."),
            InvoicePoReconciliationOutcome.PurchaseOrderNotFound => NotFound(
                "Purchase-order document was not found for the authenticated tenant."),
            InvoicePoReconciliationOutcome.InvoiceExtractionResultNotFound => NotFound(
                "Invoice extraction result was not found."),
            InvoicePoReconciliationOutcome.PurchaseOrderExtractionResultNotFound => NotFound(
                "Purchase-order extraction result was not found."),
            InvoicePoReconciliationOutcome.InvalidInvoiceDocumentType => BadRequest(
                "Invoice document must have document type 'supplier_invoice'."),
            InvoicePoReconciliationOutcome.InvalidPurchaseOrderDocumentType => BadRequest(
                "Purchase-order document must have document type 'purchase_order'."),
            _ => throw new InvalidOperationException(
                $"Unsupported reconciliation outcome '{result.Outcome}'.")
        };
    }

    public sealed record InvoicePoReconciliationRequest(
        Guid InvoiceDocumentId,
        Guid PurchaseOrderDocumentId);
}
