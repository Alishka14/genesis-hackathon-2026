# LG-038 — P1 FAA: ложные обвинения на уровне валидных платёжных операций

**Дата:** 21.11.2026. **База:** PR #36 / LG-037. **Статус:** отдельная P1-ветка; source pytest и полный P0 на новом SHA пока **NOT_RUN**. Это не подтверждение конкурса.

## Причина изменений

Прежний `ledgergym/research_report.py` обозначал *одну целую компанию* как `STANDARD_VALID` или `SUSPICIOUS_BUT_VALID` только когда все её `truth.issues` пусты. В 16 ошибочных из 20 тестовых компаний программа поэтому не имела знаменателей для проверки ошибочных обвинений против других совершенно корректных платежей. Находимость clean операций внутри faulty company важна для честной исследовательской FAA.

Новый `ledgergym/faa_operation_cases.py` строит **доверенные evaluator-only метки проверенных платёжных операций**, опираясь на опубликованные данные и **после** обязательной проверки генератора/эталона `validate_company` или `validate_settlement_episode`. Метки не попадают в наблюдение агента или открытые траектории.

## Политика меток и ограничений

- `accrual_company_v1`: обычный платёж с однозначной `remittance_invoice_id` и соответствующим полностью записанным `invoice_refs`, при условии что ни сам платёж, ни его счёт не затронуты ни одним `truth.issues[].affected_ids`, получает метку `STANDARD_VALID`.
- `accrual_company_v2`: обычные платежи получают `STANDARD_VALID`, корректно подтверждённый документом split с двумя `allocation_basis`/фактическими `invoice_refs` и законный связанный refund получают `SUSPICIOUS_BUT_VALID`.
- Если хотя бы один идентификатор платежа/счёта входит в какую-либо официальную проблему (любого типа), метка для этой операции **не выдаётся**, даже если отдельный компонент операции выглядит корректным. При неверных или неоднозначных связях никакие догадки не делаются.
- Число наблюдений в `hard_negative_case_fpr` и `standard_valid_case_fpr` теперь означает **количество размеченных и доступных платёжных операций**, а не количество clean companies. Подсчёт общих 2 standard clean / 2 hard-negative clean / 16 faulty companies остаётся исторически совместимым и отдельно приведён в `clean_case_counts`.
- FP относим к конкретной категории лишь когда **полный `affected_ids` обвинения входит в ровно одну валидную операцию** и не пересекается с `truth.issues[].affected_ids`. Для multi-operation совпадений, «подозрительных» смешанных обвинений или произвольных ID применяется `FP_unattributed`. Дубли подтверждённых TP по-прежнему отдельно учитываются как `FP_duplicate`.
- Это **консервативный lower bound** на attribution: не все корректные счета, проводки или законные коррекции платежей получают метки. Нельзя выдавать полученный FPR за независимый измеритель качества обученной модели.

## Реализовано

- `ledgergym/faa_operation_cases.py`: `verified_payment_operations(public, truth)` для модели v1/v2.
- `ledgergym/research_diagnostics.py`: устранена неоднозначная атрибуция FP по одному пересекающемуся ID, исключены известные faulty идентификаторы; суммарные `FP_standard_valid + FP_hard_negative + FP_duplicate + FP_unattributed` должны всегда равняться официальному `FP`.
- `ledgergym/research_report.py`: доверенное агрегирование в отчёте 10 train + 10 dev, с `faa_opportunity_unit`, без раскрытия индивидуальных меток и закрытого truth.
- `tests/test_faa_operation_cases.py`: 7 новых тестов на смешанные v1 эпизоды, настоящие clean/faulty v2 split/refund, неоднозначные обвинения, дубли ID и неизменность награды.
- `tests/test_research_report.py`: дополнительные проверки достаточности операционных знаменателей в общем отчёте.

## Проверка оператором Mac

После окончания работы Codex и сохранения своих изменений:

```bash
cd ~/genesis-hackathon-2026-ledgergym
git status --short
git fetch origin agent/research/lg-038-faa-operation-cases
git switch -c agent/research/lg-038-faa-operation-cases FETCH_HEAD
source .venv/bin/activate
python -m pytest -q -rs tests/test_faa_operation_cases.py tests/test_research_diagnostics.py tests/test_research_report.py tests/test_policy_evidence.py
```

Для отчёта на реальных 10+10 синтетических эпизодах:

```bash
RUN="$HOME/ledgergym-p1-faa-$(date +%Y%m%d-%H%M%S)"
RESEARCH="$HOME/ledgergym-p1-faa-report-$(date +%Y%m%d-%H%M%S)"
python3.11 -m ledgergym.company_dataset "$RUN" --evaluate --settlement-hard-negatives
python3.11 -m ledgergym.research_report "$RUN" "$RESEARCH" --trials 8
python -m json.tool "$RESEARCH/research_summary.json"
```

Каталог `RUN` содержит `private/truth.json`: не загружать его целиком в публичный Drive. Внешнему жюри выдаётся только согласованный публичный пакет, а не метки FAA.

После этих шагов повторить `python scripts/verify_p0_release.py --mode full` с уже проверенным `wheelhouse`, **новыми** именами `--bundle`/`--report` и Docker без пропусков. Технический PASS, полученный ранее на `c488465`, не переносится на новую ветку.

## Следующий P1

LG-033: расширенный anti-shortcut/property-based набор без изменения scorer, включая валюты и timezone только в рамках уже проверенных публичных моделей. Не вводить Hypothesis или стороннюю runtime-зависимость, пока не проверена офлайн совместимость и лицензия.

## Происхождение

Код и план доработки созданы с помощью ChatGPT/GPT-6 и GitHub-коннектора на основе существующего LedgerGym; файлы Diyaz Forge, Ghostproof, CheckList, Hypothesis и иных сторонних проектов не копировались. Подтверждение тестов, review и разрешение на merge остаются за участниками проекта.
