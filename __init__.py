"""gateway-relay — approval cards, relay tools and the inbound pump for `gateway`."""
from __future__ import annotations

import asyncio
from pathlib import Path

from . import core

_ROUTES_SCHEMA = {
    "name": "relay_routes",
    "description": "Список разрешённых адресатов для передачи сообщений. Других адресатов не существует.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_SEND_SCHEMA = {
    "name": "relay_send",
    "description": (
        "Передать сообщение другому агенту через супергруппу. НЕ отправляет сразу: "
        "владельцу уходит карточка в топик approvals с кнопками «Отправить»/«Отклонить». "
        "Вызывать можно свободно — без нажатия кнопки ничего не уйдёт."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Ключ маршрута из relay_routes"},
            "text": {"type": "string", "description": "Текст сообщения (без секретов)"},
        },
        "required": ["target", "text"],
    },
}

_PROTOCOL_SCHEMA = {
    "name": "relay_protocol",
    "description": ("Протокол tg-gateway в формате для агента: какие сообщения приходят, "
                    "как отвечать, какие методы и правила. Вызови, если не уверен в формате."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_STATUS_SCHEMA = {
    "name": "relay_status",
    "description": ("Статус задачи в хабе (A2A tasks/get): состояние, вопрос, артефакт. "
                    "Работает только в endpoint-режиме."),
    "parameters": {
        "type": "object",
        "properties": {"task_id": {"type": "string", "description": "task_id от relay_send"}},
        "required": ["task_id"],
    },
}

_CANCEL_SCHEMA = {
    "name": "relay_cancel",
    "description": (
        "Отменить свою задачу (только инициатор). Владельцу уходит карточка "
        "«Отменить?»; после подтверждения пиру отправляется уведомление об отмене."
    ),
    "parameters": {
        "type": "object",
        "properties": {"task_id": {"type": "string", "description": "task_id из relay_send"}},
        "required": ["task_id"],
    },
}

_ASK_SCHEMA = {
    "name": "ask_default",
    "description": (
        "Спросить свой default-профиль (мозги агента) и получить текстовый ответ. "
        "Вопрос уходит как внешний запрос через gateway."
    ),
    "parameters": {
        "type": "object",
        "properties": {"question": {"type": "string", "description": "Вопрос default-профилю"}},
        "required": ["question"],
    },
}

_INBOX_SCHEMA = {
    "name": "gateway_inbox",
    "description": (
        "Принятые владельцем сообщения от других агентов (что пришло через gateway). "
        "ack=true очищает инбокс после прочтения."
    ),
    "parameters": {
        "type": "object",
        "properties": {"ack": {"type": "boolean", "description": "Пометить прочитанным"}},
        "required": [],
    },
}


def _telegram_callback_factory(native, adapter):
    """Owner's card buttons. Scoped by pattern so core button flows keep working."""
    from telegram.ext import CallbackQueryHandler

    async def _on_callback(update, context):
        query = getattr(update, "callback_query", None)
        if query is None:
            return
        payload = query.data or ""
        if not payload.startswith("gw"):
            return
        message = getattr(query, "message", None)
        await asyncio.to_thread(
            core.resolve_card_click, payload,
            str(getattr(query.from_user, "id", "")), query.id,
            str(getattr(message, "chat_id", "")), str(getattr(message, "message_id", "")),
        )

    native.add_handler(CallbackQueryHandler(_on_callback, pattern=r"^gw(out|in):"))



_ANSWER_SCHEMA = {
    "name": "a2a_answer",
    "description": ("Финализировать задачу хаба своим ответом. Вызывается ИСПОЛНИТЕЛЕМ "
                    "(профиль, которому делегировали): текст уходит в хаб дословно, задача "
                    "закрывается как completed."),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "hub_task из делегированной задачи"},
            "text": {"type": "string", "description": "Ответ по существу, дословно"},
        },
        "required": ["task_id", "text"],
    },
}

_PROGRESS_SCHEMA = {
    "name": "a2a_progress",
    "description": ("Сообщить хабу прогресс по задаче, не закрывая её (хартбит). "
                    "Используй при долгой работе: «собираю образ», «3 из 5 проверок»."),
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "hub_task"},
            "text": {"type": "string", "description": "Что сейчас происходит"},
        },
        "required": ["task_id"],
    },
}


_TASK_SCHEMA = {
    "name": "a2a_task",
    "description": ("Состояние задачи в хабе (A2A tasks/get): state, прогресс, ответ (artifact), "
                    "признак done. Используй после relay_send/a2a_call: задача выполняется "
                    "асинхронно, ответ забирают этим инструментом или из a2a_inbox."),
    "parameters": {
        "type": "object",
        "properties": {"task_id": {"type": "string", "description": "task_id задачи"}},
        "required": ["task_id"],
    },
}

