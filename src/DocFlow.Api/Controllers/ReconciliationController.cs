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
    private readonly IReconciliationCaseService _caseService;

    public ReconciliationController(
        IInvoicePurchaseOrderReconciliationService service,
        IReconciliationCaseService caseService)
    {
        _service = service;
        _caseService = caseService;
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


    [HttpPost("invoice-po/cases")]
    [Consumes("application/json")]
    [ProducesResponseType(typeof(ReconciliationCaseSnapshot), StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ReconciliationCaseSnapshot>> CreateInvoicePoCase(
        [FromBody] InvoicePoReconciliationRequest request,
        CancellationToken cancellationToken)
    {
        if (request.InvoiceDocumentId == Guid.Empty)
            return BadRequest("Invoice document id is required.");
        if (request.PurchaseOrderDocumentId == Guid.Empty)
            return BadRequest("Purchase-order document id is required.");
        if (request.InvoiceDocumentId == request.PurchaseOrderDocumentId)
            return BadRequest("Invoice and purchase-order document ids must be different.");

        var result = await _caseService.CreateAsync(
            User.GetRequiredCustomerId(),
            request.InvoiceDocumentId,
            request.PurchaseOrderDocumentId,
            User.GetRequiredClientName(),
            cancellationToken);

        return result.Outcome switch
        {
            InvoicePoReconciliationOutcome.Completed => CreatedAtAction(
                nameof(GetCase),
                new { caseId = result.Case!.Id },
                result.Case),
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

    [HttpGet("cases/{caseId:guid}")]
    [ProducesResponseType(typeof(ReconciliationCaseSnapshot), StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ReconciliationCaseSnapshot>> GetCase(
        Guid caseId,
        CancellationToken cancellationToken)
    {
        if (caseId == Guid.Empty)
            return NotFound();

        var snapshot = await _caseService.GetAsync(
            User.GetRequiredCustomerId(),
            caseId,
            cancellationToken);

        return snapshot is null ? NotFound() : Ok(snapshot);
    }

    public sealed record InvoicePoReconciliationRequest(
        Guid InvoiceDocumentId,
        Guid PurchaseOrderDocumentId);
}
