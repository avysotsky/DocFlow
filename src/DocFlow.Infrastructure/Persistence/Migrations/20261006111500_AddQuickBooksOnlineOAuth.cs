using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261006111500_AddQuickBooksOnlineOAuth")]
    public partial class AddQuickBooksOnlineOAuth : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "QuickBooksOnlineConnections",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    TargetKey = table.Column<string>(
                        type: "character varying(100)",
                        maxLength: 100,
                        nullable: false),
                    RealmId = table.Column<string>(
                        type: "character varying(200)",
                        maxLength: 200,
                        nullable: false),
                    ProtectedAccessToken = table.Column<string>(
                        type: "character varying(8192)",
                        maxLength: 8192,
                        nullable: false),
                    AccessTokenExpiresAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    ProtectedRefreshToken = table.Column<string>(
                        type: "character varying(8192)",
                        maxLength: 8192,
                        nullable: false),
                    RefreshTokenExpiresAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    ConnectedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_QuickBooksOnlineConnections", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "QuickBooksOnlineOAuthStates",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    TargetKey = table.Column<string>(
                        type: "character varying(100)",
                        maxLength: 100,
                        nullable: false),
                    StateHash = table.Column<string>(
                        type: "character varying(64)",
                        maxLength: 64,
                        nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    ExpiresAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false),
                    ConsumedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_QuickBooksOnlineOAuthStates", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "UX_QuickBooksOnlineConnections_TenantTarget",
                table: "QuickBooksOnlineConnections",
                columns: new[] { "CustomerId", "TargetKey" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_QuickBooksOnlineOAuthStates_ExpiresAt",
                table: "QuickBooksOnlineOAuthStates",
                column: "ExpiresAt");

            migrationBuilder.CreateIndex(
                name: "UX_QuickBooksOnlineOAuthStates_StateHash",
                table: "QuickBooksOnlineOAuthStates",
                column: "StateHash",
                unique: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "QuickBooksOnlineConnections");
            migrationBuilder.DropTable(name: "QuickBooksOnlineOAuthStates");
        }
    }
}