_INBOX_A2A_SCHEMA = {
    "name": "a2a_inbox",
    "description": ("Ответы, пришедшие от других агентов асинхронно: from, task, text, ago_s. "
                    "По умолчанию забирает и очищает прочитанное (ack=true)."),
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Сколько последних ответов вернуть (по умолчанию 10)"},
            "ack": {"type": "boolean", "description": "Пометить прочитанными (по умолчанию true)"},
        },
        "required": [],
    },
}

def register(ctx) -> None:
    # The ingress copy (launch profile home) only needs the inbound hook.
    ctx.register_hook("pre_gateway_dispatch", core.pre_gateway_dispatch)
    ctx.register_telegram_handler(_telegram_callback_factory)

    # Регистрируем полный набор в КАЖДОМ профиле: что реально видно модели,
    # решает конфиг профиля (`toolsets` / `platform_toolsets` → gateway_relay).
    # Хаб-карточка остаётся единственным гейтом на отправку, поэтому профиль
    # gateway тоже может инициировать запрос, если владелец его об этом просит.
    ctx.register_tool(name="gateway_inbox", toolset="gateway_relay",
                      schema=_INBOX_SCHEMA, handler=core.tool_inbox,
                      description="Owner-approved inbound messages", emoji="\U0001f4e5")
    ctx.register_tool(name="relay_routes", toolset="gateway_relay",
                      schema=_ROUTES_SCHEMA, handler=core.tool_routes,
                      description="Allowlisted relay destinations", emoji="\U0001f517")
    ctx.register_tool(name="relay_send", toolset="gateway_relay",
                      schema=_SEND_SCHEMA, handler=core.tool_send,
                      description="Relay via an owner-approved card", emoji="\u2709")
    ctx.register_tool(name="relay_protocol", toolset="gateway_relay",
                      schema=_PROTOCOL_SCHEMA, handler=core.tool_protocol,
                      description="Agent-facing protocol text", emoji="\U0001f4d8")
    ctx.register_tool(name="relay_status", toolset="gateway_relay",
                      schema=_STATUS_SCHEMA, handler=core.tool_status,
                      description="Task status via hub", emoji="\U0001f50e")
    ctx.register_tool(name="relay_cancel", toolset="gateway_relay",
                      schema=_CANCEL_SCHEMA, handler=core.tool_cancel,
                      description="Cancel a submitted task", emoji="\u21a9")
    ctx.register_tool(name="a2a_task", toolset="gateway_relay",
                      schema=_TASK_SCHEMA, handler=core.tool_task,
                      description="Hub task state (A2A tasks/get)", emoji="\U0001f50e")
    ctx.register_tool(name="a2a_inbox", toolset="gateway_relay",
                      schema=_INBOX_A2A_SCHEMA, handler=core.tool_a2a_inbox,
                      description="Async answers from other agents", emoji="\U0001f4ec")
    ctx.register_tool(name="a2a_answer", toolset="gateway_relay",
                      schema=_ANSWER_SCHEMA, handler=core.tool_answer,
                      description="Finish a hub task with the answer", emoji="\u2705")
    ctx.register_tool(name="a2a_progress", toolset="gateway_relay",
                      schema=_PROGRESS_SCHEMA, handler=core.tool_progress,
                      description="Report hub task progress", emoji="\u23f3")
    ctx.register_tool(name="relay_task", toolset="gateway_relay",
                      schema={**_TASK_SCHEMA, "name": "relay_task"}, handler=core.tool_task,
                      description="Hub task state (A2A tasks/get)", emoji="\U0001f50e")
    ctx.register_tool(name="relay_inbox", toolset="gateway_relay",
                      schema={**_INBOX_A2A_SCHEMA, "name": "relay_inbox"},
                      handler=core.tool_a2a_inbox,
                      description="Async answers from other agents", emoji="\U0001f4ec")
    ctx.register_tool(name="relay_answer", toolset="gateway_relay",
                      schema={**_ANSWER_SCHEMA, "name": "relay_answer"}, handler=core.tool_answer,
                      description="Finish a hub task with the answer", emoji="\u2705")
    ctx.register_tool(name="ask_default", toolset="gateway_relay",
                      schema=_ASK_SCHEMA, handler=core.tool_ask_default,
                      description="Ask this agent's default profile", emoji="\U0001f9e0")
    core.start_watcher(ctx)
