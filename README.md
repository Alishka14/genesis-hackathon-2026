# LedgerGym — синтетическая среда финансового аудита

> **Текущий release-handoff, 22.11.2026:** [финальные ссылки, подтверждённые результаты и оставшиеся шаги](docs/verification/FINAL_SUBMISSION_HANDOFF_2026-11-21.md). До дедлайна 22.11, 23:59 по Астане необходимо загрузить публичный архив, видео, презентацию и обеспечить доступ жюри. Публичный датасет — **только** экспорт `scripts/export_submission.py`; каталог исходных данных с `private/truth.json` нельзя отправлять. Собственная `LICENSE` не утверждена. **Разделы старых PR ниже — исторические:** названия веток и показатели тестов описывают прошлые этапы, а не текущий релиз.

LedgerGym генерирует согласованные синтетические истории, предоставляет ограниченные инструменты расследования и оценивает находки по доказательствам. Модель `company` поддерживает 200–2000 проводок, 20–200 документов и 0–12 ошибок четырёх типов, включая два связанных сценария. Технический P0 подтверждён на чистом `a2be0a26ac000f311b1934f25bb741ec929e2931` (6/6 PASS; Docker 22/22 без пропусков; установленный wheel 172 теста / 193 файла). Итоговый `main` `3b25dc0ac298c809d06bcca289bc15c920d9d469` содержит идентичное Git-дерево. Не считать локальные тесты сертификацией Genesis.

## Проверка релиза и конкурсной поставки (актуально на 22.11.2026)

**Проверяемый релиз = конкретный commit SHA, успешный full P0 на нём, проверенный архив, лицензия и доступ жюри.** Слияние PR само по себе не является тестированием. Статус на 22.11: полный P0 подтверждён на идентичном дереве `a2be0a26`/`3b25dc0`; публичный экспорт проверен: 10+10, 60 траекторий, 1 488 переходов, 125 файлов, без private truth. GitHub остаётся приватным, облачные материалы и подтверждение заявки отсутствуют. См. [текущий handoff](docs/verification/FINAL_SUBMISSION_HANDOFF_2026-11-21.md).

После сборки открытого mixed 10 train + 10 dev набора:

```bash
DATASET="$HOME/ledgergym-dev-$(date +%Y%m%d-%H%M%S)"
PUBLIC="$HOME/ledgergym-public-$(date +%Y%m%d-%H%M%S)"
python3.11 -m ledgergym.company_dataset "$DATASET" --evaluate --settlement-hard-negatives
python scripts/export_submission.py "$DATASET" "$PUBLIC"
python scripts/verify_submission_package.py "$PUBLIC"
```

`DATASET` содержит evaluator-only `private/truth.json` и `private/provenance.json` — **не публиковать**. Передавать жюри только проверенное содержимое `PUBLIC` и документацию, а также четыре политики, исходники, тесты, видео и презентацию. Проверка пакета удостоверяет структуру/хэши, но не независимую правильность бухучёта и не скрытую оценку.

Документ [JURY_95_READINESS](docs/verification/JURY_95_READINESS_2026-11-21.md) отделяет локальные доказательства от вопросов, требующих подписи команды и проверки организаторов. В репозитории пока нет утверждённого собственного файла `LICENSE`; выбор лицензии и подтверждение авторства остаются за правообладателями.

## Исследовательские модули и полный submission trace (в `main`; проверка нового SHA обязательна)

В кодовой базе `main` реализованы: evaluator-only EQT и FAA, 10+10 aggregate research report, scorer invariance/дедуктивный shrinking, CAB causal clean/fault для четырёх v1 типов, CAD перестановка публичных таблиц и биективное переименование всех opaque ID. Полный обязательный формат записывается **отдельно** в evaluation/submission/trajectories.jsonl с trace_index.json; прежний evaluation/trajectories.jsonl оставлен переносимым action-only. В Dashboard необязательный режим --research-report показывает только агрегаты, связанные SHA-256 с выбранным датасетом.

Создание 10+10 и исследования (все каталоги должны быть новыми):

~~~bash
RUN="$HOME/ledgergym-dev-$(date +%Y%m%d%H%M%S)"
RESEARCH="$HOME/ledgergym-research-$(date +%Y%m%d%H%M%S)"
python3.11 -m ledgergym.company_dataset "$RUN" --evaluate --settlement-hard-negatives
python3.11 -m ledgergym.research_report "$RUN" "$RESEARCH"
python3.11 -m ledgergym.cab_company_pairs
python3.11 -m ledgergym.dashboard --dataset "$RUN" --research-report "$RESEARCH/research_summary.json"
~~~

