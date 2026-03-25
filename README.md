# ГАРАНТ MCP

MCP-сервер для подключения Claude к правовой базе данных **ГАРАНТ** через официальный API

Позволяет искать нормативные акты, читать документы, отслеживать изменения законодательства и анализировать судебную практику прямо в диалоге с Claude.

## Инструменты

| Инструмент | Описание |
|---|---|
| `garant_search` | Полнотекстовый поиск по базе (нормативные акты / арбитражная практика) |
| `garant_get_snippets` | Найти релевантные параграфы внутри документа |
| `garant_get_document_html` | Получить полный текст документа (HTML-блоки) |
| `garant_get_entry_html` | Получить конкретный параграф с контекстом |
| `garant_get_topic_info` | Метаданные документа: тип, статус, дата, орган |
| `garant_get_redactions` | Список всех редакций документа |
| `garant_find_modified` | Проверить изменения документов за период |
| `garant_block_on_control_changed` | Мониторинг изменений конкретных параграфов |
| `garant_find_hyperlinks` | Расставить ссылки на нормы ГАРАНТ в тексте |
| `garant_get_prime_categories` | Дерево рубрик правовых новостей |
| `garant_get_news` | Правовые новости по рубрикам и датам |
| `garant_search_court_practice` | Поиск судебной практики (Сутяжник) |
| `garant_get_limits` | Текущие лимиты API |
| `garant_download_document_url` | Ссылка для скачивания документа (PDF/RTF/ODT) |

## Требования

Для использования необходим собственный токен **Гарант-Коннект**. Токен выдаётся через личный кабинет на [garant.ru](https://garant.ru) или по запросу вашему менеджеру ГАРАНТ.

## Деплой на Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com)

1. Форкните репозиторий на GitHub
2. Создайте новый проект на [railway.app](https://railway.app) → **Deploy from GitHub repo**
3. В разделе **Variables** добавьте переменную:
   ```
   GARANT_TOKEN = ваш_токен
   ```
4. В разделе **Settings → Networking** нажмите **Generate Domain**
5. Проверьте, что сервер запустился: откройте `https://ваш-домен.up.railway.app/health` — должно вернуть `{"status": "ok"}`

## Подключение к Claude Web

1. Откройте [claude.ai](https://claude.ai) → **Settings → Integrations → Add integration**
2. Введите:
   - **Name:** ГАРАНТ
   - **URL:** `https://ваш-домен.up.railway.app/mcp`
3. Нажмите **Add**

## Подключение к Claude Desktop

В файл конфигурации `claude_desktop_config.json` добавьте:

```json
{
  "mcpServers": {
    "garant": {
      "command": "python",
      "args": ["/путь/к/server.py"],
      "env": {
        "GARANT_TOKEN": "ваш_токен"
      }
    }
  }
}
```

## Локальный запуск

```bash
git clone https://github.com/ваш-логин/garant-mcp
cd garant-mcp
pip install "mcp[cli]" httpx pydantic
export GARANT_TOKEN="ваш_токен"
python server.py
```

## Лицензия

MIT
