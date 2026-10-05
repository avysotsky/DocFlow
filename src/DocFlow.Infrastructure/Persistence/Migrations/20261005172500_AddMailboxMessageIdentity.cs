using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005172500_AddMailboxMessageIdentity")]
    public partial class AddMailboxMessageIdentity : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "MailboxMessages",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CustomerId = table.Column<Guid>(type: "uuid", nullable: false),
                    MessageIdentity = table.Column<string>(
                        type: "character varying(512)",
                        maxLength: 512,
                        nullable: false),
                    RawMessageSha256 = table.Column<string>(
                        type: "character varying(64)",
                        maxLength: 64,
                        nullable: false),
                    InternetMessageId = table.Column<string>(
                        type: "character varying(998)",
                        maxLength: 998,
                        nullable: true),
                    Sender = table.Column<string>(
                        type: "character varying(512)",
                        maxLength: 512,
                        nullable: true),
                    Subject = table.Column<string>(
                        type: "character varying(998)",
                        maxLength: 998,
                        nullable: true),
                    ReceivedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: true),
                    CreatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MailboxMessages", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "MailboxAttachments",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    MailboxMessageId = table.Column<Guid>(type: "uuid", nullable: false),
                    Ordinal = table.Column<int>(type: "integer", nullable: false),
                    FileName = table.Column<string>(
                        type: "character varying(512)",
                        maxLength: 512,
                        nullable: false),
                    ContentType = table.Column<string>(
                        type: "character varying(100)",
                        maxLength: 100,
                        nullable: false),
                    Size = table.Column<long>(type: "bigint", nullable: false),
                    Sha256 = table.Column<string>(
                        type: "character varying(64)",
                        maxLength: 64,
                        nullable: false),
                    CreatedAt = table.Column<DateTimeOffset>(
                        type: "timestamp with time zone",
                        nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MailboxAttachments", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MailboxAttachments_MailboxMessages_MailboxMessageId",
                        column: x => x.MailboxMessageId,
                        principalTable: "MailboxMessages",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_MailboxMessages_CustomerId_CreatedAt",
                table: "MailboxMessages",
                columns: new[] { "CustomerId", "CreatedAt" });

            migrationBuilder.CreateIndex(
                name: "IX_MailboxMessages_CustomerId_MessageIdentity",
                table: "MailboxMessages",
                columns: new[] { "CustomerId", "MessageIdentity" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MailboxAttachments_MailboxMessageId_Ordinal",
                table: "MailboxAttachments",
                columns: new[] { "MailboxMessageId", "Ordinal" },
                unique: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "MailboxAttachments");
            migrationBuilder.DropTable(name: "MailboxMessages");
        }
    }
}
