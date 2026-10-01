using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261001182000_AddBatchIntakeIdempotencyRecords")]
    public partial class AddBatchIntakeIdempotencyRecords : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "BatchIntakeIdempotencyRecords",
                columns: table => new
                {
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    Key = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    RequestFingerprint = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    GenerationId = table.Column<Guid>(type: "uuid", nullable: false),
                    ResponseJson = table.Column<string>(type: "jsonb", nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ExpiresAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey(
                        "PK_BatchIntakeIdempotencyRecords",
                        x => new { x.CustomerId, x.Key });
                });

            migrationBuilder.CreateIndex(
                name: "IX_BatchIntakeIdempotencyRecords_ExpiresAt",
                table: "BatchIntakeIdempotencyRecords",
                column: "ExpiresAt");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "BatchIntakeIdempotencyRecords");
        }
    }
}
