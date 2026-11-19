# hermes-tg-gateway

Плагин Hermes: шлюзовой профиль агента для межагентного обмена через Telegram.
Пара к сервису-боту [`tg-gateway`](../tg-gateway) (хаб). Протокол — JSON-RPC 2.0 /
A2A v1.0 поверх ЛС Telegram, описан в `docs/protocol.md` хаба.

Плагин **не содержит** маршрутов, карточек-подтверждений и БД — всё это в хабе.
Здесь только провод: принять задачу, прогнать ход профиля, ответить.

## Два режима

| режим | когда | что делает |
|---|---|---|
| `endpoint` (основной) | есть хаб | принимает `message/send` только от `hub.bot_id`, отвечает `tasks/update` |
| `group` (legacy) | хаба нет | самостоятельный relay в супергруппе: карточки владельцу, реестр `gateway-routes.json` |

Переключение — поле `mode` в `gateway-routes.json` профиля `gateway`:

```json
{"mode": "endpoint", "hub": {"bot_id": 1000000001, "username": "my_hub_bot"}}
```

## Инструменты

- `relay_send(target, text)` — создать исходящую задачу (в `endpoint` — JSON-RPC к хабу, в `group` — карточка владельцу);
- `relay_status(task_id)` — `tasks/get` у хаба;
- `relay_cancel(task_id)` — `tasks/cancel`;
- `relay_protocol()` — текст протокола от хаба (что от агента ждут и в каком формате);
- `ask_default(question)` — тихий ход своего default-профиля (у него есть инструменты);
- `gateway_inbox(ack)` — недоставленное/ждущее владельца;
- `relay_routes()` — реестр (только `group`).

## Установка

Плагин ставится в два дома (иначе не работают кнопки в `group`-режиме):

```
<profile-home>/plugins/gateway-relay/    # инструменты, watcher
<launch-home>/plugins/gateway-relay/     # хук + фабрика callback-хендлера
```

Имя в `plugin.yaml` — `gateway-relay`; в агенте с `plugins.enabled: [group-gateway]`
манифест переименовывается при деплое (см. AGENTS.md).

## Тесты

```bash
python3 tests/test_state.py               # машина состояний (9 групп)
python3 tests/test_gateway_relay_hook.py  # хук/карточки/endpoint (24 группы)
```
