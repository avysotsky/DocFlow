FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

COPY . .
RUN dotnet restore src/DocFlow.Api/DocFlow.Api.csproj
RUN dotnet publish src/DocFlow.Api/DocFlow.Api.csproj \
    --configuration Release \
    --no-restore \
    --output /app/publish \
    /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:8.0-bookworm-slim AS runtime
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-venv \
        tesseract-ocr \
        tesseract-ocr-eng \
    && tessdata_dir="$(dirname "$(dpkg -L tesseract-ocr-eng | grep '/eng.traineddata$' | head -n 1)")" \
    && test -n "$tessdata_dir" \
    && ln -s "$tessdata_dir" /opt/tessdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app/publish ./
COPY src/DocFlow.Extraction.Worker /app/worker

RUN python3 -m venv /opt/docflow-venv \
    && /opt/docflow-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/docflow-venv/bin/pip install --no-cache-dir /app/worker \
    && mkdir -p /data/storage /app/worker/output \
    && chown -R app:app /data/storage /app/worker/output

ENV ASPNETCORE_URLS=http://+:8080 \
    FileStorage__RootPath=/data/storage \
    ExtractionWorker__RootPath=/app/worker \
    ExtractionWorker__PythonExecutable=/opt/docflow-venv/bin/python \
    TESSDATA_PREFIX=/opt/tessdata

EXPOSE 8080

USER app

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health/live || exit 1

ENTRYPOINT ["dotnet", "DocFlow.Api.dll"]
