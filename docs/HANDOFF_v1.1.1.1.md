# DocFlow — handoff после версии 1.1.1.1

Дата фиксации состояния: 2026-09-30  
Ветка-снимок: `DocFlow/v_1.1.1.1_Init`

Этот файл предназначен для переноса контекста в следующий чат/этап разработки. Он фиксирует текущее состояние проекта, проверенный сценарий и рекомендуемый следующий этап.

## 1. Назначение проекта

DocFlow — приватный коммерческий проект автоматической обработки бизнес-документов.

Целевой сценарий:

```text
PDF / scan / supplier quotation / invoice
        ↓
inspection
        ↓
text / OCR / layout / tables
        ↓
semantic structured extraction
        ↓
deterministic validation
        ↓
review if required
        ↓
PostgreSQL / Excel / CSV / external API / ERP
```

Главная ценность проекта — не «PDF → TXT», а преобразование разнородных документов поставщиков в нормализованные и проверенные бизнес-данные.

## 2. Текущий стек

### .NET

- .NET 8
- ASP.NET Core Web API
- EF Core 8
- Npgsql
- PostgreSQL 16
- Swagger / OpenAPI

### Python worker

- Python 3.11
- PyMuPDF
- pdfplumber
- Pydantic v2
- pytest

### CI

- `.github/workflows/dotnet-ci.yml`
- `.github/workflows/python-worker-ci.yml`

Обе части проекта собираются/проверяются через GitHub Actions.

## 3. Структура solution

```text
DocFlow.sln
src/
  DocFlow.Api/
  DocFlow.Application/
  DocFlow.Domain/
  DocFlow.Infrastructure/
  DocFlow.Extraction.Worker/
```

Архитектурная граница на текущем этапе:

- .NET API отвечает за application flow, storage, статусы документов и persistence.
- Python worker отвечает за parsing, semantic extraction и deterministic validation.
- Python не должен напрямую писать в PostgreSQL.

## 4. PostgreSQL и EF Core

База: `docflow`  
Роль приложения: `docflow_app`  
Локальная разработка использует PostgreSQL через SSH tunnel, локальный порт `55433`.

Пароль/connection string не хранить в Git. Используются User Secrets / локальная конфигурация.

### Entity `Document`

Основные поля:

- `Id`
- `CustomerId`
- `OriginalFileName`
- `ContentType`
- `StorageKey`
- `Size`
- `DocumentType`
- `Status`
- `CreatedAt`
- `ProcessedAt`
- `DeleteAt`

Статусы:

```text
Uploaded
Processing
Processed
NeedsReview
Failed
```

### Entity `ExtractionResult`

Поля:

- `Id`
- `DocumentId`
- `StructuredDataJson` (`jsonb`)
- `Confidence`
- `ValidationStatus`
- `CreatedAt`

Связь:

```text
Document 1 → 0..1 ExtractionResult
```

`DocumentId` имеет unique index.

Validation statuses в .NET:

```text
Pending
Valid
NeedsReview
Invalid
```

## 5. File storage

Файлы PDF не хранятся в PostgreSQL.

Текущая реализация:

- `IFileStorage`
- `LocalFileStorage`
- стандартный storage API: `src/DocFlow.Api/storage`

В БД сохраняется только metadata и `StorageKey`.

В будущем `IFileStorage` позволит заменить local storage на S3-compatible storage без изменения бизнес-логики.

## 6. API, реализованный к версии 1.1.1.1

### Upload document

```http
POST /api/documents
```

`multipart/form-data`:

- `customerId`
- `file`

Проверки:

- `CustomerId != Guid.Empty`
- файл не пустой
- максимум 20 MB
- расширение `.pdf`
- content type `application/pdf`
- сигнатура `%PDF-`

При успешной загрузке:

1. PDF сохраняется в `IFileStorage`.
2. создаётся `Document` со статусом `Uploaded`.
3. metadata сохраняется в PostgreSQL.
4. при ошибке БД выполняется compensation: загруженный файл удаляется из storage.

### Get document

```http
GET /api/documents/{id}
```

Возвращает metadata и текущий status документа.

### Save extraction result

```http
POST /api/documents/{id}/extraction-result
```

Назначение: принять `StructuredExtractionResult` от worker и сохранить его в `ExtractionResults`.

При валидном результате:

```text
Document.Status = Processed
Document.DocumentType = supplier_quotation
Document.ProcessedAt = UTC now
```

Если результат требует review, документ переводится в `NeedsReview`.

### Get extraction result

```http
GET /api/documents/{id}/extraction-result
```

Возвращает сохранённый structured JSON, confidence и validation status из PostgreSQL.

## 7. Python layout extraction

Основная provider-neutral модель находится в `docflow_worker/models.py`.

### Layout contracts

- `BoundingBox`
- `WordContent`
- `TextBlockContent`
- `TableContent`
- `PageContent`
- `DocumentContent`

`DocumentContent` содержит:

