# YouTube Gemini Visual Analyzer — личный MCP для ChatGPT

Небольшой *личный* Streamable-HTTP MCP-сервер на Python. Через Gemini API анализирует **звуковую и визуальную** составляющие публичных YouTube-видео и Shorts, а не только субтитры.

## Что умеет

- `analyze_youtube_video`: режимы `quick`, `visual`, `deep`; ориентировочные таймкоды, сцены, речь, текст на экране, различие фактов и утверждений.
- `inspect_youtube_moment`: уточняющий вопрос о конкретном моменте.
- `youtube_mcp_status`: проверить настройку ключа и локальный лимит.
- Принимает только валидные HTTPS-ссылки на YouTube; произвольные URL не загружаются.
- Суточный ограничитель вызовов (по умолчанию 15). Ключ Google читается только из переменных окружения, не хранится в репозитории.

## Развёртывание на Render

1. Создай отдельный репозиторий GitHub и помести в него файлы этой папки. **Не загружай `.env`.**
2. [Render](https://dashboard.render.com/) → New → Web Service, выбери репозиторий, runtime Python, instance **Free**, регион Frankfurt.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log`.
5. В Environment добавь секреты:
   - `GEMINI_API_KEY`: ключ из [Google AI Studio](https://aistudio.google.com/api-keys).
   - `MCP_SECRET_PATH`: случайная строка длиной не менее 32 символов. Сгенерировать: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   - `GEMINI_MODEL=gemini-3.8-flash`, `MAX_CALLS_PER_DAY=15`.
6. Запусти deploy. Проверка публичной готовности: `https://ИМЯ-СЕРВИСА.onrender.com/health` возвращает `{"status":"ok"}`.
7. Личный MCP URL: `https://ИМЯ-СЕРВИСА.onrender.com/ЗНАЧЕНИЕ_MCP_SECRET_PATH/mcp`.
8. В **веб-версии** ChatGPT открой Plugins → `+` → Add custom MCP server. Введи имя `YouTube Gemini`, URL из пункта 7 и в этом пилотном варианте выбери **No authentication**: доступ ограничен секретной ссылкой. Создай и установи плагин. Если аккаунт не позволяет подключение, работа плагина в ChatGPT недоступна.

**Безопасность.** Это персональный прототип с секретным URL, не полноценная OAuth 2.1-авторизация. Не публикуй секретный URL; при утечке меняй `MCP_SECRET_PATH` в Render и меняй адрес в ChatGPT. Публичный сервис доступен через Интернет, а любой владелец секретной ссылки способен тратить твою квоту Gemini. Для многопользовательского или производственного использования реализуй OAuth 2.1, устойчивую квоту в Redis и ограничения расходов на стороне Google Cloud.

**Стоимость.** Render Free может засыпать после периода бездействия, а квоты и тарификация Google Gemini API задаются отдельно. Лимит `MAX_CALLS_PER_DAY` — локальный счётчик процесса (после перезапуска сбрасывается), **не** гарантия расходов. Проверь Billing и установи ограничения в Google Cloud.

**Ограничения видео.** Gemini может семплировать изображения ~1 кадр/сек, поэтому быстрые сцены могут быть пропущены; ссылки на закрытые или недоступные видео не работают. Вывод модели не заменяет независимую проверку фактов.

## Локальное тестирование

```bash
python -m pip install -r requirements-dev.txt
# Экспортируй GEMINI_API_KEY и MCP_SECRET_PATH через системные переменные окружения.
uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Для теста протокола:

```bash
curl -sS 'http://127.0.0.1:8000/ТВОЙ_СЕКРЕТ/mcp' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

`pytest -q` проверяет MCP handshake, маршрутизацию инструментов и валидацию YouTube URL без реального вызова Google. Для проверки с настоящим видео требуется API-ключ и доступная модель.

## Справка

- [Google Gemini video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
- [ChatGPT — подключение custom MCP](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [MCP Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)

## Проверка готовности (аудит 30.10.2026)

- `gemini-3.8-flash`, Interactions API и поля `video.uri` / `processing`
  соответствуют текущей документации Google. Доступность модели для конкретного
  ключа, региона и тарифного плана подтверждается только настоящим вызовом.
- Локальные тесты используют подмену HTTP Google: они не доказывают анализ
  реального видео или подключение к ChatGPT.
- `/health` подтверждает запуск процесса, но не наличие рабочего ключа Gemini.
  `youtube_mcp_status` проверяет наличие ключа, но не его действительность.
- Режимы не ограничивают длительность входного видео. Локальный счётчик и лимит
  выходных токенов не гарантируют нулевых расходов. Используйте ключ проекта без
  платного биллинга, если требуются только бесплатные вызовы; не включайте billing
  автоматически. Не повторяйте неуспешные запросы без выяснения причины.

### Живой smoke-тест

Задайте `YOUTUBE_MCP_URL` через защищённые переменные окружения, не вставляя
секретный URL в отчёты или репозиторий. После проверки бесплатной квоты:

```bash
python scripts/live_smoke.py --url 'https://youtube.com/shorts/AWOibEA9bW0' --timestamp 00:05 --allow-quota-use
```

Скрипт проверяет initialize → initialized → tools/list → status и выполняет
**четыре настоящих вызова Gemini**: речь, сцены, надписи, конкретный момент.
Без флага запросы не отправляются. При первой ошибке инструмента тест останавливается.
Сопоставьте ответы с самостоятельным просмотром ролика: успешный HTTP-ответ
не доказывает точность распознавания. Этот тест проверяет удалённый MCP, но
не установку в ChatGPT; в ChatGPT отдельно вызовите status и анализ видео.
