# WhisperRoles

HTTP API для расшифровки аудиофайлов с разделением по спикерам (диаризацией). Использует OpenAI `gpt-4o-transcribe-diarize`. Node.js, лёгкий контейнер.

## Быстрый старт

```bash
docker run -d \
  --name whisper-roles \
  -p 8000:8000 \
  -e OPENAI_API_KEY=sk-... \
  ghcr.io/molchanovartem/whisperroles:latest
```

## API

### POST /transcribe

Загрузить аудиофайл. Возвращает `job_id`.

```bash
curl -X POST http://localhost:8000/transcribe \
  -F file=@meeting.mp3
```

```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "processing"}
```

### GET /status/{job_id}

Проверить статус задачи.

```bash
curl http://localhost:8000/status/550e8400-e29b-41d4-a716-446655440000
```

Статусы: `processing`, `done`, `error`

### GET /result/{job_id}

Получить результат (text/plain).

```bash
curl http://localhost:8000/result/550e8400-e29b-41d4-a716-446655440000
```

```
[00:00:01 - 00:00:05] speaker_0: Добрый день, начинаем совещание.
[00:00:06 - 00:00:12] speaker_1: Здравствуйте, у меня есть вопрос.
[00:00:13 - 00:00:20] speaker_0: Да, конечно, слушаю.
```

## JS-клиент

```bash
node client.mjs meeting.mp3 http://localhost:8000
```

Загружает файл, ждёт результат, печатает расшифровку.

## Переменные окружения

| Параметр         | Обязательный | Описание                                                      |
| :--------------- | :----------- | :------------------------------------------------------------ |
| `OPENAI_API_KEY` | да           | API ключ OpenAI                                               |
| `RESULTS_DIR`    | нет          | Папка для результатов (по умолчанию `/data/results`)          |
| `PORT`           | нет          | Порт сервера (по умолчанию `8000`)                            |

## Стоимость

OpenAI `gpt-4o-transcribe-diarize`: **$0.006/мин** аудио. Часовое совещание — ~$0.36.

## Ограничения

- Файлы > 25 MB автоматически нарезаются на части через ffmpeg
- Поддерживаемые форматы: mp3, mp4, mpeg, mpga, m4a, wav, webm
- Аудиофайл удаляется после обработки, результаты хранятся в txt

## Сборка локально

```bash
docker build -t whisper-roles .
docker run -d -p 8000:8000 -e OPENAI_API_KEY=sk-... whisper-roles
```
