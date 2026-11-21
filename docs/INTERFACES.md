# LedgerGym — environment interfaces v0.4

## Canonical judge protocol (Role 3, 21 November 2026)

The root `judge_adapter.py` is the organizer entry point. The older flat-action interface below remains a compatibility API, not the canonical judge transport. Runtime uses only the Python standard library; tests use the pinned `requirements-role3-test.txt`.

```python
generate_episode(seed, config, output_dir)  # delegates existing generator/export; returns None
make_env()                                # trusted judge object with reset and step
score_episode(episode_dir, findings, inspection_steps)
```

Generation accepts the existing Role 2 team configuration. The output contains `public/` (manifest, policy, ledger, invoices, payments, fx) and judge-only `private/` (truth, provenance). Existing nonempty output directories are not overwritten. It does not replace or expand the financial generator.

`env.reset(seed, {"mode":"closed","episode_dir":path,"team_config":{}})` loads those supplied files, preserves IDs/order/values, and never regenerates after a load failure. `mode="train"` without episode_dir delegates the existing generator using team_config. Reset failures disable the prior episode and return a bounded exception, not a private path or traceback message. Initial output is `({"task":str,"manifest":object,"policy":object,"remaining_steps":100}, {})`.

Canonical actions are `{"name":NAME,"args":ARGUMENTS}`:

| Name | Args | Successful result |
| --- | --- | --- |
| list_records | table, cursor (null first), limit (1–50) | {records:[...],next_cursor:null/string} |
| get_record | table, id | record object |
| get_document | doc_id | invoice/payment object |
| calculator | expression | Decimal result string |
| submit | findings: {episode_id, findings:[...]} | {accepted:true} |

Step returns `({"result":value_or_null,"error":null_or_{code,message},"remaining_steps":int}, reward, terminated, truncated, {})`. Unknown actions/tables/IDs and malformed reads spend one action and produce bounded errors. Malformed submit terminates; closed reward is still zero. The findings validator and matcher remain Role 4 implementations; their documented outstanding normalization defects are not silently replaced here.

One hundred actions include submit; 99 inspections plus submit are accepted, while 100 inspections truncate to empty findings. Inspection cost excludes submit. The deadline starts at reset entry and includes policy execution. Completion freezes the result until reset. Post-terminal operations cannot rescore or append findings.

`score_episode` returns tp, fp, fn, precision, recall, f1 and return. Structurally invalid findings return null for the six metrics and return=-1; a bounded error is logged on the trusted evaluator logger. `env.final_score` is evaluator-only. Closed policy rewards are always zero and public info is empty, including terminal and malformed-submit responses. Train returns terminal reward. Scoring uses existing evaluation code and its official formula.

Canonical cursors are deterministic, table/page-bound and accepted only after issuance in the current reset. Reset clears issued authority. After an identical page is legitimately issued again, an identical historical string is necessarily indistinguishable from the newly issued string; current issuance is the authority. Native legacy clients retain their existing random tokens and portable replay. Exact canonical replay uses unchanged literal actions and full observable-value comparison, including tokens.

`run_file_agent(seed, config, agent_path, timeout=60)` in `ledgergym.isolated_runner` runs a policy through the restricted Docker path. Only its script is mounted; source, episode files, truth and Docker socket are not mounted. There is no unsandboxed fallback. Network is disabled; filesystem and process resources are restricted. Returned score/trajectory are trusted caller artifacts. Missing Docker/image is an explicit runtime limitation, not evidence of isolation.

`FlightRecorder` and `verify_replay` in `ledgergym.flight_recorder` record/compare episode_id, step, action, observation, visible reward, terminated and truncated without adding truth to observations. A same-process judge object or recorder is not a security boundary: untrusted policies must never receive it directly.

Verification: `python -m ledgergym.role3_mirror`. Demos: `python -m ledgergym.role3_demo local --trajectory trajectories.jsonl`; `python -m ledgergym.role3_demo restricted --episode PATH --trajectory trajectories.jsonl`. The restricted demo must run the real pinned Docker image or report NOT_RUN.

