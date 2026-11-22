# LedgerGym — отчёт об исправлениях по аудиту (22.11.2026)

**Ветка:** `fix/audit-p0`, отправлена на GitHub с разрешения капитана; черновик PR в `main`, без merge.
**База:** `main` `508663205dd095f8b1282cec34034fc3bc38f9e4` (после PR #41/#42).
**Проверенный код:** `daef68d3c1a82a7fb8a7994a2ac97cd7502be3af` (последний коммит кода; последующие коммиты меняют только этот отчёт).
**Окружение:** Linux x86_64, 2 CPU; Python 3.11.18 (генерация, матрица, пробы) и 3.13.18 (pytest 9.1.1); Docker отсутствует; сети для pip нет.
**Источник требований:** официальное ТЗ GENESIS FinTech 2026 (PDF, 6 страниц), предоставленное капитаном.

Это локальная техническая проверка, а не сертификация Genesis и не оценка жюри.

## 0. База и происхождение исправлений

`agent/world/lg-014` слит в PR #14; после merge в неё отдельно добавлен коммит `15c9bc0` (финансовый отчёт). Ранее подготовленный `ledgergym-fixes.patch` (на `lg-014`) по `git apply --check` конфликтует с `main` и с draft PR #40, поэтому каждое его исправление пересмотрено против `main`.

## A. Исправления

| ID | Проблема | Коммит / файлы | Исправление | Проверка | Статус |
|---|---|---|---|---|---|
| BUG-01 | Нет LICENSE | `daef68d`: `LICENSE`, `pyproject.toml`, `MANIFEST.in`, README, checklist | MIT, «LedgerGym contributors» — выбор капитана 22.11 | wheel: `License-Expression: MIT`, `licenses/LICENSE`; sdist содержит `LICENSE` | Исправлено |
| BUG-02 | Падал `test_policy_evidence` | — | Уже исправлено в `main` (`a2be0a2`) | pytest | Не требовалось |
| BUG-03 | Отчёт устарел, скриптов нет | `908dd9e`: `ledgergym/financial_audit_matrix.py`, тест, `docs/FINANCIAL_AUDIT_REPORT.md` | Воспроизводимая матрица с exit code; отчёт перенесён, разделы 1–13 без изменений, раздел 14 датирован; статус Draft | 700 миров / 1500 PASS в обоих режимах; порча данных отклоняется | Исправлено |
| BUG-04 | Док: повторы ID «некорректны» | `52f8481`: `docs/INTERFACES.md` | Текст приведён к контракту (множество) | `test_repeated_ids_are_set_semantics_and_not_malformed` | Исправлено |
| BUG-05 | `role3_mirror` без pytest — traceback | `800c684`: `role3_mirror.py`, тест | `NOT_RUN` + команда установки, exit 2 | 2 теста: FAIL на старом коде, PASS на новом | Исправлено |
| RISK-01 | Шаблонные параметры ошибок | `5d70b32`: `company_world.py`, `company_dataset.py`, тест | Опция `fault_parameters="varied"` (±1–3 дня, 25/50/75 %, дубли KZT/USD) и `timestamp_offsets="mixed"` (5 смещений) | По умолчанию байт-в-байт как `main` (хэши public/truth/provenance); разнообразие на 40 seed; моменты времени не меняются | Исправлено как опция |
| RISK-02 | Один набор доказательств | `5d70b32`: `company_world.py`, `company_checks.py` | Опция `evidence_alternatives=true`: FX без документа счёта, дубль — два документа счёта. Валидатор: каждый набор ⊇ минимального, хотя бы один ⊇ полной цепочки | Судья даёт TP на каждый набор и 0 при удалении любого ID; без опции минимальный набор не принимается | Исправлено как опция (решение капитана) |
| RISK-04 | Единая команда и контейнер | — | Уже есть в `main`: `scripts/verify_p0_release.py`, README строка 64; закреплённый образ `python:3.11.11-slim-bookworm@sha256:0810…` в README и `OFFLINE_INSTALL.md`. Вывод первого аудита «частично» относился к устаревшему README `lg-014` | Чтение `main` | Не требовалось |

Опциональные режимы описаны в `docs/INTERFACES.md`, раздел «Опциональные режимы генератора». Опубликованный датасет не меняется: команда по умолчанию даёт те же 160 файлов эпизодов (SHA-256 совпадают с `main`).

## B. Тестирование

| Проверка | Команда | Passed | Failed | Skipped | Результат |
|---|---|---:|---:|---:|---|
| pytest, база `main` 5086632 | `python3 -m pytest -q -rs -p no:cacheprovider` | 673 | 0 | 14 | PASS |
| pytest, `fix/audit-p0` | то же | 713 | 0 | 14 | PASS |
| Docker (7 isolated runner + 7 role3 runtime) | входит в pytest | — | — | 14 | **NOT_RUN** (нет Docker) |
| Focused P0 gate на `daef68d` (чистый worktree) | `python3 scripts/verify_p0_release.py --mode focused --report …` | 3 этапа | 0 | — | PASS, `technical_pass: true` |
| Full P0 / offline wheel gate Python 3.11 | `--mode full --wheelhouse … --bundle …` | — | — | — | **NOT_RUN** (нет wheelhouse, сети и Docker) |
| Финансовая матрица | `python3.11 -m ledgergym.financial_audit_matrix` | 1500 | 0 | — | PASS, 700 миров |
| Финансовая матрица, новый режим | то же `--varied` | 1500 | 0 | — | PASS, 700 миров |
| Датасет по умолчанию | `python3.11 -m ledgergym.company_dataset DIR --evaluate --settlement-hard-negatives` | replay 60/60 | 0 | — | PASS; 160 файлов идентичны `main` |
| Датасет `--varied` + экспорт + проверка пакета | `company_dataset … --varied`, `export_submission.py`, `verify_submission_package.py` | 125 файлов, 1488 переходов | 0 | — | PASS; названий опций и приватных полей в публичном пакете нет |
| Baseline в режиме `--varied` | `evaluation/summary.json` | oracle и сверка F1=1; mark_all и random F1=0 | — | — | Как ожидалось |
| Wheel / sdist | `pip wheel --no-build-isolation`, `build_meta.build_sdist` | собраны | 0 | — | LICENSE внутри, приватных файлов нет |
| Внешняя проба контракта и атак | `probe_judge.py` (вне репозитория) | 29 | 1 | — | Единственный FAIL (S8) проверяет старое утверждение документации, исправленное в BUG-04 |

## C. GitHub PR и Actions (через REST API; UI не просматривался)

| PR | Branch | Status | CI | Причина | Решение |
|---|---|---|---|---|---|
| #40 | `agent/quality/lg-040-independent-finance-metamorphic` | open, draft, `mergeable_state=dirty` | failure | Конфликт с `main`; CI не стартует | Rebase владельцем PR. `company_world.py` и `_config` меняются и здесь, и в #40 — при rebase объединить списки ключей |
| новый | `fix/audit-p0` | draft | ожидается failure | CI не стартует | Решение по биллингу |
| Issue #29 | — | open | — | Аннотация job: «The job was not started because recent account payments have failed or your spending limit needs to be increased» | Только владелец: Settings → Billing & plans |

## D. Оставшиеся риски

**P0:** CI заблокирован биллингом; Docker-изоляция и full offline gate на текущем SHA не перепроверены (NOT_RUN); дедлайн по README — 22.11, 23:59 (Астана).
**P1:** конфликт с PR #40 в `company_world.py`; опциональные режимы не включены в опубликованный датасет (решение команды); перенесённые отчёт и раздел семантики сумм требуют утверждения автором.
**P2:** `financial_impact.py` не реализован; README содержит исторические разделы старых PR.

## E. Соответствие ТЗ (кратко)

| Раздел ТЗ | Статус | Доказательство |
|---|---|---|
| 02 четыре типа, два compound, чистые и отвлекающие случаи | Выполнено | матрица 700 миров ×2 режима; тесты v1/v2 |
| 02 вариативность сумм, валют, часовых поясов; защита от простых трюков | Выполнено как опция | `fault_parameters`, `timestamp_offsets` (+ EUR/+03/+09 в PR #40) |
| 03 формат эпизода, null, закрытые файлы | Выполнено | экспорт 125 файлов, private truth не экспортирован |
| 04 reset/step, 5 действий, 100 шагов, тайм-аут, курсоры | Выполнено | тесты проекта, внешняя проба |
| 05 matcher 1:1, «хотя бы один полный допустимый набор» | Выполнено | несколько наборов поддержаны и проверены |
| 06/07 четыре политики, траектории без эталона | Выполнено | summary, `verify_submission_package` |
| 07 изоляция агента | Не проверено здесь | Docker NOT_RUN |
| 07/09 контейнер и единая команда | Выполнено в документации | README строка 64, закреплённый образ |
| 09 исходники с лицензией | Выполнено | `LICENSE` (MIT) |

## F. Прогноз по официальной шкале (не результат жюри)

| Критерий | Макс. | Прогноз | Обоснование |
|---|---:|---:|---|
| Контракт и изоляция | 25 | 21 | Контракт подтверждён пробами и тестами; Docker-изоляция здесь не перепроверена |
| Данные и эталон | 25 | 22 | Плюс варьируемые параметры и альтернативные доказательства; режимы опциональны и не включены в опубликованный датасет |
| Надёжность награды | 25 | 23 | Matcher и атаки сильные; несколько наборов доказательств проверены |
| Воспроизводимость | 15 | 13 | Байт-в-байт повтор; финансовая матрица в репозитории |
| Инженерия | 10 | 8 | Лицензия, одна команда, честные ограничения; CI не работает |
| **Итого** | **100** | **≈87** | Предыдущая оценка этого аудита ≈84, экспертная до него — 75 |

## G. Требует решения команды

1. Биллинг GitHub Actions (Issue #29), затем CI на ветке.
2. Full P0 gate с Docker и wheelhouse на итоговом SHA перед подачей.
3. Merge PR `fix/audit-p0` и согласование с PR #40.
4. Включать ли опциональные режимы в опубликованный датасет (сейчас нет).
5. Подтверждение авторства участниками и утверждение перенесённого финансового отчёта.

## Как продолжить

```bash
git fetch origin fix/audit-p0 && git checkout fix/audit-p0
python3 -m pytest -q -rs -p no:cacheprovider
python3.11 -m ledgergym.financial_audit_matrix && python3.11 -m ledgergym.financial_audit_matrix --varied
python3 scripts/verify_p0_release.py --mode focused --report "$HOME/p0-focused.json"
# на машине с Docker и wheelhouse:
python scripts/verify_p0_release.py --mode full --wheelhouse WH --bundle NEW_DIR --report REPORT.json
```