- pages
- derived full text
- page count
- pages with text
- empty page numbers
- `needs_ocr`
- table count

### `PdfContentExtractor`

Использует PyMuPDF для извлечения:

- page text
- text blocks
- words
- bounding boxes
- tables

Таблицы текущего digital quotation успешно обнаруживаются как structured tables.

Важно: semantic extraction использует не только `page.text`, а `DocumentContent` с blocks/tables. Это принципиально, потому что линейный raw text может иметь неправильный порядок элементов.

## 8. OCR

OCR пока НЕ реализован.

`DocumentContent.needs_ocr` уже определяет случай, когда PDF содержит страницы, но embedded text отсутствует.

Будущий flow:

```text
embedded text present → normal parser
embedded text absent  → OCR → DocumentContent → semantic extraction
```

Не подключать OCR до отдельного теста на scanned PDF.

## 9. Semantic extraction

Абстракция:

```text
StructuredExtractionEngine
```

Она принимает `DocumentContent`, а не простой raw string.

Это сделано для будущих вариантов:

- deterministic
- ONNX
- external LLM
- hybrid

### Реализованный engine

```text
DeterministicSupplierQuotationEngine
engine name: deterministic_supplier_quotation_v1
```

Он извлекает supplier quotation из распознанных tables и blocks.

### Semantic model `SupplierQuotationData`

Основные поля:

- `supplier_name`
- `quotation_number`
- `quotation_date`
- `valid_until`
- `currency`
- `customer_reference`
- `incoterms`
- `items[]`
- `subtotal`
- `vat_rate`
- `vat_amount`
- `total`
- `payment_terms`
- `delivery`
- `warranty`
- `notes`
- `prepared_by`
- `quote_status`

Каждый item содержит:

- `sku`
- `description`
- `quantity`
- `unit`
- `unit_price`
- `lead_time_days`
- `line_total`

Для количества и денежных значений используется `Decimal`.

## 10. Deterministic validation

Semantic extraction и validation разделены.

Extractor отвечает на вопрос:

> Что было извлечено из документа?

Validator отвечает:

> Согласуются ли извлечённые данные между собой?

Это позволяет в будущем применять один validator к deterministic, ONNX и LLM extraction results.

Текущие проверки:

```text
line_totals: quantity × unit_price = line_total
subtotal:    Σ line_total = subtotal
vat:         subtotal × vat_rate = vat_amount
grand_total: subtotal + vat_amount = total
```

Возможные validation statuses worker:

```text
valid
invalid
incomplete
```

`confidence` в текущем deterministic validator — доля успешно прошедших групп проверок. Для полностью корректного тестового quotation: `1.0`.

## 11. StructuredExtractionResult

Текущий provider-neutral результат содержит:

- `engine`
- `document_type`
- `data`
- `confidence`
- `validation_status`
- `validation`

`validation` содержит подробные checks со статусами `passed / failed / skipped`, message и details.

## 12. Python CLI

Рабочая директория Windows:

```text
D:\Projects\DocFlow\src\DocFlow.Extraction.Worker
```

Virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Проверенный запуск semantic extraction + validation:

```powershell
python main.py `
  --storage-root ..\DocFlow.Api\storage `
  --storage-key "2026/09/b58c49fe349f443680b7c32de204f624.pdf" `
  --document-type supplier_quotation `
  --output-structured-json quotation-structured.json
```

Проверенный результат:

```text
pageCount = 1
pagesWithText = 1
needsOcr = false
tableCount = 2
structuredEngine = deterministic_supplier_quotation_v1
structuredDocumentType = supplier_quotation
validationStatus = valid
confidence = 1.0
```

Generated files (`quotation-layout.json`, `quotation-structured.json`, extracted text, storage PDFs) не должны коммититься в Git.

## 13. Проверенный synthetic supplier quotation

Test customer id:

```text
11111111-1111-1111-1111-111111111111
```

Document id:

```text
e87c7f8d-ff45-4ab3-b8c6-6fcb0f1095c6
```

Storage key:

```text
2026/09/b58c49fe349f443680b7c32de204f624.pdf
```

Созданный ExtractionResult id:

```text
db60ec25-d86e-4b88-909e-c59d842c5940
```

### Извлечённые metadata

```text
Supplier: ACME Components Ltd.
Quotation: QT-2026-183
Quotation date: 2026-09-30
Valid until: 2026-10-15
Currency: EUR
Customer reference: RFQ-78421
Incoterms: DAP Odesa, Ukraine
```

### Items

```text
AX-100      20 × 12.50 = 250.00
BX-240       8 × 38.75 = 310.00
CBL-M12-05  30 ×  9.80 = 294.00
PSU-24V-120  6 × 46.00 = 276.00
SNS-PT100   12 × 27.25 = 327.00
```

### Totals

```text
Subtotal: 1457.00 EUR
VAT 20%:   291.40 EUR
Total:    1748.40 EUR
```

Все четыре группы deterministic validation прошли.

