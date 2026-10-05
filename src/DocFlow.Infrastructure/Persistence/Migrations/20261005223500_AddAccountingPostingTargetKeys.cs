using DocFlow.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DocFlow.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(DocFlowDbContext))]
    [Migration("20261005223500_AddAccountingPostingTargetKeys")]
    public partial class AddAccountingPostingTargetKeys : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "TargetKey",
                table: "AccountingPostingRecords",
                type: "character varying(100)",
                maxLength: 100,
                nullable: true);

            migrationBuilder.Sql(
                """
                UPDATE "AccountingPostingRecords"
                SET "TargetKey" = 'legacy'
                WHERE "TargetKey" IS NULL;
                """);

            migrationBuilder.AlterColumn<string>(
                name: "TargetKey",
                table: "AccountingPostingRecords",
                type: "character varying(100)",
                maxLength: 100,
                nullable: false,
                oldClrType: typeof(string),
                oldType: "character varying(100)",
                oldMaxLength: 100,
                oldNullable: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "TargetKey",
                table: "AccountingPostingRecords");
        }
    }
}