See ROLE3_PHASE1_VERIFICATION.md, ROLE3_PHASE2_SECURITY.md and ROLE3_FINAL_VERIFICATION.md for actual results and limitations. The 20 paired tests cover environment transport and replay; they do not certify the Role 2/4 financial D01–D20 content.

## Historical native contract v0.3

Статус: ПРОЕКТ, требуется сверка с оригинальным FinTech PDF и review команды. Разработка разрешена капитаном 20.11.2026; в команде три человека, персональные назначения ещё не предоставлены. Контракт не является подтверждением условий организаторов.

## Границы

Эпизод: одна синтетическая компания и период. Публичные файлы: `manifest.json`, `ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`, `policy.json`. Частные: `truth.json`, `provenance.json` и seed закрытого эпизода. Агент видит только публичные данные. Скрытие поля Python не является изоляцией: недоверенный агент требует отдельного процесса с ограничением файловой системы, сети и процессов. До проверки такой границы нельзя заявлять закрытую безопасную оценку.

Минимальные поля публичных таблиц согласно мастер-спецификации: manifest (`schema_version`, `episode_id`, `base_currency`, `period_start`, `period_end`, `timezone`, counts, rounding); ledger (`row_id`, `timestamp`, `account`, `debit_minor`, `credit_minor`, `currency`, `entity_id`, `invoice_id`, `payment_id`); invoices (`doc_id`, `invoice_id`, `entity_id`, `issued_at`, `due_at`, `currency`, `total_minor`, `line_items`); payments (`doc_id`, `payment_id`, `timestamp`, `currency`, `amount_minor`, `invoice_refs`); FX (`date`, `source_currency`, `target_currency`, `rate`); policy (FX date, period cutoff, rounding). Время ISO 8601 с offset; деньги целые минимальные единицы; FX как десятичная строка. Null означает неизвестную/отсутствующую ссылку, а не ноль.

## Находка и эталон

Предлагаемые коды: `duplicate_invoice`, `payment_allocation`, `fx_rate_or_date`, `reporting_period`. Находка содержит `type`, `affected_ids` (непустой массив публичных идентификаторов), `claimed_amount_minor` (целое число), `currency` (трёхбуквенный код), `evidence_ids` (массив публичных ID), `explanation` (строка). Submit: `{episode_id, findings}`. Пределы: 30 находок, 10 evidence IDs на находку, 1000 символов объяснения. Дубли идентификаторов в списках считаются некорректной структурой; точные ID чувствительны к регистру, порядок в списках значения не имеет. Отсутствующий или несуществующий ID не может быть доказательством.

Private truth: `issues` содержит `issue_id`, `type`, `affected_ids`, `expected_amount_minor`, `currency`, `allowed_evidence_sets`. Полный набор допускается как подмножество evidence: дополнительные ID должны существовать в публичных данных; их релевантность отдельно не штрафуется. Этот вариант нуждается в сверке с кейсом и review. Точное совпадение суммы в minor units (допуск 0) — временное проектное решение, не установленный официальный допуск.

Значение суммы — абсолютная сумма выявленного расхождения в указанной валюте: дублированная сумма, нераспределённая/неверно распределённая сумма, разница FX в валюте учёта, сумма неверно отнесённой операции. Для спорных пересечений и частичных случаев нужна финальная фиксация владельцами генератора и оценщика. Округление FX — Decimal по опубликованной policy с явной разрядностью валюты. Запрещены float и смешение разных валют при суммировании.

### Financial Amount Semantics

`expected_amount_minor` (Private Ground Truth) и `claimed_amount_minor` (Agent Submission) представляют денежную величину конкретной финансовой аномалии в минимальных единицах валюты, указанной в `currency`.

Экономический смысл зависит от `type`:

- `duplicate_invoice` — номинальная сумма одного дублирующегося счёта в валюте счёта.
- `payment_allocation` — стоимость суммы платежа, не распределённой на правильный счёт, пересчитанная в KZT по корректному курсу.
- `fx_rate_or_date` — абсолютная разница между корректной суммой платежа в KZT и суммой, отражённой в бухгалтерской проводке.
- `reporting_period` — стоимость счёта, отражённого в неправильном отчётном периоде, в KZT.

