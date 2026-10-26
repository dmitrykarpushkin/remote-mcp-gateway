# remote-mcp-gateway

[English](README.md) · **Русский**

[![CI](https://github.com/dmitrykarpushkin/remote-mcp-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/dmitrykarpushkin/remote-mcp-gateway/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Claude в телефоне или в браузере получает доступ к вашей машине — по ключу, с журналом каждого вызова и без shell.**

Для тех, кто хочет, чтобы облачный ассистент (кастомный коннектор claude.ai, голосовой режим, Claude Code,
Agent SDK) мог заглянуть на сервер, прочитать заметки и передать работу фоновым агентам, но не получал полной
свободы действий.

```text
> what are my coding sessions doing?
  ⎿ sessions_overview()
[website] Fix the footer — waiting for you, active 3 min ago
  agent said last: The footer overlaps the cookie banner below 380px. Should I move the banner up?

> ask the website agent to go ahead and move the banner
  ⎿ delegate_task(task="Website session: yes, move the cookie banner above the footer")
Accepted (id t3f9a1c). The result will appear in task_updates.
```

*Пример сессии: модель видит, чем заняты агенты-программисты, и ставит задачу в очередь, но сама не выполняет
ни одной команды.*

## Зачем

- **Работает с клиентами, которые не умеют свои заголовки.** Ключ принимается в `Authorization: Bearer`,
  `X-API-Key`, `X-Gateway-Key`, а для клиентов без заголовков — первым сегментом пути (в журнале он замаскирован).
- **Каждый вызов записывается до того, как выполнится.** Имя инструмента и аргументы попадают в `calls.jsonl`:
  что сделала модель, можно проверить, а не верить её пересказу.
- **Только чтение, пока вы не разрешите больше.** Инструменты по умолчанию только читают, а доступ к файлам
  ограничен одной папкой: никаких `..`, абсолютных путей, скрытых файлов и симлинков наружу.
- **Делегирование без shell.** `delegate_task` только ставит текст в очередь; задачи забирают отдельные агентские
  сессии в песочнице и сдают результат обратно.
- **Маленький и покрыт тестами.** Построен на FastMCP; 39 тестов идут без сети и без настоящего `claude`.

## Чем отличается

| | Локальный MCP-сервер (stdio) | stdio-сервер, проброшенный в HTTP через туннель | **remote-mcp-gateway** |
|---|---|---|---|
| Доступен из claude.ai, с телефона, голосом | нет | да | да |
| Авторизация, которую пройдёт клиент без заголовков | не нужна | делаете сами | встроена |
| Журнал каждого вызова | делаете сами | делаете сами | встроен, пишется до вызова |
| Передача задач фоновым агентам | нет | нет | плагин по желанию |

Если ассистент работает только на вашем ноутбуке, локальный stdio-сервер проще и безопаснее. Шлюз нужен, когда
клиент живёт в облаке и должен дотянуться до вашей машины через интернет.

## Быстрый старт

```bash
git clone https://github.com/dmitrykarpushkin/remote-mcp-gateway && cd remote-mcp-gateway
pip install -e . && cp gateway.example.toml gateway.toml   # задайте files.root, sessions.projects, plugins
GATEWAY_CONFIG=gateway.toml mcp-gateway                     # http://127.0.0.1:8766/mcp, ключ в .state/key
```

Закройте его TLS (Cloudflare Tunnel, Tailscale Funnel или nginx) и добавьте как кастомный коннектор с заголовком
`Authorization: Bearer <содержимое .state/key>`. Для Claude Code:

```bash
claude mcp add --transport http workspace https://your-host/mcp --header "Authorization: Bearer $(cat .state/key)"
```

## Как устроено

```text
MCP-клиент --HTTPS--> проверка ключа --> сервер FastMCP --> журнал (calls.jsonl)
                                            ├─ files       только чтение, одна корневая папка
                                            ├─ sessions    только чтение: сессии Claude Code
                                            ├─ memory      заметки только на дозапись (по желанию)
                                            └─ delegation  очередь задач + диспетчер (по желанию)
```

Плагины, диспетчеры (опрос, любая команда, сохранённый удалённый триггер Claude Code) и решения в дизайне описаны
в [docs/design.md](docs/design.md) (на английском).

## Статус

Работает «руками» личного голосового ассистента: с телефона он смотрит, чем заняты агенты на сервере,
читает общие заметки и передаёт задачи. В октябре 2026 года ядро переписано на FastMCP.

## Разработка

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check .
pytest -q
```

---

Лицензия: [MIT](LICENSE) · Автор: [Dmitry Karpushkin](https://github.com/dmitrykarpushkin)
