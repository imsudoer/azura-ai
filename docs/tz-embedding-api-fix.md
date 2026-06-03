# ТЗ: исправление Embedding API на роутере OnlySq

## Контекст
OnlySq API (`api.onlysq.ru/ai/openai`) — OpenAI-совместимый роутер, который проксирует запросы к различным backend-провайдерам. Endpoint `/embeddings` должен быть полностью совместим с OpenAI Embeddings API.

## Проблемы, выявленные клиентом

### Проблема 1: `Unknown name "user"` (gemini-embedding-001)

**Модель**: `gemini-embedding-001`
**Запрос (OpenAI SDK стандартный)**:
```json
{
  "model": "gemini-embedding-001",
  "input": "текст для эмбеддинга"
}
```
OpenAI SDK автоматически добавляет поле `"user"` в payload (стандартное поле OpenAI API).

**Ответ роутера**: 500
```json
{
  "error": {
    "code": 400,
    "message": "Invalid JSON payload received. Unknown name \"user\": Cannot find field.",
    "status": "INVALID_ARGUMENT"
  }
}
```

**Причина**: роутер проксирует весь payload as-is в Google Gemini API, который не принимает поле `user`. Роутер должен **стрипать** нестандартные для конкретного backend поля перед проксированием.

**Требуется**: перед отправкой запроса к Gemini-backend стрипать поля, которые Gemini не поддерживает (`user`, `encoding_format`, и любые другие, не входящие в Gemini Embedding API).

---

### Проблема 2: `encoding format must be one of: base64_int8 base64_binary` (pplx-embed-v1-4b)

**Модель**: `pplx-embed-v1-4b`
**Запрос (OpenAI SDK стандартный)**:
```json
{
  "model": "pplx-embed-v1-4b",
  "input": "текст для эмбеддинга"
}
```
OpenAI SDK по умолчанию шлёт `encoding_format: "float"` (или не шлёт, тогда сервер должен подставить `float` по умолчанию как в OpenAI API).

**Ответ роутера**: 500
```json
{
  "error": {
    "code": 400,
    "message": "encoding format must be one of: base64_int8 base64_binary"
  }
}
```

**Причина**: pplx-embed backend ожидает `encoding_format` только `base64_int8` или `base64_binary`, не поддерживает стандартный `float`. Роутер не транслирует/дефолтит этот параметр.

**Требуется**: 
1. Если клиент не передал `encoding_format` или передал `"float"` — роутер должен:
   - Либо установить дефолт, принимаемый backend'ом (например `base64_binary`)
   - Либо получить от backend ответ в его формате и **конвертировать** в `float` (массив чисел), как ожидает OpenAI-совместимый клиент
2. Ответ роутера ВСЕГДА должен быть OpenAI-совместимым:
   ```json
   {
     "object": "list",
     "data": [
       {"object": "embedding", "index": 0, "embedding": [0.123, -0.456, ...]}
     ],
     "model": "pplx-embed-v1-4b",
     "usage": {"prompt_tokens": N, "total_tokens": N}
   }
   ```
   То есть `embedding` — массив float, даже если backend отдал base64.

---

## Общие требования к `/embeddings` endpoint

1. **Полная совместимость с OpenAI Embeddings API** (https://platform.openai.com/docs/api-reference/embeddings)
2. **Параметр `encoding_format`**:
   - Должен поддерживаться: `"float"` (по умолчанию), `"base64"`
   - Если backend не поддерживает `float` — роутер запрашивает в доступном формате и конвертирует ответ
3. **Параметр `user`**:
   - Принимать и игнорировать (не проксировать в backend'ы, которые его не поддерживают)
4. **Параметр `dimensions`** (MRL — Matryoshka Representation Learning):
   - Если модель поддерживает MRL (pplx-embed-v1-4b, pplx-embed-v1-0.6b) — проксировать
   - Если не поддерживает — игнорировать (не проксировать, не ломать запрос)
5. **Формат ответа**: всегда OpenAI-совместимый JSON, независимо от формата backend'а
6. **Batch input**: `"input"` может быть строкой или массивом строк — оба варианта должны работать
7. **Коды ошибок**: 4xx от backend → 4xx клиенту (не 500). 500 только для реальных серверных ошибок роутера.

## Модели для тестирования

| Model | Dims | Backend | Особенности |
|---|---|---|---|
| `pplx-embed-v1-4b` | 2560 | Perplexity | Только `base64_int8` / `base64_binary` |
| `pplx-embed-v1-0.6b` | 1024 | Perplexity | Только `base64_int8` / `base64_binary` |
| `gemini-embedding-001` | 3072 | Google | Не принимает `user`, `encoding_format` |
| `text-embedding-3-small` | 1536 | OpenAI | Полная совместимость (эталон) |

## Тест-кейсы

```python
# 1. Базовый запрос — должен вернуть list[float]
POST /embeddings
{"model": "pplx-embed-v1-4b", "input": "hello world"}
# ожидание: 200, data[0].embedding = [float, float, ...]

# 2. С user — должен вернуть 200 (user игнорируется)
POST /embeddings  
{"model": "gemini-embedding-001", "input": "hello", "user": "test-user"}
# ожидание: 200

# 3. encoding_format=float (дефолт) — роутер конвертирует из base64 если нужно
POST /embeddings
{"model": "pplx-embed-v1-4b", "input": "hello", "encoding_format": "float"}
# ожидание: 200, embedding = [float, ...]

# 4. Batch input
POST /embeddings
{"model": "pplx-embed-v1-4b", "input": ["hello", "world"]}
# ожидание: 200, len(data) == 2

# 5. MRL (dimensions)
POST /embeddings
{"model": "pplx-embed-v1-4b", "input": "hello", "dimensions": 512}
# ожидание: 200, len(embedding) == 512

# 6. encoding_format=base64
POST /embeddings
{"model": "pplx-embed-v1-4b", "input": "hello", "encoding_format": "base64"}
# ожидание: 200, embedding = base64-encoded string
```
