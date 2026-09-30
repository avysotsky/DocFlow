# DocFlow — handoff для версии 1.1.1.2 Automation

Дата начала этапа: 2026-09-30  
Рабочая ветка: `DocFlow/v_1.1.1.2_Automation`

Этот файл является рабочим handoff для следующего этапа разработки. Исторический снимок завершённой версии 1.1.1.1 остаётся в:

```text
docs/HANDOFF_v1.1.1.1.md
```

## 1. Откуда продолжаем

Версия 1.1.1.1 уже доказала ручной end-to-end pipeline:

```text
POST PDF
  ↓
LocalFileStorage + Document metadata
  ↓
Python layout extraction
  ↓
deterministic semantic extraction
  ↓
deterministic validation
  ↓
StructuredExtractionResult
  ↓
ручной POST в .NET API
  ↓
ExtractionResults в PostgreSQL
  ↓
GET результата обратно из PostgreSQL
```

Проверенный supplier quotation завершился со значениями:

```text
Document type: supplier_quotation
Engine: deterministic_supplier_quotation_v1
Validation status: valid
Confidence: 1.0
Subtotal: 1457.00 EUR
VAT 20%: 291.40 EUR
Total: 1748.40 EUR
Items checked: 5
```

Проверенный DocumentId:

```text
e87c7f8d-ff45-4ab3-b8c6-6fcb0f1095c6
```

Проверенный ExtractionResultId:

```text
db60ec25-d86e-4b88-909e-c59d842c5940
```

## 2. Текущая архитектурная граница

### .NET

Отвечает за:

- ASP.NET Core API;
- application flow;
- document statuses;
- file storage abstraction;
- EF Core persistence;
- PostgreSQL;
- сохранение `ExtractionResult`.

### Python worker

Отвечает за:

- PDF parsing;
- layout extraction;
- tables / blocks / words;
- semantic extraction;
- deterministic validation.

Ключевое правило:

> Python worker не пишет напрямую в PostgreSQL. Persistence остаётся ответственностью .NET.

## 3. Что уже реализовано

### API

```http
POST /api/documents
GET  /api/documents/{id}
POST /api/documents/{id}/extraction-result
GET  /api/documents/{id}/extraction-result
```

### Document statuses

```text
Uploaded
Processing
Processed
NeedsReview
Failed
```

### Extraction validation statuses в .NET

```text
Pending
Valid
NeedsReview
Invalid
```

### Python semantic result

`StructuredExtractionResult` содержит:

- `engine`;
- `document_type`;
- `data`;
- `confidence`;
- `validation_status`;
- `validation`.

### Deterministic validation

Проверяются:

```text
line_totals: quantity × unit_price = line_total
subtotal:    Σ line_total = subtotal
vat:         subtotal × vat_rate = vat_amount
grand_total: subtotal + vat_amount = total
```

## 4. Runtime output worker

Локальные результаты обработки должны находиться в:

```text
src/DocFlow.Extraction.Worker/output/
```

Содержимое этой папки игнорируется Git. Папка сохраняется через `.gitkeep`.

Также игнорируется:

```text
*.egg-info/
```

Generated extraction outputs не коммитить.

## 5. Главная проблема текущего состояния

Середина pipeline пока ручная:

```text
Upload PDF
    ↓
Document = Uploaded
    ↓
[РУЧНО] запустить Python CLI
    ↓
[РУЧНО] получить StructuredExtractionResult JSON
    ↓
[РУЧНО] POST JSON в .NET API
    ↓
ExtractionResult persisted
    ↓
Processed / NeedsReview
```

Цель версии 1.1.1.2 — убрать эти ручные действия.

# 6. Цель версии 1.1.1.2 Automation

Пользователь должен выполнить только upload PDF.

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
Python worker запускается автоматически
        ↓
StructuredExtractionResult
        ↓
.NET сохраняет ExtractionResult
        ↓
Processed / NeedsReview / Failed
```

После завершения этапа пользователь не должен вручную запускать Python CLI и вручную отправлять extraction JSON через Swagger.

# 7. План реализации по шагам

## Шаг 1. Вынести persistence extraction result из controller

Сейчас `DocumentsController` содержит слишком много orchestration/persistence логики.

Нужно создать application service, который будет отвечать за сохранение результата обработки документа.

Рекомендуемая abstraction:

```text
IExtractionResultService
```

или аналогичное имя, если при реализации появится более удачная граница ответственности.

Service должен:

1. найти `Document`;
2. проверить, существует ли уже `ExtractionResult`;
3. создать `ExtractionResult`;
4. определить итоговый status документа;
5. сохранить изменения через EF Core.

Controller должен только принять HTTP request и вызвать application service.

## Шаг 2. Добавить processing abstraction

Создать application abstraction:

```text
IDocumentProcessingService
```

Ответственность:

```text
DocumentId
  ↓
загрузить metadata
  ↓
MarkProcessing
  ↓
запустить extraction adapter
  ↓
получить StructuredExtractionResult
  ↓
сохранить результат
  ↓