Эти величины описывают финансовые расхождения, ошибочно отражённые суммы или потенциально дублированные обязательства. Они **не являются автоматически подтверждёнными денежными убытками**.

В compound-сценариях несколько ошибок могут затрагивать одну операцию. Суммирование `expected_amount_minor` по всем issues не является корректным универсальным способом расчёта совокупного финансового ущерба. Кроме того, запрещено складывать суммы в разных валютах без приведения к общей валюте.

Текущий evaluator сопоставляет отдельные findings с issues и рассчитывает метрики качества обнаружения. Совокупный финансовый убыток не рассчитывается.

### Financial Impact Aggregation Design (Proposed)

**Статус:** проект интерфейса. Финансовый анализатор ещё не реализован.

#### Назначение

Финансовая аналитика LedgerGym должна различать:

- количество финансовых аномалий;
- денежную величину каждой отдельной аномалии;
- связи между аномалиями, затрагивающими общие финансовые объекты;
- подтверждённый денежный ущерб, если для его расчёта имеется обоснованная методика и достаточно данных.

`expected_amount_minor` не является универсальной оценкой фактического убытка. Суммирование этих значений не должно автоматически интерпретироваться как совокупный финансовый ущерб.

#### Разделение ответственности

Существующий `score.py` отвечает за оценку качества обнаружения ошибок агентом и возвращает `tp`, `fp`, `fn`, `precision`, `recall`, `f1`, `reward`.

Предлагаемый отдельный модуль `ledgergym/financial_impact.py` должен отвечать за анализ финансовых аномалий и их взаимосвязей.

Добавление финансовой аналитики не должно изменять формулу `reward`, правила сопоставления findings с issues или контракт `score.py`.

#### Предлагаемый интерфейс

`analyze_financial_impact(public, truth, provenance)`

Предлагаемая структура результата:

```python
{
    "issue_count": 2,
    "anomalies": [
        {
            "issue_id": "...",
            "type": "duplicate_invoice",
            "amount_minor": 129861,
            "currency": "KZT"
        },
        {
            "issue_id": "...",
            "type": "payment_allocation",
            "amount_minor": 129861,
            "currency": "KZT"
        }
    ],
    "overlap_groups": [
        {
            "kind": "duplicate_allocation",
            "issue_ids": ["...", "..."],
            "payment_id": "..."
        }
    ],
    "confirmed_loss_minor": None,
    "confirmed_loss_currency": None
}
```

Этот пример иллюстрирует предлагаемый контракт, а не результат действующего API.

#### Правила обработки

**Clean world**

При отсутствии issues:

- `issue_count = 0`;
- `anomalies = []`;
- `overlap_groups = []`;
- `confirmed_loss_minor = None`;
- `confirmed_loss_currency = None`.

Отсутствие известных аномалий не доказывает отсутствие денежных убытков.

**Single-fault world**

Каждая аномалия сохраняет собственные `issue_id`, `type`, `amount_minor` и `currency`.

Отсутствие `compound_groups` не доказывает отсутствие экономических связей.

**Compound world**

`provenance["compound_groups"]` используется для представления явно заданных генератором связей между issues.

Общие идентификаторы финансовых объектов подтверждают связь, но сами по себе не устанавливают величину денежного ущерба.

#### Денежные величины и валюты

Все суммы сохраняются целыми числами в минимальных единицах соответствующей валюты.

Значения в разных валютах нельзя складывать без явно определённого правила конвертации.

В первой версии анализатора автоматический расчёт общей суммы финансовых аномалий не предусматривается.

#### Подтверждённый ущерб

`confirmed_loss_minor = None` означает, что величина подтверждённого ущерба не определена. Это не эквивалентно нулевому ущербу.

`confirmed_loss_currency = None` используется, когда сумма ущерба не определена.

В первой версии оба поля остаются `None` для всех сценариев. Расчёт ущерба потребует отдельной методики и проверки.


#### Приватность

`truth` и `provenance` содержат приватные данные генератора.

Финансовый анализатор предназначен для внутреннего аудита и не должен раскрывать Private Ground Truth агенту через публичный интерфейс.