LG-037 EQT и LG-038 FAA включены в локальный установленный wheel и прошли полный P0 на исходном `a2be0a26` (172 установленных теста). На новом draft PR #40, изменяющем финансовую модель, такой проверки ещё нет. Рассматриваем EQT/FAA как доверенные исследовательские постпроцессоры, не как официальный reward или независимый benchmark. Детали и остаток работ: [GATE3_RESEARCH_2026-11-21](docs/verification/GATE3_RESEARCH_2026-11-21.md).

## Локальная веб-панель (в `main`; требуется ручная проверка браузера)

Панель включена в проверенный `main`; оператор отдельно подтвердил открытие экрана, Train/Dev, платежи и Replay. Однако это не независимая сертификация UX. Улучшения объяснений и доказательств из PR #41 требуют нового тестирования перед merge. Финансовое ядро, scorer и официальный reward не менялись ради интерфейса. В панели доступна только локальная открытая выборка; она предназначена для просмотра синтетических данных и агрегированных baseline-результатов, а **не** для выдачи скрытой оценки или обучения модели.

**Быстрый запуск веб-интерфейса (Python 3.11+, без npm, без внешних API):**

```sh
python3.11 -m ledgergym.dashboard --demo
# Открыть в браузере http://127.0.0.1:8765
# Остановить в Terminal через Ctrl+C.
```

Если у тебя уже создан 10+10 dataset с `--evaluate`, можно открыть его без повторной генерации:

```sh
python3.11 -m ledgergym.dashboard --dataset /ПУТЬ/К/ДАТАСЕТУ
```

Dashboard предоставляет обзор эпизодов, F1/reward сравнение четырёх политик, train/dev селектор, постраничный просмотр **только публичных** `invoices`, `payments`, `ledger`, `fx` и интерактивный **Agent Replay** (пошаговый просмотр записанной траектории reconciliation/random/mark-all). В разделе **Audit Findings** отображаются найденные публичным детерминированным checker расхождения с affected IDs и evidence IDs. Этот checker не является обученной автономной моделью и использует правила, связанные с генератором. В Agent Replay не показываются приватные ответы, но используется локальный development-отчёт с итоговой reward; это не инструмент для закрытого агента. Сервер слушает **127.0.0.1**, API чтения ограничен фиксированными маршрутами. Frontend использует HTML/CSS/JS без сторонних библиотек; backend — стандартная библиотека Python. Это не общедоступный сайт и не production-сервер.

**Новый полный event recorder:** после `python3.11 -m ledgergym.company_dataset NEW_DIR --settlement-hard-negatives --evaluate` появляется `NEW_DIR/evaluation/trajectories_full.jsonl` с `episode_id`, `step`, `action`, `observation`, `reward`, `terminated`, `truncated`. Это **доверенный development-артефакт**, содержащий reward; его нельзя выдавать недоверенному агенту в closed mode. Старый переносимый `trajectories.jsonl` с actions сохранён без изменения контракта.

**Единый P0 acceptance gate:** `python scripts/verify_p0_release.py --mode focused --report "$HOME/ledgergym-p0-focused.json"` запускает локальные frontend/recorder/resource tests и проверяет JavaScript. Полный режим с заранее созданным wheelhouse и новым bundle: `python scripts/verify_p0_release.py --mode full --wheelhouse "$HOME/ledgergym-wheelhouse-2026" --bundle "$HOME/ledgergym-offline-p0" --report "$HOME/ledgergym-p0-full.json"`. Полный gate выполняет integration, **строгий** Docker JUnit без SKIP, no-index installed-wheel с frontend ассетами и CPU/RAM. Он выдаёт `success=true` только при всех технических PASS, но всегда оставляет `submission_ready=false` до подписания командой. **Применять только к чистой Git-ветке, отчёты и bundle требуют новых путей.**

**Измерение локальных ресурсов:** `scripts/profile_local_resources.py` записывает wall time, CPU и наблюдаемый пик RSS для отдельной команды на macOS/Linux. Это измерение, **не** принудительное ограничение ресурсов и не подтверждение лимитов платформы жюри.