Processed / NeedsReview / Failed
```

## Шаг 3. Создать adapter для запуска Python worker

Не запускать `ProcessStartInfo` прямо из controller или application service.

Создать abstraction, например:

```text
IDocumentExtractionRunner
```

Infrastructure implementation:

```text
PythonDocumentExtractionRunner
```

Его задача:

- получить `StorageKey`;
- запустить Python worker;
- передать необходимые CLI parameters;
- получить structured JSON;
- проверить exit code;
- передать JSON обратно в .NET;
- корректно обработать stderr/technical failure.

## Шаг 4. Добавить background queue

На этом этапе НЕ использовать RabbitMQ и Kafka.

Для локального MVP использовать простой in-process queue на базе:

```text
System.Threading.Channels
```

Нужна abstraction уровня приложения, например:

```text
IDocumentProcessingQueue
```

Queue хранит `DocumentId` для обработки.

## Шаг 5. Добавить HostedService / BackgroundService

Background worker должен:

1. ожидать `DocumentId` из queue;
2. создать DI scope;
3. вызвать `IDocumentProcessingService`;
4. залогировать результат/ошибку;
5. продолжить обработку следующих документов.

Важно: `DbContext` scoped, поэтому background singleton не должен удерживать один `DbContext` между задачами.

## Шаг 6. Enqueue после успешного upload

После того как:

1. файл сохранён;
2. `Document` сохранён в PostgreSQL;

нужно enqueue `document.Id`.

Upload request при этом не должен ждать выполнения Python extraction.

Предпочтительный HTTP flow:

```text
POST /api/documents
→ документ сохранён
→ задача поставлена в очередь
→ HTTP response пользователю
```

Дальнейшая обработка происходит background.

## Шаг 7. Корректные переходы статусов

Ожидаемые переходы:

```text
Uploaded
  ↓
Processing
  ├── valid       → Processed
  ├── invalid     → NeedsReview
  ├── incomplete  → NeedsReview
  └── exception   → Failed
```

Не переводить документ в `Processed`, если persistence `ExtractionResult` не завершён успешно.

## Шаг 8. Idempotency

Связь в БД уже ограничивает:

```text
Document 1 → 0..1 ExtractionResult
```

`DocumentId` имеет unique index.

Но application logic также должна предотвращать повторное создание результата при retry/двойном enqueue.

Повторная обработка должна иметь явно определённое поведение, а не случайно падать на unique constraint.

## Шаг 9. Добавить manual process endpoint

Полезный development/admin endpoint:

```http
POST /api/documents/{id}/process
```

Он должен ставить существующий документ в processing queue.

Назначение:

- retry;
- debugging;
- ручной запуск без повторного upload;
- основа будущего admin/review workflow.

## Шаг 10. Тестирование automation flow

Минимально проверить:

1. upload валидного supplier quotation;
2. response API возвращается без ожидания Python processing;
3. `Document.Status` проходит `Uploaded → Processing → Processed`;
4. `ExtractionResult` появляется автоматически;
5. результат совпадает с уже проверенным deterministic extraction;
6. повторный enqueue не создаёт второй `ExtractionResult`;
7. ошибка Python переводит документ в `Failed`;
8. invalid/incomplete validation переводит документ в `NeedsReview`.

# 8. Предлагаемое размещение кода

Не считать имена окончательными до начала реализации, но предпочтительная структура:

```text
src/
  DocFlow.Application/
    Abstractions/
      IDocumentProcessingService.cs
      IDocumentProcessingQueue.cs
      IDocumentExtractionRunner.cs
      IExtractionResultService.cs

  DocFlow.Infrastructure/
    Processing/
      DocumentProcessingQueue.cs
      PythonDocumentExtractionRunner.cs

  DocFlow.Api/
    BackgroundServices/
      DocumentProcessingBackgroundService.cs
```

Application не должен зависеть от Infrastructure.

Infrastructure реализует application abstractions.

# 9. Что сознательно НЕ делать в 1.1.1.2

Не добавлять сейчас:

- RabbitMQ;
- Kafka;
- Redis;
- Kubernetes;
- ONNX semantic extraction;
- external LLM extraction;
- OCR;
- invoice extractor;
- S3 migration;
- authentication/billing;
- frontend/review UI.

Причина: сначала нужно автоматизировать уже доказанный deterministic supplier quotation path.

# 10. Критерий завершения версии 1.1.1.2

Этап завершён, когда можно выполнить только:

```text
POST /api/documents
```

а затем без ручных действий получить:

```text
GET /api/documents/{id}
→ Status = Processed / NeedsReview / Failed

GET /api/documents/{id}/extraction-result
→ persisted StructuredExtractionResult
```

Для корректного synthetic supplier quotation ожидается:

```text
Status = Processed
DocumentType = supplier_quotation
ValidationStatus = Valid
Confidence = 1.0
```

# 11. Что делать после Automation

Следующий robustness stage:

1. digital supplier quotation без рамок таблицы;
2. supplier invoice;
3. scanned PDF и OCR;
4. dirty/real supplier PDF;
5. затем решить, где deterministic extraction недостаточен и нужен ONNX/LLM fallback.

# 12. С чего начать в новом чате

1. Прочитать `docs/HANDOFF_v1.1.1.1.md` как исторический baseline.
2. Прочитать этот файл `docs/HANDOFF_v1.1.1.2_Automation.md` как активный план.
3. Убедиться, что рабочая ветка:

```text
DocFlow/v_1.1.1.2_Automation
```

4. Не менять Python extraction algorithms.
5. Первым изменением вынести persistence `ExtractionResult` из `DocumentsController` в application service.
6. После каждого законченного подэтапа проверять build/tests до перехода дальше.

---

Версия 1.1.1.2 посвящена только автоматизации уже работающего extraction pipeline. Цель — убрать ручной мост между upload, Python worker и .NET persistence, не усложняя систему преждевременно.