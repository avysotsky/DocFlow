using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005164500_AddReconciliationCaseAuditEvents")]
    public partial class AddReconciliationCaseAuditEvents : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ReconciliationCaseAuditEvents",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    ReconciliationCaseId = table.Column<Guid>(type: "uuid", nullable: false),
                    Action = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: false),
                    PreviousStatus = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: true),
                    NewStatus = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: false),
                    Note = table.Column<string>(
                        type: "character varying(2000)",
                        maxLength: 2000,
                        nullable: true),
                    PerformedByClient = table.Column<string>(
                        type: "character varying(200)",
                        maxLength: 200,
                        nullable: false),
                    OccurredAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ReconciliationCaseAuditEvents", x => x.Id);
                    table.ForeignKey(
                        name: "FK_ReconciliationCaseAuditEvents_ReconciliationCases_ReconciliationCaseId",
                        column: x => x.ReconciliationCaseId,
                        principalTable: "ReconciliationCases",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ReconciliationCaseAuditEvents_ReconciliationCaseId_OccurredAt",
                table: "ReconciliationCaseAuditEvents",
                columns: new[] { "ReconciliationCaseId", "OccurredAt" });
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ReconciliationCaseAuditEvents");
        }
    }
}
