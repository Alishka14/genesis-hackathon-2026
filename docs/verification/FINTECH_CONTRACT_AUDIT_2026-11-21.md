# FinTech технический контракт: матрица соответствия LedgerGym (21.11.2026)

**Уровень достоверности:** аудит существующего кода и внутренних документов репозитория, **не официальная приёмка кейса**. Исходный отдельный PDF/публикация с техническими критериями FinTech в доступных исходниках не подтверждены; перед сдачей капитан и владелец финансового блока должны сравнить параметры **с первоисточником**. Статусы далее не означают PASS новых тестов PR #32. Общий организационный регламент подтверждён отдельно в `docs/COMPETITION_RULES.md`.

## Контракт и кодовая опора

| Раздел | Где реализовано | Обозначение статуса | Что перепроверить |
| --- | --- | --- | --- |
| Точки входа жюри | `judge_adapter.py`: `generate_episode`, `make_env`, `score_episode` | IMPLEMENTED; role3 parent tests available | Сигнатуры и формат ответа в оригинальном кейсе |
| Canonical reset/step | `ledgergym/canonical.py`, `docs/INTERFACES.md` | IMPLEMENTED; локальные role3 проверки ранее были PASS | Режим closed, ошибочный reset и лимит 100 действий |
| Пять разрешённых инструментов | `ledgergym/canonical.py`, `ledgergym/env.py` | IMPLEMENTED | Формат `{name,args}` в официальном API; не путать с legacy `{action:...}` |
| Публичные файлы | `ledgergym/episode_io.py` | IMPLEMENTED | Валюты, обязательные поля, временные зоны и схему CSV/JSONL |
| Приватный финансовый эталон | `ledgergym/episode_io.py`, `ledgergym/isolated_runner.py` | IMPLEMENTED | Проверить, что `truth.json` и `provenance.json` не попадают в container, Git, видеозапись |
| Четыре семейства ошибок v1 | `ledgergym/company_world.py`, `ledgergym/company_checks.py` | IMPLEMENTED; локальный internal synthetic benchmark PASS | Контрольные кейсы и определение суммы исправления |
| Два compound-сценария | `ledgergym/company_world.py` и соответствующие тесты | IMPLEMENTED | Независимость доказательств, отсутствие двойного учёта |
| Законные split/refund и v2 fault controls | `ledgergym/company_world_v2.py`, `ledgergym/settlement_faults_v2.py` | IMPLEMENTED; restricted scope | v2 сейчас не покрывает все четыре семейства; не заявлять полное v2 покрытие |
| Evidence-aware one-to-one matcher | `ledgergym/score.py` | IMPLEMENTED | Финальная сверка допустимых evidence sets, сравнений сумм и элементов списка |
| F1 и награда | `ledgergym/score.py`: `reward = clip(2*F1 - 1 - 0.002*inspection_steps,-1,1)` | IMPLEMENTED | Организаторский допуск по деньгам, учёт неверных шагов |
| Четыре baseline | `ledgergym/baselines.py`, `ledgergym/fixture_evaluation.py` | IMPLEMENTED | Oracle имеет доступ к private truth и является *верхней границей*, не агентом |
| Датасет 10 train + 10 dev | `ledgergym/company_dataset.py` | IMPLEMENTED; участник запустил 20 эпизодов | Переключение `--settlement-hard-negatives` меняет версионированный набор, сохранить профиль в отчёте |
| Повторение 60 траекторий | `ledgergym/replay.py`, `ledgergym/fixture_evaluation.py` | IMPLEMENTED; 60/60 на прежнем коде | Новый полный event recorder и replay UI проверить на PR #32 |
| Изоляция Docker | `ledgergym/isolated_runner.py` | IMPLEMENTED; ранее 22/22 real Docker PASS | Проверить текущую ветку с 0 SKIP, обеспечить локальный pinned Docker image |
| Офлайн-поставка | `scripts/verify_offline_release.py` | Ранее 9/9 PASS на PR #30 | Новый 10-stage gate: проверить все frontend assets внутри wheel |
| Локальный audit dashboard | `ledgergym/dashboard.py`, `dashboard_static/` | NEW / NEEDS OPERATOR TEST | Только loopback/чтение public; Audit Findings = deterministic checker, не обученный агент |
| Полный P0 aggregator | `scripts/verify_p0_release.py` | NEW / NEEDS OPERATOR TEST | Флаг `submission_ready=false` сохраняется при техническом PASS |
| Источники/лицензии/ИИ | `THIRD_PARTY_NOTICES.md`, `docs/PROVENANCE_AND_AI_DISCLOSURE.md` | PARTIAL | Выбор лицензии собственного кода, состав команды, вклад и капитан |

## Несоответствия и открытые решения

1. **Оригинальный кейс.** Внутренний `docs/INTERFACES.md` прямо обозначает допуск суммы 0 и правило о дополнительных evidence IDs как предварительные проектные решения. Нельзя без первоисточника утверждать, что они официальны.
2. **Поддерживаемые деньги.** Поддержка рассчитана на проектную KZT/USD модель, часовую зону +05:00, ROUND_HALF_EVEN и преимущественно начисления/платежи; независимый аудит реальной бухгалтерии не выполнялся.
3. **Область задач v2.** Принимаются clean split/refund и отдельные duplicate/allocation faults. Нет полного набора v1 fault families под v2.
4. **AI-природа продукта.** LedgerGym — синтетическая среда и оценщик, а Reconciliation — детерминированная policy, не обученная модель. В презентации не обещать автономный AI-сервис, которого нет в исходниках.
5. **Ресурсный профиль.** Docker container имеет настроенные `--memory 256m`, `--cpus 0.5`, `--pids-limit 32` и отключённую сеть; локальный resource profiler фиксирует только измерение. Соответствие **официальному** runner budget требует явного подтверждения.
6. **GitHub Actions.** Новейшие workflows завершаются до первого шага с `runner_id=0` (issue #29). На текущем HEAD не подтверждены CI-тесты. Нельзя подписывать P0 до отдельной проверки.
7. **Release approval.** Капитан утверждает объединение веток, public/private доступ жюри, членство и вклад, собственную лицензию, 3-минутное видео, презентацию, Google Drive документ и официальную отправку.

## Рекомендуемый acceptance workflow

~~~bash
# Активный Python с pytest, Node v22+ и установленный Python 3.11.
python scripts/verify_p0_release.py --mode focused \
  --report "$HOME/ledgergym-p0-focused-NEW.json"

python scripts/verify_p0_release.py --mode full \
  --wheelhouse "$HOME/ledgergym-wheelhouse-2026" \
  --bundle "$HOME/ledgergym-p0-offline-NEW" \
  --report "$HOME/ledgergym-p0-full-NEW.json"
~~~

Для повторного прогона укажи новые выходные пути. Полный технический PASS не означает `contest_certified=true`; ручные решения капитана по авторству/сдаче и независимые тесты жюри не входят в этот script.

**Решение по каждой строке должен отметить ответственный человек после просмотра актуальных исходников и оригинального PDF FinTech-кейса.** Не переносить прежние PASS автоматически на PR #32.