#### Совместимость

Предлагаемая функциональность должна быть добавлена отдельно от существующего evaluator.

Реализация не должна изменять:

- структуру `public`, `truth` и `provenance`;
- существующие типы issues и их денежную семантику;
- формат Agent Submission;
- результаты и формулу вознаграждения `score.py`.

#### Ограничения

Первая версия финансовой аналитики предоставляет структурированное описание аномалий и явно известных compound-связей.

Она не рассчитывает фактический денежный ущерб, не доказывает экономическую независимость ошибок и не выполняет автоматическую дедупликацию денежных сумм.

Для сопоставления строится двудольный граф допустимых пар и находится максимальное 1:1 паросочетание; TP — его размер, FP — прочие находки, FN — прочие issues. При пустом эталоне и пустом ответе F1=1; при пустом эталоне и непустом ответе F1=0; иначе F1=2TP/(2TP+FP+FN). Precision/recall при нулевом знаменателе 0. Итоговая награда `clip(2*F1 - 1 - 0.002*inspection_steps, -1, 1)`, за исследовательские шаги 0. Неверная структура submit: терминальная -1. Текст объяснения не определяет совпадение.

## Среда и безопасность

`reset(seed, config) -> (observation, info)` и `step(action) -> (observation, reward, terminated, truncated, info)`. Только `list_records`, `get_record`, `get_document`, `calculator`, `submit`; страница до 50 строк, 100 действий включая submit. Неверный вызов тратит шаг. Временное решение: inspection_steps считает все действия, кроме submit, включая неверные; submit допускается на шаге 100. Исчерпание бюджета/тайм-аут: truncated с пустым ответом, без дополнительного действия. Повторное действие после окончания не начисляет награду.

Режим closed: reward и диагностика не передаются агенту до окончания прогона; до интеграционного решения способ безопасной доставки агрегированного результата оценивается отдельно. Скрытый seed, truth, provenance, внутренние пути и tracebacks не попадают в наблюдения, логи и траектории. Cursor привязан к разрешённой таблице и эпизоду; калькулятор поддерживает только ограниченную Decimal-арифметику, без eval/exec.

### JSON-действия и ответы текущей реализации

Ниже описан исполняемый контракт `LedgerSandbox`, а не дополнительное требование организаторов. Все действия — JSON-объекты. Обязательные поля должны присутствовать; дополнительные поля отвергаются. Вложенный `args` не используется.

| `action` | Остальные обязательные поля | Необязательные поля | Успешное наблюдение |
| --- | --- | --- | --- |
| `list_records` | `table`: строка из списка ниже | `cursor`: полученная строка или null; `limit`: целое 1–50, по умолчанию 50 | `records`: массив; `next_cursor`: строка или null |
| `get_record` | `table`, `id`: строки | нет | `record`: объект |
| `get_document` | `doc_id`: строка | нет | `document`: объект invoice/payment |
| `calculator` | `expression`: строка | нет | `value`: десятичная строка |
| `submit` | `episode_id`: строка; `findings`: массив по схеме выше | нет | `status`: `finished` или `invalid_submit` |

Каждое наблюдение также содержит `remaining_steps`: целое 0–100. Разрешены только четыре таблицы и следующие первичные ключи:

| Таблица | Ключ `get_record` |
| --- | --- |
| `ledger` | `row_id` |
| `invoices` | `invoice_id` |
| `payments` | `payment_id` |
| `fx` | `rate_id` — существующее предварительное расширение учебных фикстур |

Наличие другой таблицы во входном объекте не добавляет её в разрешённый список. `manifest` и `policy` доступны через reset; `get_document` ищет только invoice/payment по `doc_id`. Читатели возвращают копии данных. Allowlist не проверяет все поля внутри разрешённых документов: корректность public/private разделения обязан обеспечить доверенный загрузчик; это не замена внешней изоляции.

Пример первой страницы:

```json
{"action":"list_records","table":"ledger","limit":50}
```

Для следующей страницы клиент передаёт ровно полученный `next_cursor`. Null означает отсутствие следующей страницы. Нельзя строить курсор из ID эпизода, номера строки или seed.

