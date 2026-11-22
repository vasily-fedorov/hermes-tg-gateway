# hermes-tg-gateway

Плагин Hermes: шлюзовой профиль агента для межагентного обмена через Telegram.
Пара к сервису-боту [`tg-gateway`](../tg-gateway) (хаб). Протокол — JSON-RPC 2.0 /
A2A v1.0 поверх ЛС Telegram, описан в `docs/protocol.md` хаба.

Плагин **не содержит** маршрутов, карточек-подтверждений и БД — всё это в хабе.
Здесь провод и две ступени политики: **вход** (принять задачу) и **выход** (проверить
ответ перед отправкой).

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

Клиент (любой профиль агента, тулсет `gateway_relay`):

- `relay_send(target, text)` — создать исходящую задачу (в `endpoint` — JSON-RPC к хабу, в `group` — карточка владельцу);
- `relay_status(task_id)` — `tasks/get` у хаба: `state`, `done`, `progress`, `answer`;
- `relay_inbox(limit, ack)` — ответы других агентов, пришедшие асинхронно;
- `relay_cancel(task_id)` — `tasks/cancel`;
- `relay_protocol()` — текст протокола от хаба;
- `relay_routes()` — актуальный список адресатов (`agent/card` у хаба), локальный файл — фолбэк;
- `gateway_inbox(ack)` — недоставленное/ждущее владельца (legacy-режим).

Исполнитель (профиль `gateway`):

- `relay_draft(task_id, text)` — **положить ответ в outbox**: хаб получит текст только
  после проверки выходным шлюзом. Основной путь ответа;
- `relay_answer(task_id, text)` — прямой ответ мимо шлюза (пишет аудит `answer_bypass_gate`);
- `ask_default(question)` — короткий ручной вопрос своему default-профилю.

## Как формируется ответ

```
default (ребёнок делегации) ──relay_draft──► profiles/gateway/gateway-outbox.json
                                                     │
                                        watcher: outbox_drain() каждые 3 с
                                                     │
                        outbound_gate: edit → anchors → secrets → danger → limit
                                                     │
                                     tasks/update(completed, artifact) → хаб
```

Выходной шлюз (`outbound_gate`) — **детерминированный код**, не LLM-судья:

| Ступень | Что делает | Аудит |
|---|---|---|
| `edit` | правка формулировок моделью агента (режим `policy.outbound_edit`: `off`\|`safe`\|`always`) | `edit_applied` / `edit_rejected:<причина>` / `edit_failed` |
| anchors | числа, IP, версии, пути, команды в бэктиках и строгие отрицания обязаны остаться; коридор 0.4–1.7× | `lost:<вид>` / `negation_lost:<маркер>` |
| secrets | токены, ключи, приватные ключи, e-mail → `***` | `secrets_masked` |
| danger | опасные фрагменты → `[опасный фрагмент: <правило> — не исполнять]` | `danger_neutralized:<правила>` |
| limit | обрезка по `max_text` маршрута | `truncated:<было>-><стало>` |

Если правка не прошла проверку — уходит **дословный** черновик. Короткий текст с
«сейчас проверю/уточню» не отправляется вовсе (`plan_not_answer`, задача `failed`).

## Вход

`pre_gateway_dispatch` (хук) — единственная точка входа в агента:

1. в `endpoint`-режиме принимается только сообщение от `hub.bot_id`, остальные боты → `bot_not_allowed`;
2. `scan_incoming` + окно ±60 симв. вокруг опасного фрагмента: если рядом императив — отказ
   с правилом и фрагментом; если это отчёт — фрагмент нейтрализуется, текст проходит;
3. `annotate_foreign_code` — чужой код помечается как данные, не исполняется;
4. `filter_inbound` + рамка `[A2A inbound … untrusted]` (модуль A2A-security Hermes);
5. `kind=answer` → в инбокс, без хода модели.

## Гарантии и границы

- Задачи живут только в хабе; локально — кэш маршрутов и outbox.
- Один watcher на агента: flock на `<home>/gateway-watcher.lock` (в процессе живут две
  копии плагина — без лока каждая задача обрабатывалась дважды).
- Шлюз — фильтр, не песочница: делегированный ребёнок работает с правами default-профиля.

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
python3 tests/test_gateway_relay_hook.py  # хук, endpoint, outbox, правка (35 групп)
```
