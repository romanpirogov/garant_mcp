"""
MCP-сервер для подключения к правовой базе данных ГАРАНТ
через API Гарант-Коннект (v2).

Аутентификация: Bearer-токен передаётся через переменную окружения
GARANT_TOKEN или напрямую в параметре инициализации.
"""

import json
import os
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator, ConfigDict

# ---------------------------------------------------------------------------
# Инициализация сервера
# ---------------------------------------------------------------------------

mcp = FastMCP("garant_mcp")

BASE_URL = os.environ.get("GARANT_BASE_URL", "https://api.garant.ru")
_TOKEN: str = os.environ.get("GARANT_TOKEN", "")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _headers() -> dict:
    token = _TOKEN or os.environ.get("GARANT_TOKEN", "")
    if not token:
        raise ValueError(
            "GARANT_TOKEN не задан. Установите переменную окружения GARANT_TOKEN."
        )
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _binary_headers() -> dict:
    token = _TOKEN or os.environ.get("GARANT_TOKEN", "")
    if not token:
        raise ValueError("GARANT_TOKEN не задан.")
    return {"Authorization": f"Bearer {token}"}


def _handle_error(response: httpx.Response) -> str:
    code = response.status_code
    if code == 400:
        return f"Ошибка 400: неверные параметры запроса. Ответ: {response.text[:300]}"
    if code == 401:
        return "Ошибка 401: токен не передан или недействителен."
    if code == 403:
        return "Ошибка 403: недостаточно прав. Проверьте подписку или лимиты."
    if code == 404:
        return f"Ошибка 404: ресурс не найден (topic/entry может не существовать)."
    if code == 423:
        return "Ошибка 423: превышен лимит запросов. Попробуйте позже."
    if code == 429:
        return "Ошибка 429: слишком много запросов. Уменьшите частоту обращений."
    return f"Ошибка {code}: {response.text[:300]}"


# ---------------------------------------------------------------------------
# Модели входных данных (Pydantic v2)
# ---------------------------------------------------------------------------

class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(
        ...,
        description="Поисковый запрос (до 16 КБ). Если isQuery=True, принимается "
                    "формат расширенного запроса ГАРАНТ.",
        min_length=1,
        max_length=16_000,
    )
    isQuery: bool = Field(
        default=False,
        description="True — запрос в синтаксисе ГАРАНТ (до 50 символов), "
                    "False — полнотекстовый поиск.",
    )
    page: int = Field(default=1, description="Страница результатов (начиная с 1).", ge=1)
    env: str = Field(
        default="internet",
        description="База поиска: 'internet' — интернет-версия ГАРАНТ, "
                    "'arbitr' — база арбитражной практики.",
        pattern="^(internet|arbitr)$",
    )
    sort: int = Field(
        default=0,
        description="Сортировка: 0 — по релевантности, 1 — по дате принятия, "
                    "2 — по дате последнего изменения, 3 — по алфавиту.",
        ge=0,
        le=3,
    )
    sortOrder: int = Field(
        default=0,
        description="Порядок: 0 — убывание (новые/релевантные сначала), 1 — возрастание.",
        ge=0,
        le=1,
    )


class SnippetsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: Optional[str] = Field(
        default=None,
        description="Поисковый текст для поиска релевантных фрагментов в документе. "
                    "Обязателен, если не передан correspondent.",
    )
    topic: Optional[int] = Field(
        default=None,
        description="Номер документа, в котором ищем фрагменты.",
    )
    correspondent: Optional[dict] = Field(
        default=None,
        description='Объект {"topic": int, "entry": int} — ссылающийся документ и '
                    "его параграф. Обязателен, если не передан text.",
    )


class FindHyperlinksInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(
        ...,
        description="Текст (plain text или HTML, до 20 КБ) для поиска ссылок "
                    "на нормативные акты ГАРАНТ.",
        max_length=20_000,
    )
    baseUrl: str = Field(
        default="https://internet.garant.ru",
        description="Базовый URL для формирования ссылок: "
                    "https://internet.garant.ru (онлайн-версия) или "
                    "https://base.garant.ru / http://ivo.garant.ru (локальная версия).",
    )


class FindModifiedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topics: list[int] = Field(
        ...,
        description="Список номеров документов (topic) для проверки изменений. "
                    "Не более 100 элементов.",
        max_length=100,
    )
    modDate: str = Field(
        ...,
        description="Дата, начиная с которой проверяются изменения. Формат YYYY-MM-DD. "
                    "Пример: '2019-07-01'.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    needEvents: bool = Field(
        default=False,
        description="True — включить в ответ историю изменений документа.",
    )


class BlockOnControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fromDate: str = Field(
        ...,
        description="Дата начала периода проверки. Формат YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    urlArray: list[str] = Field(
        ...,
        description="Список URL-адресов параграфов вида "
                    "'http://internet.garant.ru/#/document/{topic}/entry/{entry}'. "
                    "Проверяется, изменились ли конкретные параграфы.",
    )
    needEvents: bool = Field(
        default=False,
        description="True — включить историю событий для каждого параграфа.",
    )


class CreateNewsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[int] = Field(
        ...,
        description="Список ID рубрик (из /v2/prime). Для выбора всех — передать "
                    "пустой список или список корневых ID.",
    )
    fromDate: str = Field(
        ...,
        description="Начало диапазона дат. Формат YYYY-MM-DD.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    toDate: Optional[str] = Field(
        default=None,
        description="Конец диапазона (не обязателен). Формат YYYY-MM-DD. "
                    "Максимальный диапазон toDate − fromDate = 10 дней.",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    sort: int = Field(
        default=1,
        description="Сортировка: 1 — по дате публикации (убывание, по умолчанию), "
                    "2 — по алфавиту.",
        ge=1,
        le=2,
    )


class SutyazhnikSearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(
        ...,
        description="Поисковый запрос для поиска по судебной практике ГАРАНТ. "
                    "Максимальная длина 1000 символов.",
        min_length=1,
        max_length=1_000,
    )
    count: int = Field(
        default=20,
        description="Количество результатов. Диапазон 1–1000.",
        ge=1,
        le=1_000,
    )
    kind: Optional[list[str]] = Field(
        default=None,
        description="Фильтр по виду практики: '301' — нормы из кодексов, "
                    "'302' — судебная практика, '303' — нормы из подзаконных актов.",
    )


# ---------------------------------------------------------------------------
# Инструменты
# ---------------------------------------------------------------------------

@mcp.tool(
    name="garant_search",
    annotations={
        "title": "Поиск документов в базе ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def garant_search(params: SearchInput) -> str:
    """Полнотекстовый поиск по базе ГАРАНТ.

    Возвращает постранично список документов, удовлетворяющих запросу.
    Каждая страница содержит до 50 документов.

    Args:
        params (SearchInput):
            - text (str): поисковый запрос
            - isQuery (bool): использовать синтаксис расширенного запроса
            - page (int): номер страницы (с 1)
            - env (str): 'internet' или 'arbitr'
            - sort (int): критерий сортировки (0–3)
            - sortOrder (int): направление сортировки (0 — убывание, 1 — возрастание)

    Returns:
        str: JSON со списком документов (name, url, topic), количеством страниц
             и общим числом найденных документов.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/v2/search",
                headers=_headers(),
                json=params.model_dump(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            data = resp.json()
            result = {
                "totalDocs": data.get("totalDocs"),
                "totalPages": data.get("totalPages"),
                "page": data.get("page"),
                "documents": [
                    {
                        "topic": d.get("topic"),
                        "name": d.get("name"),
                        "url": f"https://internet.garant.ru/{d.get('url', '')}",
                    }
                    for d in data.get("documents", [])
                ],
            }
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при поиске: {e}"


@mcp.tool(
    name="garant_get_snippets",
    annotations={
        "title": "Релевантные фрагменты документа ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_snippets(params: SnippetsInput) -> str:
    """Найти в документе фрагменты, релевантные поисковому запросу.

    Используется для ответа на вопрос: «в каком параграфе документа
    содержится ответ на запрос?»

    Нужно передать либо text (поисковый текст) и topic (номер документа),
    либо correspondent (ссылающийся документ + параграф) и topic.

    Args:
        params (SnippetsInput):
            - text (str, optional): поисковый запрос
            - topic (int, optional): номер целевого документа
            - correspondent (dict, optional): {"topic": int, "entry": int}

    Returns:
        str: JSON со списком фрагментов: relevance (0–1), entry (номер параграфа),
             ancestors (хлебные крошки с номерами и заголовками разделов).
    """
    body: dict = {}
    if params.text is not None:
        body["text"] = params.text
    if params.topic is not None:
        body["topic"] = params.topic
    if params.correspondent is not None:
        body["correspondent"] = params.correspondent

    if not body:
        return "Ошибка: передайте хотя бы один из параметров: text, topic или correspondent."

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/v2/snippets",
                headers=_headers(),
                json=body,
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении снипетов: {e}"


@mcp.tool(
    name="garant_get_document_html",
    annotations={
        "title": "Получить полный текст документа ГАРАНТ (HTML)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_document_html(
    topic: int = Field(..., description="Номер документа (topic) в базе ГАРАНТ."),
) -> str:
    """Получить полный текст документа в формате HTML, разбитый на блоки.

    Документ возвращается в виде массива блоков (items), каждый с порядковым
    номером и HTML-текстом. Ссылки внутри HTML относительные.

    Args:
        topic (int): числовой идентификатор документа (topic).

    Returns:
        str: JSON {"items": [{"number": int, "text": "<html>"}]}.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/topic/{topic}/html",
                headers=_binary_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            data = resp.json()
            items = data.get("items", [])
            summary = {
                "topic": topic,
                "blocks_count": len(items),
                "items": items[:5],  # первые 5 блоков для предпросмотра
                "note": "Возвращены первые 5 блоков. Используйте garant_get_entry_html "
                        "для получения конкретного параграфа.",
            }
            return json.dumps(summary, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении HTML документа {topic}: {e}"


@mcp.tool(
    name="garant_get_entry_html",
    annotations={
        "title": "Получить параграф документа ГАРАНТ (HTML)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_entry_html(
    topic: int = Field(..., description="Номер документа."),
    entry: int = Field(..., description="Номер параграфа (entry) внутри документа."),
) -> str:
    """Получить конкретный параграф документа вместе с его контекстом.

    Возвращает HTML-текст параграфа, его заголовок, хлебные крошки (ancestors)
    и список «ответных» параграфов из других документов (respondents).
    Содержит до 100 ссылок из других документов на этот параграф.

    Args:
        topic (int): номер документа.
        entry (int): номер параграфа.

    Returns:
        str: JSON {entry, title, text, ancestors, respondents}.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/topic/{topic}/entry/{entry}/html",
                headers=_binary_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении параграфа {entry} документа {topic}: {e}"


@mcp.tool(
    name="garant_get_topic_info",
    annotations={
        "title": "Метаданные документа ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_topic_info(
    topic: int = Field(..., description="Номер документа (topic)."),
) -> str:
    """Получить метаданные документа: тип, статус, дату принятия, орган, территорию и т.д.

    Поле 'access' показывает доступность документа:
    - ACCESS_IS_FREE — открытый доступ;
    - ACCESS_BY_MONEY — платный контент;
    - ACCESS_BY_REQUEST — доступ по заявке;
    - ACCESS_DENIED — закрыт.

    Args:
        topic (int): числовой идентификатор документа.

    Returns:
        str: JSON с полями topic, name, type, status, date, adopted, territory,
             category, rstatus, access и др.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/topic/{topic}",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении метаданных документа {topic}: {e}"


@mcp.tool(
    name="garant_get_redactions",
    annotations={
        "title": "Редакции документа ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_redactions(
    topic: int = Field(..., description="Номер документа."),
) -> str:
    """Получить список всех редакций (версий) документа с их статусами.

    Статусы редакций: rs_New (новая), rs_Actual (актуальная), rs_Old (устаревшая)
    и их подвиды (Preactive — ещё не вступила в силу, Abolished — утратила силу).

    Args:
        topic (int): номер документа.

    Returns:
        str: JSON-массив редакций, каждая содержит: status, topic (номер редакции),
             activity (периоды действия), changingDocuments (изменяющие документы).
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/redactions/{topic}",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            data = resp.json()
            # Суммаризируем: показываем статус и периоды действия
            result = []
            for r in (data if isinstance(data, list) else []):
                result.append({
                    "topic": r.get("topic"),
                    "status": r.get("status"),
                    "activity": r.get("activity", []),
                    "changingDocuments_count": len(r.get("changingDocuments", [])),
                })
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении редакций документа {topic}: {e}"


@mcp.tool(
    name="garant_find_modified",
    annotations={
        "title": "Проверить изменения документов ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_find_modified(params: FindModifiedInput) -> str:
    """Проверить, изменились ли документы начиная с указанной даты.

    Полезно для мониторинга актуальности отслеживаемых нормативных актов.
    Можно передать до 100 номеров документов за один запрос.

    Args:
        params (FindModifiedInput):
            - topics (list[int]): список номеров документов
            - modDate (str): дата проверки в формате YYYY-MM-DD
            - needEvents (bool): включить историю событий

    Returns:
        str: JSON {"topics": [{"topic": int, "modStatus": 1|2, "events": [...]}]}.
             modStatus: 1 — изменился, 2 — не изменился.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/v2/find-modified",
                headers=_headers(),
                json=params.model_dump(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при проверке изменений: {e}"


@mcp.tool(
    name="garant_block_on_control_changed",
    annotations={
        "title": "Проверить изменения параграфов под контролем ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_block_on_control_changed(params: BlockOnControlInput) -> str:
    """Проверить изменения конкретных параграфов (entry) документов.

    В отличие от find-modified, работает с URL конкретных параграфов, а не
    документов целиком. Возвращает только изменившиеся параграфы.

    Args:
        params (BlockOnControlInput):
            - fromDate (str): дата начала проверки (YYYY-MM-DD)
            - urlArray (list[str]): список URL параграфов
            - needEvents (bool): включить историю событий

    Returns:
        str: JSON {"urlArray": [{"url": str, "modStatus": 1|2, "events": [...]}]}.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/v2/block-on-control/changed",
                headers=_headers(),
                json=params.model_dump(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при проверке параграфов: {e}"


@mcp.tool(
    name="garant_find_hyperlinks",
    annotations={
        "title": "Найти ссылки на нормы ГАРАНТ в тексте",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def garant_find_hyperlinks(params: FindHyperlinksInput) -> str:
    """Расставить гиперссылки на нормативные акты в тексте.

    Принимает plain text или HTML (до 20 КБ) и возвращает тот же текст,
    но с проставленными HTML-ссылками на документы ГАРАНТ.

    Args:
        params (FindHyperlinksInput):
            - text (str): входной текст
            - baseUrl (str): базовый URL для ссылок

    Returns:
        str: JSON {"text": "<html с расставленными ссылками>"}.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/v2/find-hyperlinks",
                headers=_headers(),
                json=params.model_dump(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при расстановке гиперссылок: {e}"


@mcp.tool(
    name="garant_get_prime_categories",
    annotations={
        "title": "Получить рубрики новостей ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_prime_categories() -> str:
    """Получить дерево рубрик для сервиса «Правовые новости» ГАРАНТ.

    Рубрики используются в garant_get_news для фильтрации новостей по теме.
    Каждая рубрика содержит id, text (название) и children (вложенные рубрики).

    Returns:
        str: JSON {"categories": [...]} с деревом рубрик.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/prime",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении рубрик: {e}"


@mcp.tool(
    name="garant_get_news",
    annotations={
        "title": "Получить правовые новости ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_news(params: CreateNewsInput) -> str:
    """Получить правовые новости ГАРАНТ по выбранным рубрикам и диапазону дат.

    Новости привязаны к конкретным нормативным актам и содержат краткие
    аналитические обзоры изменений. Диапазон дат — не более 10 дней.

    Args:
        params (CreateNewsInput):
            - categories (list[int]): ID рубрик (из garant_get_prime_categories)
            - fromDate (str): начало диапазона (YYYY-MM-DD)
            - toDate (str, optional): конец диапазона (YYYY-MM-DD)
            - sort (int): 1 — по дате (убывание), 2 — по алфавиту

    Returns:
        str: JSON {"news": [{"name": str, "document": {...}, "paragraphs": [...]}]}.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            body = params.model_dump(exclude_none=True)
            resp = await client.post(
                f"{BASE_URL}/v2/prime/create-news",
                headers=_headers(),
                json=body,
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении новостей: {e}"


@mcp.tool(
    name="garant_search_court_practice",
    annotations={
        "title": "Поиск по судебной практике ГАРАНТ (Сутяжник)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def garant_search_court_practice(params: SutyazhnikSearchInput) -> str:
    """Поиск по судебной практике с привязкой к нормам законодательства.

    Возвращает судебные дела, сгруппированные по нормам, которые применялись
    в спорах по данной теме. Полезно для анализа правоприменительной практики.

    Args:
        params (SutyazhnikSearchInput):
            - text (str): запрос (до 1000 символов)
            - count (int): количество результатов (1–1000)
            - kind (list[str], optional): фильтр ['301', '302', '303']

    Returns:
        str: JSON {"documents": [{"norms": [...], "courts": [...], "kind": str}]}.
             norms — нормы закона, courts — судебные дела.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            body = params.model_dump(exclude_none=True)
            resp = await client.post(
                f"{BASE_URL}/v2/sutyazhnik-search",
                headers=_headers(),
                json=body,
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при поиске судебной практики: {e}"


@mcp.tool(
    name="garant_get_limits",
    annotations={
        "title": "Получить лимиты API ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_get_limits() -> str:
    """Получить текущие лимиты на использование API ГАРАНТ.

    Возвращает массив ограничений: для каждой группы endpoint указано
    название лимита, значение (количество запросов) и список URL.

    Returns:
        str: JSON-массив [{title, value, names, url}].
    """
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/v2/limits",
                headers=_headers(),
            )
            if resp.status_code != 200:
                return _handle_error(resp)
            return json.dumps(resp.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Ошибка при получении лимитов: {e}"


@mcp.tool(
    name="garant_download_document_url",
    annotations={
        "title": "Получить ссылку для скачивания документа ГАРАНТ",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def garant_download_document_url(
    topic: int = Field(..., description="Номер документа."),
    format: str = Field(
        default="pdf",
        description="Формат файла: 'pdf', 'rtf' или 'odt'.",
        pattern="^(pdf|rtf|odt)$",
    ),
) -> str:
    """Сформировать URL для скачивания документа в формате PDF, RTF или ODT.

    Возвращает готовый URL со встроенным токеном авторизации.
    Фактическое скачивание происходит при переходе по URL.

    Args:
        topic (int): номер документа.
        format (str): 'pdf', 'rtf' или 'odt'.

    Returns:
        str: JSON {"url": str, "topic": int, "format": str}.
    """
    suffix_map = {"pdf": "download-pdf", "rtf": "download", "odt": "download-odt"}
    suffix = suffix_map[format]
    token = _TOKEN or os.environ.get("GARANT_TOKEN", "")
    url = f"{BASE_URL}/v2/topic/{topic}/{suffix}"
    return json.dumps(
        {
            "url": url,
            "topic": topic,
            "format": format,
            "note": f"Добавьте заголовок 'Authorization: Bearer {token[:8]}...' при запросе.",
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    if transport == "stdio":
        mcp.run()
    else:
        port = int(os.environ.get("PORT", 8000))
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port, path="/mcp")