### Жизненный цикл курсора и воспроизведение

- Курсор — непрозрачная строка, выданная текущим экземпляром среды после последнего reset. Он связан с таблицей и смещением, но не содержит скрытый seed или метки truth.
- Одинаковая следующая позиция в пределах одного reset получает один и тот же курсор; повторный запрос с тем же курсором и limit возвращает ту же страницу.
- После reset старые курсоры отклоняются. Курсоры другого экземпляра среды, другой таблицы и невыданные значения тоже отклоняются.
- Строки курсоров случайны и не являются частью детерминированной сериализации эпизода. При воспроизведении расследования нужно заново получать курсоры из ответов новой среды. Сырые действия со старыми курсорами не воспроизводятся. Для повторного запуска используется описанный ниже переносимый формат ссылок на страницы.
- Реестр ограничен бюджетом: за один эпизод возможны не более 99 успешных исследовательских действий до обязательного завершения.

### Ошибки, бюджет и завершение

Некорректное исследовательское действие возвращает `{"error":"invalid_action","remaining_steps":N}`, нулевую награду и пустой `info`; вход, внутренние пути и traceback не отражаются в ответе. Неизвестный инструмент, лишнее поле, неизвестный ID, недопустимый limit/cursor и недопустимая арифметика расходуют один шаг.

Калькулятор принимает до 128 символов и до 50 AST-узлов: десятичные литералы, скобки, унарные `+/-`, операции `+`, `-`, `*`, `/`. Точность Decimal — 28 значащих цифр; литералы по модулю не больше 1e18, промежуточные результаты не больше 1e30. Это ограниченный калькулятор с округлением в контексте Decimal, а не арифметика неограниченной точности. Степень, импорт, вызовы функций, обращения к атрибутам, деление на ноль и scientific notation не поддерживаются.

| Событие | `terminated` | `truncated` | Действие оценщика |
| --- | --- | --- | --- |
| Корректное чтение/ошибка на шагах 1–99 | false | false | Не вызывается; reward=0 |
| Валидный submit на шагах 1–100 | true | false | Оценить findings; inspection_steps не включает submit |
| Malformed submit до исчерпания времени | true | false | Обычный matcher не вызывается; итог -1 |
| Исследовательский запрос на шаге 100 | false | true | Запрос не исполняется; пустой ответ, inspection_steps=100 |
| Истёкшее время перед обработкой действия | false | true | Пустой ответ; новый шаг не начисляется |
| Действие после завершения | — | — | `RuntimeError("episode ended; reset required")`; повторной оценки нет |

В open-режиме `_finish` возвращает итоговую награду и `info.score`. В closed-режиме числовой reward для агента всегда 0 и `info={}`, включая malformed submit; доверенный Docker-runner сохраняет окончательный результат отдельно и не отправляет терминальный score агенту. Для malformed submit runner фиксирует -1 вне обычного matcher. Это текущая проектная конвенция маскирования reward.

### Генерация при reset и совместимость v0.3

`LedgerSandbox()` создаёт среду с доверенной фабрикой `runtime.create_episode`. Каждый `reset(seed, config)` заново создаёт пару public/evaluator: оценщик замыкает truth только своего эпизода. Одинаковые seed/config воспроизводят содержимое выбранного эпизода и итоговую оценку; случайные курсоры исключены из побайтовой воспроизводимости.

- `seed`: целое число, bool отвергается; `None` выбирает свежий случайный 128-битный seed. Скрытый seed не записывается в observation/info/траекторию.
- `config=None`: `{"scenario":"duplicate_invoice","fault":true}`. Пустой объект и неизвестные поля отвергаются существующим генератором.
- Одиночные `scenario`: `duplicate_invoice`, `payment_allocation`, `fx_rate_or_date`, `reporting_period`; необязательный `fault` — bool, по умолчанию true.
- Составные `scenario`: `fx_allocation`, `duplicate_allocation`; необязательные `first_fault` и `allocation_fault` — bool, по умолчанию true.
- `scenario="company"`: `postings` 200–2000 (по умолчанию 400), `documents` 20–200 (по умолчанию 80), словари `faults`/`compounds` с количеством ошибок. Суммарно 0–12 ошибок, compound считается за две. Требуется `postings >= 2*documents+2` и достаточное число подходящих операций. Подробности и допустимые сочетания: `COMPANY_MODEL.md`.
- Параметры применяются заново при каждом reset, без наследования предыдущего config. Успешный reset выдаёт manifest/policy/remaining_steps=100 и info={}, обновляет таймер и полностью заменяет публичные данные, оценщик и курсоры.
- При ошибке reset предыдущий эпизод становится недоступен для step; восстановление — следующий успешный reset. Ошибки генерации относятся к доверенному оркестратору. Агентский JSON-протокол не предоставляет reset или фабрику.

