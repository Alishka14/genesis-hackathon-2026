# P0 owner review — matcher и независимый финансовый аудит (21.11.2026)

**Статус:** REVIEW / рабочая ветка `agent/evaluation/lg-020-matcher`. Не сливать в `main` без утверждения. Затрагивает официальные критерии scorer/data. Исходный верификатор: `docs/verification/p0-matcher-probe.py` из интеграционной ветки.

## 1. Matcher: точечные исправления

| Известный контрпример | Предыдущее состояние | Исправленный контракт / требуемый тест |
| --- | --- | --- |
| repeated affected IDs | invalid submit (-1 с null metrics) | canonical set-equivalence; TP при остальных правильных полях |
| repeated evidence IDs | invalid submit | повторные IDs не нарушают семантику, сырой лимит 10 IDs остаётся |
| unknown string issue type | invalid submit | well-formed finding, semantic FP |
| lowercase 3-letter currency | invalid submit | well-formed finding, semantic FP, без автоматической нормализации в KZT |
| arbitrary public entity_id in evidence | native считал доступным, canonical отвергал | оба допускают **только addressable IDs** get_record/get_document |
| M11 ambiguous maximum matching | перевёрнутое назначение A→1/B→0 | cardinality=2 и стабильный lexicographic tie-break A→0/B→1 |

Изменённые файлы: `ledgergym/score.py`, `ledgergym/canonical.py`, `ledgergym/runtime.py`. Официальная формула reward не менялась. Проверки `tests/test_matcher_p0_regression.py`.

## 2. Независимая финансовая сверка

`ledgergym/independent_audit.py` — отдельная реализация вычислений по **публичным записям**, без импортов из `company_world`, `company_checks`, baseline или private `truth`. Валютная конвертация — точные рациональные `fractions.Fraction`, вместо `Decimal` генератора.

Проверяет:
- баланс бухгалтерского регистра, типы/знаки денежных сумм и источники;
- равенство суммы позиций и суммы invoice, бухгалтерские проводки по invoice;
- корректность FX-rate date, вычисленного KZT amount и rounding;
- наличие дублированного экономического обязательства через документальную service identity;
- расчёт суммы нераспределённой оплаты и справедливость её ссылки;
- отнесение invoice к отчётному месяцу;
- доступные evidence ID и сравнение выведенных публичных сигнатур с закрытым truth **только после** самостоятельного расчёта.

Тесты `tests/test_independent_financial_audit.py` покрывают чистый случай, каждую из четырёх ошибок, оба compound-варианта, несколько seed, изменение баланса, перестановки и конфигурацию 2000 ledger/200 documents/12 issues.

**Ограничения:** в текущем синтетическом `accrual_company_v1` не охвачены реальные стандарты аудита, бухгалтерская законность возвратов, полный межвалютный платёжный matching и официальные P01–P20 финансовые пары. Независимость реализации не заменяет независимое экспертное ревью. Проверяющий алгоритм отвергает неподдерживаемые данные.

## 3. Тестирование и точные утверждения

- Локальный изолированный тест исправленного scorer: **9/9 PASS**. Это не весь репозиторий.
- Первая CI-итерация GitHub Actions (`44896938974`): **330 PASS, 1 FAIL**. Сбой в подготовке нового тестового случая: изменение случайной проводки иногда нарушало однонаправленность debit/credit до проверки общего баланса; **не ошибка математической модели**. Исправлено в `tests/test_independent_financial_audit.py` с выбором исходно дебетовой строки.
- Повторная CI-итерация для текущего PR должна подтвердить полный результат. Нельзя заявлять PASS до окончания Actions.
- Ручной аудит official organizer-host, все D01–D20 и release gate: **NOT_RUN**.

## 4. Перед слиянием

- [ ] Полный CI на Python 3.11 и 3.12: PASS, без скрытых пропусков Docker.
- [ ] `python docs/verification/p0-matcher-probe.py`: все девять контрольных примеров PASS.
- [ ] Проверить native/canonical score parity, целевую схему `findings` и reward.
- [ ] Независимое review финансовых исходных операций и evidentiary chains.
- [ ] Отдельно проверить корректные split payments/refunds, FX/timezone и compound causal delta.
- [ ] Не смешивать аудит со статистикой успешности RL-политики; oracle с известным truth не доказывает качество агента.
- [ ] Получить разрешение владельца на merge и конкурсную отправку.

**Команды для воспроизведения в целевом checkout:**

    python -m pytest -q -rs -p no:cacheprovider
    python docs/verification/p0-matcher-probe.py
    python -m pytest tests/test_matcher_p0_regression.py tests/test_independent_financial_audit.py -q