`POST /api/documents/{id}/extraction-result` успешно сохранил результат в PostgreSQL, а `GET /api/documents/{id}/extraction-result` успешно прочитал тот же structured result обратно.

Таким образом, версия 1.1.1.1 доказала ручной end-to-end pipeline от upload PDF до persisted validated business data.

## 14. Что НЕ реализовано к версии 1.1.1.1

Не считать эти функции готовыми:

- автоматический запуск Python worker после upload
- background processing orchestration
- OCR
- ONNX semantic extraction
- external LLM extraction
- hybrid fallback logic
- borderless quotation benchmark
- invoice extraction
- real dirty supplier PDF benchmark
- human review UI
- authentication / authorization
- billing
- Excel/CSV export
- S3 production storage
- RabbitMQ / Kafka
- Kubernetes
- Redis
- vector database / RAG

Не добавлять тяжёлую инфраструктуру до появления реальной необходимости.

## 15. Главная проблема текущей версии

Pipeline работает, но середина процесса пока ручная:

```text
Upload PDF
    ↓
Document = Uploaded
    ↓
[РУЧНО] запустить Python CLI
    ↓
[РУЧНО] получить quotation-structured.json
    ↓
[РУЧНО] POST JSON в .NET API
    ↓
ExtractionResult persisted
    ↓
Document = Processed / NeedsReview
```

Следующий этап должен убрать эти ручные действия.

# 16. Следующий этап разработки: automatic processing orchestration

## Цель

Пользователь выполняет только upload PDF. После этого DocFlow самостоятельно запускает extraction, validation и persistence.

Целевой flow:

```text
POST /api/documents
        ↓
Document = Uploaded
        ↓
enqueue processing
        ↓
Document = Processing
        ↓
Python worker
        ↓
StructuredExtractionResult
        ↓
.NET persistence
        ↓
Processed / NeedsReview / Failed
```

## Рекомендуемая реализация для следующего этапа

Не вводить RabbitMQ/Kafka на этом этапе.

Для локального MVP сначала реализовать простой .NET orchestration layer:

1. Вынести сохранение extraction result из controller в application service.
2. Добавить `IDocumentProcessingService` / аналогичную application abstraction.
3. Добавить background queue на базе `System.Threading.Channels` или эквивалентного простого механизма.
4. После успешного upload enqueue `DocumentId`.
5. Background worker переводит документ `Uploaded → Processing`.
6. .NET запускает Python worker через отдельный adapter/process runner (`ProcessStartInfo`), не из controller.
7. Python получает `StorageKey`, строит `StructuredExtractionResult` и отдаёт JSON.
8. .NET десериализует результат и сохраняет `ExtractionResult` через EF Core.
9. При `valid` → `Processed`.
10. При `invalid/incomplete` → `NeedsReview`.
11. При технической ошибке → `Failed` и логирование причины.
12. Обеспечить idempotency: повторный запуск не должен создавать второй `ExtractionResult` для того же `DocumentId`.

Дополнительно полезно сделать ручной endpoint для повторного запуска:

```http
POST /api/documents/{id}/process
```

Он пригодится для разработки, retry и будущего admin/review flow.

## Важные архитектурные правила следующего этапа

- Controller должен оставаться тонким.
- Не помещать запуск Python процесса непосредственно в controller.
- Python не пишет в PostgreSQL напрямую.
- Persistence остаётся ответственностью .NET.
- Не смешивать semantic extraction и deterministic validation.
- Не подключать LLM/ONNX до автоматизации существующего deterministic path.
- Не подключать message broker до появления реальной нагрузки/распределённого deployment.

## Критерий завершения следующего этапа

Следующий этап считается завершённым, когда можно выполнить только:

```text
POST PDF
```

и без ручного запуска Python и без ручного POST JSON через некоторое время получить:

```text
GET /api/documents/{id}
→ Status = Processed или NeedsReview

GET /api/documents/{id}/extraction-result
→ persisted StructuredExtractionResult
```

## После automation stage

После автоматизации нужно перейти к robustness benchmark:

1. digital quotation без рамок таблицы;
2. supplier invoice;
3. scanned PDF → OCR;
4. dirty/real supplier PDF;
5. только после этих тестов решать, где нужен ONNX/LLM fallback.

## 17. Рекомендуемая следующая Git-ветка

Предлагаемое имя, но ветку пока не создавать автоматически без отдельного решения:

```text
DocFlow/v_1.1.2.0_Automation
```

## 18. Что сделать в начале следующего чата

1. Прочитать этот файл целиком.
2. Проверить, что локальная рабочая копия находится на нужной development branch.
3. Запустить текущие `.NET CI` и `Python Worker CI`/локальные тесты при необходимости.
4. Не менять extraction algorithms до автоматизации orchestration.
5. Начать с выделения application service для persistence и processing workflow.

---

Состояние версии 1.1.1.1: первый ручной end-to-end business-document processing pipeline реализован и проверен. Следующий этап — убрать ручной мост между .NET upload, Python worker и .NET persistence.