`LedgerSandbox(public, evaluator)` сохраняет режим фиксированного загруженного эпизода; `reset()` восстанавливает копию public и бюджет. Передавать seed/config в этом режиме теперь запрещено (`ValueError`), поскольку они раньше молча игнорировались. Миграция: для генерации использовать конструктор без public/evaluator; для загруженного эпизода вызывать reset без параметров.

`LedgerSandbox(episode_factory=callable)` допускает другую **доверенную** фабрику `(seed, config) -> (public, evaluator)`. Она отвечает за схему, валидацию и отсутствие закрытых данных в public. Нельзя одновременно задавать фабрику и фиксированный эпизод. In-process callback не защищает truth от интроспекции недоверенного Python-кода; внешняя изоляция по-прежнему обязательна для закрытого оценивания. Малые генераторы не стали конкурсным benchmark от добавления factory.

### Переносимые траектории и replay

`run_baseline` возвращает `trajectory` как массив действий. В сохранённом действии `list_records` вместо случайного токена записывается `"cursor":{"from_step":N}`, где N — индекс предыдущего действия (с нуля), вернувшего нужный next_cursor. Это формат файла траектории; напрямую в `env.step` такой объект передавать нельзя. Первая страница не содержит cursor. Oracle по-прежнему возвращает trajectory=null.

`replay_actions(env, actions, seed=None, config=None)` выполняет reset, затем заменяет каждую ссылку на next_cursor из соответствующего ответа **текущего** запуска. Возвращает `initial`, `info` и `steps` (полные результаты step). Закрытый режим среды сохраняет маскирование оценки. Seed/config должны поступать из доверенного источника; replay не добавляет их в результат.

Ссылка допускается только на более раннее чтение той же таблицы, действительно выдавшее курсор. Сырые токены, будущие/отрицательные индексы, другая таблица и исчерпанная страница вызывают ValueError. Повторные ссылки на одну страницу допустимы. Значения episode_id, находок, limit и прочих полей не исправляются: ошибочный submit остаётся ошибочным. Replay допускает частичную траекторию, но отвергает действия после terminated/truncated. Остальные некорректные действия обрабатываются самой средой с обычным расходом бюджета. Ошибка replay не откатывает уже выполненные действия.

Для повторения нужен тот же public episode либо точные исходные seed/config/version; один episode_id не удостоверяет совпадение содержимого. Сырые ответы replay содержат новые курсоры и потому не являются канонической сериализацией траектории. Формула reward и matcher не менялись.

## Открытые решения

1. Сверить все условия с шестистраничным FinTech PDF; с положением — сроки/сдачу.
2. Утвердить коды, определение суммы, допуски, значения и области имён ID, корректность дополнительных evidence.
3. Провести review описанного v0.3 контракта actions/cursor/factory/replay, закрытого канала результатов, 100-го шага и тайм-аута.
4. Назначить людей/ревьюеров на три роли команды, покрыв четыре функциональные области; закрепить правила интеграции.
5. Подтвердить метод внешней изоляции для недоверенного кода и проверить её атаками.

## Предварительные расширения учебных примеров

Для демонстрации доказуемости введены `service_ref` внутри `line_items` вместе с `duplicate_rule`, `remittance_invoice_id` и `invoice_refs: [{invoice_id, amount_minor}]`, уникальный `rate_id` у строк FX и `reporting_period` у проводок. Эти поля и конкретные правила не подтверждены оригинальным FinTech PDF. При несоответствии официальному контракту понадобится миграция, а не утверждение, что расширения официальны. FX-пример использует только USD/KZT с двумя знаками, `ROUND_HALF_EVEN`, котировку target major per source major и дату операции; пример cutoff использует фиксированное смещение, не исторические правила IANA timezone.

