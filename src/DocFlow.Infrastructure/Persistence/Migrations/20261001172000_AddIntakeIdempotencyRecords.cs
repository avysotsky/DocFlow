using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261001172000_AddIntakeIdempotencyRecords")]
    public partial class AddIntakeIdempotencyRecords : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "IntakeIdempotencyRecords",
                columns: table => new
                {
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    Key = table.Column<string>(type: "character varying(128)", maxLength: 128, nullable: false),
                    RequestFingerprint = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: false),
                    Outcome = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    DocumentId = table.Column<Guid>(type: "uuid", nullable: true),
                    OriginalFileName = table.Column<string>(type: "character varying(512)", maxLength: 512, nullable: false),
                    DocumentStatus = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    DocumentCreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    DocumentDeleteAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    Error = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ExpiresAt = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey(
                        "PK_IntakeIdempotencyRecords",
                        x => new { x.CustomerId, x.Key });
                });

            migrationBuilder.CreateIndex(
                name: "IX_IntakeIdempotencyRecords_ExpiresAt",
                table: "IntakeIdempotencyRecords",
                column: "ExpiresAt");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "IntakeIdempotencyRecords");
        }
    }
}
