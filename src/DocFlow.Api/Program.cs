using DocFlow.Api.BackgroundServices;
using DocFlow.Application.Abstractions;
using DocFlow.Infrastructure.Persistence;
using DocFlow.Infrastructure.Processing;
using DocFlow.Infrastructure.Storage;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var connectionString = builder.Configuration.GetConnectionString("DocFlowDbContext")
    ?? throw new InvalidOperationException("Connection string 'DocFlowDbContext' was not found.");

builder.Services.AddDbContext<DocFlowDbContext>(options =>
    options.UseNpgsql(connectionString));

builder.Services.AddScoped<IExtractionResultService, ExtractionResultService>();
builder.Services.AddScoped<IDocumentProcessingService, DocumentProcessingService>();
builder.Services.AddSingleton<IDocumentProcessingQueue, DocumentProcessingQueue>();
builder.Services.AddHostedService<DocumentProcessingBackgroundService>();

var storageRoot = builder.Configuration["FileStorage:RootPath"] ?? "storage";
if (!Path.IsPathRooted(storageRoot))
    storageRoot = Path.Combine(builder.Environment.ContentRootPath, storageRoot);

builder.Services.AddSingleton<IFileStorage>(new LocalFileStorage(storageRoot));

var workerRoot = builder.Configuration["ExtractionWorker:RootPath"]
    ?? "../DocFlow.Extraction.Worker";
if (!Path.IsPathRooted(workerRoot))
    workerRoot = Path.Combine(builder.Environment.ContentRootPath, workerRoot);

var pythonExecutable = builder.Configuration["ExtractionWorker:PythonExecutable"];

builder.Services.AddSingleton<IDocumentExtractionRunner>(
    new PythonDocumentExtractionRunner(
        workerRoot,
        storageRoot,
        pythonExecutable));

var app = builder.Build();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseHttpsRedirection();
app.MapControllers();

app.Run();