Подтверждённые локальные результаты на дереве `a2be0a26`, совпадающем с финальным `main` `3b25dc0`: Python 3.14 full P0 PASS (6/6); Docker 22/22 без SKIP; Python 3.11 installed wheel 10/10 стадий, **172 теста**, SHA-256 **193 файла**; 20 эпизодов/60 траекторий/6 пар. PR #40 и PR #41 требуют самостоятельного нового P0. Подробности: [P0 и dashboard handoff](docs/verification/P0_DASHBOARD_2026-11-21.md).

**Матрица соответствия FinTech-кейсу:** [FINTECH_CONTRACT_AUDIT_2026-11-21.md](docs/verification/FINTECH_CONTRACT_AUDIT_2026-11-21.md) сопоставляет реализованный код со спецификацией среды, оценщика и генератора, отмечает допущения и задачи, требующие проверки по оригинальному приложению FinTech. Она не является официальной сертификацией.

**Ниже содержатся разделы предыдущих этапов.** Они описывают состояние кода на момент создания и могут указывать, что split/refund или другие сценарии «ещё не реализованы». Для актуальных v2 сценариев см. [V2_CAUSAL_PAIRS](docs/verification/V2_CAUSAL_PAIRS.md), [OFFLINE_RELEASE_GATE](docs/verification/OFFLINE_RELEASE_GATE.md) и [финальный handoff](docs/verification/FINAL_SUBMISSION_HANDOFF_2026-11-21.md).

## Role 3 canonical judge runtime (21 November 2026)

The organizer entry points are now `judge_adapter.generate_episode(seed, config, output_dir)`, `judge_adapter.make_env()` and `judge_adapter.score_episode(episode_dir, findings, inspection_steps)`. The judge environment accepts `{name,args}`, supports closed/train modes and externally supplied episodes without regenerating them, and provides deterministic canonical pagination and per-step trajectories. Financial generation and scoring remain delegated to the existing owners.

For verification, install test-only dependencies with `python -m pip install -r requirements-role3-test.txt`, then run `python -m pytest -q -rs` and `python -m ledgergym.role3_mirror`. Runtime itself has no third-party Python dependencies. These are local checks; they do not certify financial data generation or unavailable container isolation.

Run `python -m ledgergym.role3_demo local --trajectory trajectories.jsonl` for inspect/document/calculator/submit/replay. With Docker and the exact image documented below already present, run `python -m ledgergym.role3_demo restricted --episode PATH --trajectory trajectories.jsonl` for the actual file-fed closed policy path. Missing Docker/image produces NOT_RUN; there is no insecure subprocess fallback.

Protocol, compatibility and trust boundaries: [docs/INTERFACES.md](docs/INTERFACES.md). Measured results: [Phase 1](docs/ROLE3_PHASE1_VERIFICATION.md), [security](docs/ROLE3_PHASE2_SECURITY.md), [final verification](docs/ROLE3_FINAL_VERIFICATION.md). Generator/matcher/provenance limitations remain material; this change does not declare the entire project competition-ready.

**Ограничение безопасности:** обычная среда и callback оценщика выполняются в одном процессе и не изолируют недоверенного агента. Экспериментальный `isolated_runner` запускает агент в ограниченном Docker-контейнере, но ещё требует независимого аудита и проверки на инфраструктуре жюри; его нельзя считать доказанной защитой для закрытой конкурсной оценки. См. `docs/STATUS.md`.

## Продолжение по мастер-плану v2

Добавлен внутренний `payment_matching`: полные/частичные оплаты, несколько платежей на invoice, split payment, сохранение свободного остатка и явная неоднозначность. Он проверяет контрагента/дату/валюту, не угадывает ссылку по сумме и не выбирает между одновременно конкурирующими платежами по ID. Проверка подключена к чистой company-истории перед fault injection; публичные данные и reward сохранены. [Спецификация matching](docs/MATCHING_SPEC.md), [каталог сценариев](docs/SCENARIO_CATALOG.md), [статус плана v2](docs/MASTER_PLAN_V2_STATUS.md).

Генератор пока не создаёт split/overpayment hard negatives; refunds и cross-currency allocation новым модулем не поддерживаются. Это отдельный следующий этап финансовой модели. Полный набор: **244 PASS**, новый matching: **43 PASS**, включая матрицу 100 seed. Отчёт: [первый этап плана v2](docs/PLAN2_PAYMENT_MATCHING_REPORT.md).

## Офлайн-прогон компании

