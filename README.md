# WhisperRoles

Docker-контейнер для автоматической расшифровки аудиофайлов с разделением по спикерам (диаризацией). Работает на CPU, GPU не требуется.

Кладёшь аудиофайл в папку — рядом появляется `.txt` с расшифровкой.

---

## Предварительная настройка (один раз)

### 1. Установи Docker

- **Linux (Ubuntu/Debian):**

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Перелогинься чтобы группа применилась
```

- **macOS:** скачай [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- **Windows:** скачай [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Проверь что работает:

```bash
docker --version
```

### 2. Получи HuggingFace токен (нужен для разделения по спикерам)

Разделение по спикерам использует модель pyannote.audio, для неё нужен бесплатный токен:

1. Зарегистрируйся на [huggingface.co](https://huggingface.co/join)
2. Перейди на страницу модели [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) — нажми **"Agree and access repository"**
3. Перейди на страницу модели [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) — нажми **"Agree and access repository"**
4. Создай токен: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) — тип **Read**
5. Скопируй токен (начинается с `hf_...`), он понадобится при запуске

> Без токена контейнер всё равно расшифровывает речь, но не разделяет по спикерам.

### 3. Авторизуйся в реестре образов (если образ приватный)

```bash
docker login ghcr.io -u ТВОЙ_GITHUB_ЛОГИН
```

Пароль — GitHub Personal Access Token с правом `read:packages`. Создать можно тут: [github.com/settings/tokens](https://github.com/settings/tokens).

---

## Запуск

### Создай папку для аудиофайлов

```bash
mkdir -p ~/transcribe
```

### Запусти контейнер

```bash
docker run -d \
  --name whisper-roles \
  --restart unless-stopped \
  -v ~/transcribe:/data \
  -e HF_TOKEN=hf_сюда_вставь_свой_токен \
  ghcr.io/protos-galaxias/whisperroles:latest
```

Первый запуск скачает образ (~3 GB) и модели (~1 GB) — это займёт несколько минут.

### Проверь что работает

```bash
docker logs -f whisper-roles
```

Когда увидишь строку `Watching for audio files...` — контейнер готов к работе. Нажми `Ctrl+C` чтобы выйти из логов (контейнер продолжит работать).

---

## Использование

1. Положи аудиофайл в папку `~/transcribe/`
2. Подожди (время зависит от длины записи и модели)
3. Рядом с аудиофайлом появится `.txt` с расшифровкой

Поддерживаемые форматы: `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.wma`, `.aac`

### Пример результата

```
[00:00:01 - 00:00:05] SPEAKER_00: Добрый день, начинаем совещание.
[00:00:06 - 00:00:12] SPEAKER_01: Здравствуйте, у меня есть вопрос по первому пункту.
[00:00:13 - 00:00:20] SPEAKER_00: Да, конечно, слушаю.
```

---

## Настройка

Параметры передаются через `-e` при запуске. Пример с русским языком и моделью `medium`:

```bash
docker run -d \
  --name whisper-roles \
  --restart unless-stopped \
  -v ~/transcribe:/data \
  -e HF_TOKEN=hf_xxx \
  -e WHISPER_MODEL=medium \
  -e LANGUAGE=ru \
  ghcr.io/protos-galaxias/whisperroles:latest
```

| Параметр | По умолчанию | Описание |
|---|---|---|
| `HF_TOKEN` | — | Токен HuggingFace для разделения по спикерам |
| `WHISPER_MODEL` | `small` | Размер модели: `tiny` (быстро, менее точно) / `small` / `medium` / `large-v2` (медленно, точно) |
| `LANGUAGE` | автоопределение | Код языка: `ru`, `en`, `de`, `fr` и т.д. Если указать — работает быстрее |
| `BATCH_SIZE` | `8` | Размер батча. Уменьши если не хватает RAM |
| `POLL_INTERVAL` | `5` | Как часто проверять папку (секунды) |

### Рекомендации по выбору модели

| Модель | Размер модели | RAM | Скорость (CPU) | Качество |
|---|---|---|---|---|
| `tiny` | ~75 MB | ~1 GB | Быстро | Базовое |
| `base` | ~150 MB | ~1 GB | Быстро | Приемлемое |
| `small` | ~500 MB | ~2 GB | Средне | Хорошее |
| `medium` | ~1.5 GB | ~5 GB | Медленно | Очень хорошее |
| `large-v2` | ~3 GB | ~10 GB | Очень медленно | Максимальное |

---

## Управление контейнером

```bash
# Посмотреть логи
docker logs -f whisper-roles

# Остановить
docker stop whisper-roles

# Запустить снова
docker start whisper-roles

# Удалить контейнер
docker rm -f whisper-roles

# Обновить до последней версии
docker pull ghcr.io/protos-galaxias/whisperroles:latest
docker rm -f whisper-roles
# ... и запустить заново командой выше
```

---

## Решение проблем

| Проблема | Решение |
|---|---|
| `unauthorized` при скачивании образа | Выполни `docker login ghcr.io` |
| `HF_TOKEN not set — diarization disabled` | Не указан или неверный HuggingFace токен |
| `Could not download pipeline` / `403` | Не приняты лицензии моделей на HuggingFace (см. шаг 2) |
| Очень долго обрабатывает | Поставь модель поменьше: `-e WHISPER_MODEL=tiny` |
| Контейнер упал (нет логов) | Проверь `docker logs whisper-roles`, возможно не хватает RAM |
| Файл не обрабатывается повторно | Удали `.txt` рядом с аудиофайлом — обработается заново |
