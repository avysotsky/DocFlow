using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005113000_AddReconciliationCases")]
    public partial class AddReconciliationCases : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ReconciliationCases",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    InvoiceDocumentId = table.Column<Guid>(type: "uuid", nullable: false),
                    PurchaseOrderDocumentId = table.Column<Guid>(type: "uuid", nullable: false),
                    ReconciliationStatus = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: false),
                    ReviewStatus = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: false),
                    ReportJson = table.Column<string>(type: "jsonb", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    CreatedByClient = table.Column<string>(
                        type: "character varying(200)",
                        maxLength: 200,
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ReconciliationCases", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ReconciliationCases_Documents_InvoiceDocumentId",
                        column: x => x.InvoiceDocumentId,
                        principalTable: "Documents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                    table.ForeignKey(
                        name: "FK_ReconciliationCases_Documents_PurchaseOrderDocumentId",
                        column: x => x.PurchaseOrderDocumentId,
                        principalTable: "Documents",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ReconciliationCases_CustomerId_CreatedAt",
                table: "ReconciliationCases",
                columns: new[] { "CustomerId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_ReconciliationCases_InvoiceDocumentId",
                table: "ReconciliationCases",
                column: "InvoiceDocumentId");

            migrationBuilder.CreateIndex(
                name: "IX_ReconciliationCases_PurchaseOrderDocumentId",
                table: "ReconciliationCases",
                column: "PurchaseOrderDocumentId");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ReconciliationCases");
        }
    }
}
