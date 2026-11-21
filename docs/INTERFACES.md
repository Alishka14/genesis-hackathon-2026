# LedgerGym — единый контракт модулей (Gate 0)

**Статус:** PROPOSED / NOT IMPLEMENTED. **Источник:** официальный GENESIS FinTech-кейс 2026 (6 стр.) и утверждённые концептуальные документы LedgerGym. **Расположение:** только документация в плановой ветке. Любое изменение схемы требует одобрения Tech Lead.

## 1. Назначение и границы
LedgerGym — воспроизводимая офлайн RL-совместимая среда: генератор строит синтетическую компанию → controlled fault injection → публичный episode loader → read-only sandbox агента → доверенный scorer. Сама среда не обучает модель. P0: официальный контракт/четыре ошибки/два compound/clean, scoring, baselines, replay. CAB/EQT/FAA только evaluator-side diagnostics.

### Потоки
- Generator принимает seed/config/schema_version и создаёт **публичное** состояние: manifest.json, ledger.csv, invoices.jsonl, payments.jsonl, fx.csv, policy.json.
- Generator создаёт **скрытые** truth.json, provenance.json и при необходимости метки correct/hard negative; эти данные не выдаются в agent observation/info/tools/errors/logs.
- Sandbox выдаёт только запрошенную публичную информацию через пять разрешённых read-only действий, поддерживая бюджет шагов.
- Evaluator получает final findings, закрытый truth и число исследовательских шагов; вычисляет 1:1 matching и официальный reward. Скрытая диагностика остаётся evaluator-side.
- Никогда не передавать файловые пути к private материалам и ссылки на них в агентский runtime. Отдельная граница доверия обязательна; разделение Python-переменных в одном незащищённом процессе не равно изоляции.

## 2. Файлы и минимальные поля [OFFICIAL]
- **manifest.json:** schema_version, episode_id, base_currency, period_start, period_end, timezone, counts, rounding_policy. Поля counts/rounding_policy детализируются перед реализацией.
- **ledger.csv:** row_id, timestamp, account, debit_minor, credit_minor, currency, entity_id, invoice_id, payment_id.
- **invoices.jsonl:** doc_id, invoice_id, entity_id, issued_at, due_at, currency, total_minor, line_items.
- **payments.jsonl:** doc_id, payment_id, timestamp, currency, amount_minor, invoice_refs.
- **fx.csv:** date, source_currency, target_currency, rate.
- **policy.json:** FX-rate date selection, reporting cutoff, rounding rules. Точная вложенная JSON-схема — OPEN.
- **truth.json:** issue_id, type, affected_ids, expected_amount_minor, currency, допустимые наборы evidence.
- **provenance.json:** история генерации, fault injection, причинные изменения, private metadata.

Форматы: даты/время ISO-8601 с timezone offset; деньги — integer minor units (разрядность currency обязательна); FX rate — decimal string; missing references — explicit null, не угадывать связи. Разные валюты нельзя сравнивать без конвертации по policy. Отрицательные суммы и возвраты — только по определённым правилам модели.

## 3. Конкретизация схемы внутри LedgerGym [PROPOSED]
Это предлагаемые поля **внутреннего** проекта. Не считать их официально закреплёнными до Gate 0.

Примеры внутренних типов (в Python dataclass/Pydantic по решению команды):
- Invoice = {invoice_id, doc_id, entity_id, currency, total_minor, issued_at, due_at, line_items}
- Payment = {payment_id, doc_id, entity_id, currency, amount_minor, timestamp, invoice_refs}
- Allocation = {payment_id, invoice_id, applied_minor, currency, basis_reference}
- LedgerEntry = {row_id, timestamp, account, debit_minor, credit_minor, currency, entity_id, invoice_id?, payment_id?}
- Fault = {issue_id, type, affected_ids[], expected_amount_minor, currency, allowed_evidence_sets[][]}
- Episode = {public_data_ref, private_evaluator_ref, schema_version}; runtime не должен отдавать private_evaluator_ref агенту.

Предлагаемое внутреннее поле truth **allowed_evidence_sets** = список непустых наборов публичных ID. Соотнести это имя с фактическими правилами кейса до реализации.

**Пример** (сокращённая схема; не использовать как скрытый эталон в публичном пакете):

    {"issue_id":"issue-1","type":"duplicate_invoice","affected_ids":["inv-1","inv-2"],
     "expected_amount_minor":125000,"currency":"KZT",
     "allowed_evidence_sets":[["doc-inv-1","doc-inv-2","row-9"]]}

