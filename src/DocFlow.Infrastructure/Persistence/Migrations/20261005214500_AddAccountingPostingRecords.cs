using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005214500_AddAccountingPostingRecords")]
    public partial class AddAccountingPostingRecords : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "AccountingPostingRecords",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    DocumentId = table.Column<Guid>(type: "uuid", nullable: false),
                    Provider = table.Column<string>(
                        type: "character varying(64)",
                        maxLength: 64,
                        nullable: false),
                    TargetAccount = table.Column<string>(
                        type: "character varying(200)",
                        maxLength: 200,
                        nullable: false),
                    IdempotencyKey = table.Column<string>(
                        type: "character varying(128)",
                        maxLength: 128,
                        nullable: false),
                    PayloadJson = table.Column<string>(
                        type: "jsonb",
                        nullable: false),
                    Status = table.Column<string>(
                        type: "character varying(32)",
                        maxLength: 32,
                        nullable: false),
                    Attempts = table.Column<int>(type: "integer", nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    LastAttemptAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: true),
                    NextAttemptAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: true),
                    LastError = table.Column<string>(
                        type: "character varying(500)",
                        maxLength: 500,
                        nullable: true),
                    ExternalReference = table.Column<string>(
                        type: "character varying(200)",
                        maxLength: 200,
                        nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AccountingPostingRecords", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_AccountingPostingRecords_DocumentId",
                table: "AccountingPostingRecords",
                column: "DocumentId");

            migrationBuilder.CreateIndex(
                name: "IX_AccountingPostingRecords_NextAttemptAt",
                table: "AccountingPostingRecords",
                column: "NextAttemptAt");

            migrationBuilder.CreateIndex(
                name: "UX_AccountingPostingRecords_Idempotency",
                table: "AccountingPostingRecords",
                columns: new[]
                {
                    "CustomerId",
                    "Provider",
                    "TargetAccount",
                    "IdempotencyKey"
                },
                unique: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "AccountingPostingRecords");
        }
    }
}
