# WhisperRoles

HTTP API для расшифровки аудиофайлов с разделением по спикерам (диаризацией). Локальная обработка через WhisperX, GPU не требуется.

Загружаешь аудиофайл по HTTP — получаешь расшифровку с разделением по спикерам.

## Быстрый старт

```bash
docker run -d \
  --name whisper-roles \
  -p 8000:8000 \
  -e HF_TOKEN=hf_ваш_токен \
  ghcr.io/molchanovartem/whisperroles:latest
```

Первый запуск скачает модели (~1 GB) — подождите пока в логах не появится `Ready to accept requests`.

```bash
docker logs -f whisper-roles
```

## Предварительная настройка

### HuggingFace токен (для разделения по спикерам)

1. Зарегистрируйтесь на [huggingface.co](https://huggingface.co/join)
2. Примите лицензию: [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
3. Примите лицензию: [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
4. Создайте токен (тип Read): [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

> Без токена расшифровка работает, но без разделения по спикерам.

## API

### POST /transcribe

Загрузить аудиофайл. Возвращает `job_id`.

```bash
curl -X POST http://server:8000/transcribe -F file=@meeting.mp3
```

```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "processing"}
```

### GET /status/{job_id}

Проверить статус задачи.

```bash
curl http://server:8000/status/550e8400-...
```

Статусы: `processing`, `done`, `error`

### GET /result/{job_id}

Получить результат (text/plain).

```bash
curl http://server:8000/result/550e8400-...
```

```
[00:00:01 - 00:00:05] SPEAKER_00: Добрый день, начинаем совещание.
[00:00:06 - 00:00:12] SPEAKER_01: Здравствуйте, у меня есть вопрос.
```

## JS-клиент

Для удобства — скрипт `client.mjs`. Загружает файл, ждёт результат, печатает расшифровку:

```bash
node client.mjs meeting.mp3 http://server:8000
```

Работает на любой машине с Node.js 18+. Зависимостей нет.

## Переменные окружения

| Параметр        | По умолчанию    | Описание                                            |
| :-------------- | :-------------- | :-------------------------------------------------- |
| `HF_TOKEN`      | —               | Токен HuggingFace для диаризации                    |
| `WHISPER_MODEL` | `small`         | Модель: `tiny` / `base` / `small` / `medium`        |
| `LANGUAGE`      | автоопределение | Код языка (`ru`, `en`, `de`). Если указать — быстрее |
| `BATCH_SIZE`    | `8`             | Размер батча. Уменьши если мало RAM                  |
| `MAX_WORKERS`   | `1`             | Параллельных задач                                   |
| `RESULTS_DIR`   | `/data/results` | Папка для результатов                                |

### Рекомендации по модели

| Модель   | RAM    | Качество           |
| -------- | ------ | ------------------ |
| `tiny`   | ~1 GB  | Базовое            |
| `base`   | ~1 GB  | Приемлемое         |
| `small`  | ~2 GB  | Хорошее            |
| `medium` | ~5 GB  | Очень хорошее      |

Для сервера с 7 GB свободной RAM рекомендуется `small` (по умолчанию).

## Архитектура

```
[Маленький сервер]                    [Большой сервер (7 GB)]
   файлы.mp3  ─── HTTP POST ───────>  WhisperRoles API
                                         WhisperX (CPU)
              <── GET /result ───────   .txt результаты
```

## Сборка локально

```bash
docker build -t whisper-roles .
docker run -d -p 8000:8000 -e HF_TOKEN=hf_xxx whisper-roles
```