Конкретные значения type, представление money mismatch, валюта expected_amount и канонизация affected IDs — OPEN. Нельзя незаметно определить разные правила в генераторе и matcher.

## 4. Интерфейс среды [OFFICIAL]
- reset(seed,config) -> (observation,info): агенту даётся задача, manifest, краткая policy, remaining_steps. Состояние и счетчики старого эпизода обнуляются.
- step(action) -> (observation,reward,terminated,truncated,info).
- Действия: list_records(table,cursor,limit<=50), get_record(table,id), get_document(doc_id), calculator(expression), submit(findings).
- Вход/выход JSON-совместим; свободного shell, SQL, сети, FS нет.
- Unknown action/ID возвращает ограниченную ошибку и расходует шаг.
- Максимум 100 шагов включая submit; submit -> terminated=true; исчерпание бюджета/времени -> truncated=true, пустой итоговый ответ; промежуточная награда 0.
- В открытом training terminal reward может быть виден; в закрытом run scorer держит reward/diagnostics у себя до завершения.
- Calculator: ограниченная арифметика над Decimal, AST whitelist, запрет eval/exec/import/functions/files.

Рекомендуемые поля action [PROPOSED]: {type:"list_records",table:"ledger",cursor:null,limit:20} и {type:"submit",findings:[...]}. Поле type (или name/action) — OPEN, утвердить одно значение на уровне всего проекта.

## 5. Submit / outcome [OFFICIAL]
    {"episode_id":"ep-001","findings":[{"type":"duplicate_invoice",
     "affected_ids":["inv-1","inv-2"],"claimed_amount_minor":125000,
     "currency":"KZT","evidence_ids":["doc-1","doc-2","row-9"],
     "explanation":"Two postings reflect one obligation."}]}

Ограничения: findings <=30; evidence IDs <=10 на finding; explanation <=1000 символов. Точная валидация формы, поддерживаемые error types и id normalization должны быть утверждены до кода.

Официальный matcher: TP только при совпадении type, canonical affected_ids, currency, claimed_amount_minor в опубликованном допуске и хотя бы одного полного допустимого evidence set. One-to-one matching; неверные и повторные находки — FP; пропуски — FN.

P=TP/(TP+FP), R=TP/(TP+FN), F1=2TP/(2TP+FP+FN). Empty truth+empty findings => F1=1; empty truth+nonempty findings => F1=0. Неверная submit schema -> reward -1. Terminating reward = clip(2*F1 - 1 - 0.002*inspection_steps, -1,1). Диагностика CAB/EQT/FAA не меняет P/R/F1/reward.

## 6. Контракт повторяемости и границ
- Same seed + config + schema_version + identical actions => same public records, transitions, terminal score.
- Перемешивание порядка records и полная биективная замена IDs с обновлением всех ссылок не меняет семантического результата и reward oracle.
- IDs нейтральны: не включают -COPY/-BAD/-FIXED и другие подсказки.
- Любой truth issue имеет минимум один доступный агенту допустимый evidence set; отсутствие доказательства => эпизод отклоняется на preflight.

## 7. Gate 0: открытые решения (перед имплементацией)
- [ ] Команда/капитан/личная область работы оформлены в docs/SCOPE.md; зафиксировано разрешение на написание конкурсного кода.
- [ ] Конкретные строки четырёх issue types и их mapping на truth.
- [ ] Entity ID semantics: invoice_id/payment_id/doc_id/row_id; правила canonical affected_ids; строгое требование entity match.
- [ ] Public evidence IDs и допустимые allowed_evidence_sets; трактовка extras сверх полного evidence set.
- [ ] Допуск amount_minor/FX и поведение rounding; кто владеет conversion.
- [ ] Public policy.json schema: date selection, cutoff, currency scale и amendments/refunds.
- [ ] Формат action name, tool error, cursor, observed budget, timeout.
- [ ] Порядок лимита на последнем шаге (submit на шаге №100 должен обрабатываться по заранее принятому правилу).
- [ ] Детерминированное максимальное 1:1 matching при неоднозначности; tie-break.
- [ ] Размещение private evaluator по границе процессов для реального no-leak теста.

**Тест дизайна до программирования:** вручную выписать одну чистую операцию, один duplicate, одну payment-allocation ошибку и один complete evidence set; проверить соответствие схемам выше.

**Референсы:** официальный кейс GENESIS FinTech; docs/DIAGNOSTIC_EXTENSIONS.md; docs/DIAGNOSTIC_TEST_MATRIX.md. **Статус тестов:** NOT_RUN.
