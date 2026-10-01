using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261001133000_AddDocumentProcessingDiagnostics")]
    public partial class AddDocumentProcessingDiagnostics : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTimeOffset>(
                name: "LastProcessingAttemptAt",
                table: "Documents",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "LastProcessingError",
                table: "Documents",
                type: "character varying(1000)",
                maxLength: 1000,
                nullable: true);

            migrationBuilder.AddColumn<DateTimeOffset>(
                name: "LastProcessingFailureAt",
                table: "Documents",
                type: "timestamp with time zone",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "ProcessingAttempts",
                table: "Documents",
                type: "integer",
                nullable: false,
                defaultValue: 0);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "LastProcessingAttemptAt",
                table: "Documents");

            migrationBuilder.DropColumn(
                name: "LastProcessingError",
                table: "Documents");

            migrationBuilder.DropColumn(
                name: "LastProcessingFailureAt",
                table: "Documents");

            migrationBuilder.DropColumn(
                name: "ProcessingAttempts",
                table: "Documents");
        }
    }
}