Нужен Python; runtime использует только стандартную библиотеку. Команда создаёт **новый** каталог, 10 train + 10 dev эпизодов, прогоняет четыре доверенные baseline-политики и проверяет повтор всех 60 не-oracle траекторий:

```sh
python -m ledgergym.company_dataset ./ledgergym-company-run --evaluate
```

Результаты: `index.json`, каталоги train/dev с `public/` и `private/`, `evaluation/summary.json` и `evaluation/trajectories.jsonl`. Существующий каталог не перезаписывается. Это открытый набор для разработки с эталонами и предсказуемым seed, не закрытый тест. Агенту предоставляются только публичные данные через инструменты среды.

Сверочная политика использует тот же публичный проверяющий модуль, который контролирует генератор. Её F1=1 показывает согласованность реализации с заданными правилами, а не независимую способность обобщать. Oracle имеет доступ к эталону только в доверенном оценщике и не экспортирует траектории.

Модель, семантика сумм и ограничения: [COMPANY_MODEL](docs/COMPANY_MODEL.md). Фактические результаты: [отчёт lg-014](docs/LG014_REPORT.md).

## Проверка

Один локальный учебный пример без сети запускается командой `python -m ledgergym`. Это проверка связки, а не benchmark. Для запуска тестов нужен Python и pytest. В окружении, где pytest уже установлен:

```sh
python -m pytest -q
```

Среда исполнения использует только стандартную библиотеку Python. В lg-015 проверена CPython 3.11.11, добавлены wheel/sdist и фиксированные зависимости с SHA-256. Инструкция установки из локальных wheels: [OFFLINE_INSTALL](docs/OFFLINE_INSTALL.md). Сборка полного каталога: `python scripts/build_offline_bundle.py <wheelhouse> <новый-каталог>`; предварительно установить `requirements-build.lock`. Реестр сторонних компонентов и копии лицензий: [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md).

Фактическая проверка установленного пакета: **201 PASS**, включая семь Docker-тестов; Linux arm64 без сети: **194 PASS / 7 Docker SKIP** (вложенный daemon не предоставляется), генерация 10+10 и 60/60 replay. Детали и ограничения: [отчёт lg-015](docs/LG015_REPORT.md).

## Текущая реализация и ограничения

- `ledgergym/company_world.py`, `company_checks.py`: согласованная модель начислений, управляемые ошибки, закрытый журнал изменений и проверка по публичным фактам с рациональной арифметикой, независимой от Decimal генератора.
- `ledgergym/company_dataset.py`: воспроизводимые 10 train + 10 dev эпизодов размера из мастер-спецификации и опциональный офлайн-прогон.
- `ledgergym/world.py`, `payment_world.py`, `fx_world.py`, `period_world.py`: небольшие самостоятельные генераторы четырёх типов ошибок и корректных контролей с предварительными финансовыми проверками. Это не полный конкурсный генератор.
- `ledgergym/episode_io.py`: сохранение шести публичных файлов и отдельных truth/provenance с воспроизводимым содержимым; разделение каталогов не защищает данные от недоверенного процесса.
- `ledgergym/generator.py` и `ledgergym/compound_world.py`: единый конфиг для четырёх типов и двух небольших связанных примеров с независимыми переключателями дефектов.
- `ledgergym/fixture_dataset.py`: воспроизводимое создание 10 train и 10 dev **учебных фикстур**, а не конкурсного benchmark.
- `ledgergym/env.py`, `runtime.py`: генерация эпизода через reset(seed, config), пять действий и локальные ограничения бюджета, без безопасной изоляции процессов.
- `ledgergym/replay.py`: повтор переносимых траекторий с получением новых курсоров из ответов среды.
- `ledgergym/score.py`: максимальное evidence-aware сопоставление 1:1, метрики, награда и проверка структуры submit.
- `docs/INTERFACES.md`: **неутверждённые** интерфейсные решения и нерешённые вопросы.
- `docs/STATUS.md`: оставшаяся работа и ограничения.

Модель ограничена начислениями по услугам и платежами в тот же день, KZT/USD и фиксированным смещением +05:00. Она не охватывает налоги, возвраты и курсовые разницы между датой начисления и датой оплаты. Независимый человеческий финансовый/security review, проверка окружения жюри, выбор лицензии собственного кода и конкурсные материалы ещё не завершены. Официальные PDF не были доступны; дополнительные поля и семантика сумм требуют сверки. Формула reward не менялась.

