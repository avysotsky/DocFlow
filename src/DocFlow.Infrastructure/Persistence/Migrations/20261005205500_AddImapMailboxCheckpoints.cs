using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005205500_AddImapMailboxCheckpoints")]
    public partial class AddImapMailboxCheckpoints : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ImapMailboxCheckpoints",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    MailboxKey = table.Column<string>(
                        type: "character varying(100)",
                        maxLength: 100,
                        nullable: false),
                    FolderName = table.Column<string>(
                        type: "character varying(255)",
                        maxLength: 255,
                        nullable: false),
                    UidValidity = table.Column<long>(type: "bigint", nullable: false),
                    LastUid = table.Column<long>(type: "bigint", nullable: false),
                    UpdatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ImapMailboxCheckpoints", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ImapMailboxCheckpoints_CustomerId_MailboxKey_FolderName",
                table: "ImapMailboxCheckpoints",
                columns: new[] { "CustomerId", "MailboxKey", "FolderName" },
                unique: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "ImapMailboxCheckpoints");
        }
    }
}
