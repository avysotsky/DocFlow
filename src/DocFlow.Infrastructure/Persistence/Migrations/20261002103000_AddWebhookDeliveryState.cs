using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261002103000_AddWebhookDeliveryState")]
    public partial class AddWebhookDeliveryState : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTimeOffset>(name: "DeliveredAt", table: "DocumentCompletionOutbox", type: "timestamp with time zone", nullable: true);
            migrationBuilder.AddColumn<DateTimeOffset>(name: "DeliveryAbandonedAt", table: "DocumentCompletionOutbox", type: "timestamp with time zone", nullable: true);
            migrationBuilder.AddColumn<int>(name: "DeliveryAttempts", table: "DocumentCompletionOutbox", type: "integer", nullable: false, defaultValue: 0);
            migrationBuilder.AddColumn<string>(name: "LastDeliveryError", table: "DocumentCompletionOutbox", type: "character varying(500)", maxLength: 500, nullable: true);
            migrationBuilder.AddColumn<DateTimeOffset>(name: "LastDeliveryAttemptAt", table: "DocumentCompletionOutbox", type: "timestamp with time zone", nullable: true);
            migrationBuilder.AddColumn<DateTimeOffset>(name: "NextDeliveryAttemptAt", table: "DocumentCompletionOutbox", type: "timestamp with time zone", nullable: true);

            migrationBuilder.Sql(
                """
                UPDATE "DocumentCompletionOutbox"
                SET "NextDeliveryAttemptAt" = "OccurredAt"
                WHERE "NextDeliveryAttemptAt" IS NULL;
                """);

            migrationBuilder.CreateIndex(
                name: "IX_DocumentCompletionOutbox_NextDeliveryAttemptAt",
                table: "DocumentCompletionOutbox",
                column: "NextDeliveryAttemptAt");
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(name: "IX_DocumentCompletionOutbox_NextDeliveryAttemptAt", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "DeliveredAt", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "DeliveryAbandonedAt", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "DeliveryAttempts", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "LastDeliveryError", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "LastDeliveryAttemptAt", table: "DocumentCompletionOutbox");
            migrationBuilder.DropColumn(name: "NextDeliveryAttemptAt", table: "DocumentCompletionOutbox");
        }
    }
}