## Происхождение и ИИ

Код и документы текущего среза созданы при помощи OpenAI Codex по заданию капитана на основании приложенных мастер-спецификации и стартового промпта. Runtime-код использует стандартную библиотеку Python; для тестов применялся pytest. В текущем срезе сторонний код не копировался. Перед конкурсной сдачей команда должна независимо проверить вклад, условия лицензий и заполнить `docs/PROVENANCE_AND_AI_DISCLOSURE.md` по фактическому результату.

Создание/слияние и подача регулируются проектными правилами; merge, изменение доступа и отправка требуют явного подтверждения капитана.

## Учебные фикстуры

Команда создаёт новый каталог и никогда не перезаписывает существующий:

```sh
python -m ledgergym.fixture_dataset /tmp/ledgergym-fixtures-example
```

Она создаёт 10 train и 10 dev **маленьких учебных фикстур** для разработки и проверок API. Объём и разнообразие не соответствуют заявленному конкурсу; предсказуемые seed не годятся для закрытой оценки. Каждый эпизод содержит `public/` и `private/`, но разделение папок само по себе не защищает закрытые данные.

## Локальные baseline на учебных фикстурах

После создания учебного набора можно выполнить:

```sh
python -m ledgergym.fixture_evaluation /tmp/ledgergym-fixtures-example /tmp/ledgergym-fixture-results
```

Создаются `summary.json` и `trajectories.jsonl` с действиями случайной, сверочной и атакующей политик. Oracle использует скрытый эталон только внутри доверенного оценщика и в trajectories не записывается. Этот запуск предназначен для отладки на маленьких заранее известных примерах; он не является оценкой способности обобщать и не запускает недоверенный код безопасно.

## Экспериментальный запуск агента в Docker

Нужны локальный Docker и заранее загруженный точный образ. Загрузка выполняется один раз с сетью; сам runner использует `--pull=never` и не скачивает образ при оценивании:

```sh
docker pull python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5
python - <<'PYCODE'
from ledgergym.world import make_episode
from ledgergym.episode_io import export_episode
public, truth = make_episode(42, True)
export_episode('/tmp/ledgergym-isolated-demo', public, truth, seed=42)
PYCODE
python -m ledgergym.isolated_runner /tmp/ledgergym-isolated-demo examples/duplicate_agent.py --timeout 15
```

Каталог примера должен ещё не существовать. В контейнер монтируется только скрипт агента; обмен выполняется JSON-строками через stdin/stdout, оценщик остаётся на хосте. Настройки включают `--network none`, read-only root, непривилегированного пользователя, удаление capabilities, лимиты ресурсов и проверку удаления контейнера. Доверенная граница включает Docker daemon и ядро хоста. Этот механизм экспериментальный, не проходит автоматически в окружениях без Docker или нужного образа и требует независимого security review. Python-агенту доступны библиотеки стандартного образа, дополнительные зависимости и файлы не монтируются.

## Генерация и повтор локального эпизода

```python
from ledgergym.env import LedgerSandbox

env = LedgerSandbox()
observation, info = env.reset(seed=42, config={"scenario": "duplicate_invoice", "fault": True})
page, reward, terminated, truncated, info = env.step({"action": "list_records", "table": "invoices"})
```

Для сохранённых действий baseline: `replay_actions(env, actions, seed=42, config=config)` из `ledgergym.replay`. Используйте тот же seed/config, что и при построении исходного эпизода. Ссылки вида `cursor={"from_step":N}` разрешает адаптер replay; непосредственный step принимает только строковый курсор текущего reset. Seed/config не сохраняются в агентской траектории. Режим `LedgerSandbox(public, evaluator)` для загруженного эпизода допускает только `reset()` без параметров генерации. Полный контракт и миграция: `docs/INTERFACES.md`, версия 0.4.

Для новой модели в reset передайте, например:

```python
observation, info = env.reset(seed=42, config={
    "scenario": "company", "postings": 800, "documents": 100,
    "faults": {"reporting_period": 1},
    "compounds": {"fx_allocation": 1, "duplicate_allocation": 1},
})
```

Для экспорта с закрытой историей внедрений используйте `build_company(seed, config)` из `ledgergym.company_world` (config без scenario): он возвращает public, truth, provenance. Передайте provenance в `export_episode(..., seed=seed, provenance=provenance)`. Генерация через обычный `generate_episode` сохраняет прежний API из двух результатов.
