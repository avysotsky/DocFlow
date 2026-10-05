using System;
using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005180500_LinkMailboxAttachmentsToDocuments")]
    public partial class LinkMailboxAttachmentsToDocuments : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<Guid>(
                name: "DocumentId",
                table: "MailboxAttachments",
                type: "uuid",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_MailboxAttachments_DocumentId",
                table: "MailboxAttachments",
                column: "DocumentId");

            migrationBuilder.AddForeignKey(
                name: "FK_MailboxAttachments_Documents_DocumentId",
                table: "MailboxAttachments",
                column: "DocumentId",
                principalTable: "Documents",
                principalColumn: "Id",
                onDelete: ReferentialAction.SetNull);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_MailboxAttachments_Documents_DocumentId",
                table: "MailboxAttachments");

            migrationBuilder.DropIndex(
                name: "IX_MailboxAttachments_DocumentId",
                table: "MailboxAttachments");

            migrationBuilder.DropColumn(
                name: "DocumentId",
                table: "MailboxAttachments");
        }
    }
}