Сохранение `public/` и `private/` в `ledgergym.episode_io` предназначено для локального воспроизведения. Это не защитная граница. Закрытый seed сохраняется только в `private/provenance.json`. Для реальной скрытой оценки агент не должен иметь доступ к родительскому каталогу, файловой системе оценщика или его процессу.

## Конфигурация учебного генератора

`generate_episode(seed, {"scenario": ..., "fault": bool})` поддерживает четыре отдельных сценария. Для `fx_allocation` и `duplicate_allocation` используются независимые `first_fault` и `allocation_fault` (по умолчанию включены). В FX-сценарии сумма ошибки распределения — KZT minor units, полученные из нераспределённого остатка USD по публичному курсу на дату операции; строка FX входит в обязательные evidence. Ошибка курса и ошибка распределения измеряют разные расхождения одной операции и не предназначены для простого сложения как общая сумма ущерба.

Все решения и дополнительные поля предварительны. Предсказуемый генератор учебных фикстур не является скрытым оцениванием, а наличие отдельных папок `public/` и `private/` не является изоляцией.

## Экспериментальный контейнерный протокол

`run_isolated_agent(public, truth, agent_path, timeout=...)` запускает только переданный файл агента в Docker (образ фиксирован по digest), без сети, с read-only корнем и ресурсными ограничениями. Агент получает JSON-строку `{observation, reward, terminated, truncated, info}` и отвечает одной JSON-строкой action; при closed-mode исследовательские reward=0, сведения оценщика не отправляются. Конечный score возвращается доверенному вызывающему процессу после завершения. Ошибка протокола не считается чистым решением и не получает score; тайм-аут оценивает пустой ответ. Это экспериментальный механизм с зависимостью от доверенного Docker daemon/ядра, не полноценная верификация безопасности.

## Расширение v0.4: модель company и оценка набора

Старые учебные сценарии сохраняют схемы и семантику. Новая модель имеет manifest.schema_version=`0.3-company` и policy.accounting_model=`accrual_company_v1`. Добавлены публичные поля company_id, line_id, rate_id в проводках и явные правила начислений. Полный смысл полей, допустимые финансовые ситуации, affected/evidence и значения сумм описаны в `COMPANY_MODEL.md`. Для company reporting_period affected_ids содержит invoice_id; для старой двухстрочной фикстуры — row_ids. Нельзя смешивать эти варианты без проверки policy/schema.

`build_company(seed, config)` возвращает public, truth, provenance. Перед внедрениями проверяется чистая история; после — соответствие truth отдельно выведенным публичным фактам. `generate_episode(seed, {"scenario":"company", ...})` по-прежнему возвращает только public/truth; для сохранения истории нужен build_company. `export_episode` требует соответствующий seed и company provenance до создания каталога. История внедрений, seed и config записываются только в private/provenance.json. Загрузчик public восстанавливает null в nullable ledger line_id/rate_id; новые CSV/JSON файлы повторно загружаются без изменения данных.

`company_dataset` создаёт индекс kind=`synthetic_company_development` и 10+10 эпизодов. Это открытый набор разработки. Размер и состав ошибок перемешиваются отдельно; train/dev используют разные seed/IDs. `fixture_evaluation` поддерживает как прежний development_fixtures_not_benchmark, так и этот новый kind. Перед оценкой company проверяется финансовая согласованность/истина; каждый не-oracle результат повторяется через replay. Отчёт содержит общие метрики, train/dev отдельно, mean_reward, mean_inspection_steps и количество совпавших replay. trajectories.jsonl помечается `trajectory_format="ledgergym-actions-v1"`; скрытые seed, truth и provenance в него не записываются.

Сверочный baseline разделяет публичные правила с company_checks, но не получает truth. Его метрики не являются независимой оценкой качества агента. Закрытая граница исполнения не менялась.
