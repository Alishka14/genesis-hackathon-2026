# LG-029 — P0 и локальная веб-панель LedgerGym

**Дата:** 21 ноября 2026. **Статус:** изменения внесены в отдельную ветку; локальные тесты текущей ветки ещё НЕ выполнены. Основание: PR #31 с документацией, PR #30 (офлайн-поставка) и PR #28 (интеграция). Никаких merge в main или конкурсной отправки.

## Реализовано

- **Полный baseline event recorder:** `ledgergym/fixture_evaluation.py` теперь записывает `evaluation/trajectories_full.jsonl`. Каждый шаг содержит `episode_id`, `split`, `policy`, `step`, `action`, `observation`, `reward`, `terminated` и `truncated`. Старый action-only `trajectories.jsonl` сохранён. Новый recorder пользуется детерминированными development-курсорами и проверкой replay; production judge и официальный reward не менялись. **В трассировке есть открытая development-награда, поэтому её нельзя выдавать недоверенному агенту в closed mode.**
- **Dashboard:** `ledgergym/dashboard.py` — локальный HTTP-сервер только на `127.0.0.1` с маршрутами `/api/summary`, `/api/episodes`, `/api/records`, `/api/health`. Читает только агрегированный отчёт и `public/` выбранного эпизода; никакой выдачи `private/truth.json`, `private/provenance.json`, evaluator-only labels. Все query-параметры ограничены allowlist. Это read-only preview, не публичный сервис с аутентификацией.
- **Frontend:** `ledgergym/dashboard_static/` — адаптивная панель со статистикой, графиком четырёх baseline, выбором train/dev и таблиц invoices/payments/ledger/fx, пагинацией и описанием архитектуры. HTML/CSS/JS без npm или CDN; package-data включены в wheel/sdist.
- **Ресурсы:** `scripts/profile_local_resources.py` измеряет wall time, CPU time и peak RSS одной команды на Mac/Linux, пишет агрегированный JSON. Это измерение, не ресурсная изоляция контейнера и не официальное заключение.
- **Тесты:** `tests/test_dashboard_and_full_events.py`, `tests/test_resource_profile.py`; `docs/DESIGN_NOTE.md` с границами модели.

## Запуск на Mac

Исходный репозиторий был клонирован с `--single-branch`. Поэтому используй прямой fetch без `--track`:

~~~bash
cd ~/genesis-hackathon-2026-ledgergym
git status --short
# Если есть незакоммиченные изменения, сначала сохрани их.
git fetch origin refs/heads/agent/p0/lg-029-recorder-dashboard
git switch -c agent/p0/lg-029-recorder-dashboard FETCH_HEAD
python -m pytest -q -rs tests/test_dashboard_and_full_events.py tests/test_resource_profile.py
python3.11 -m ledgergym.dashboard --demo --port 8765
~~~

Открыть в браузере: **http://127.0.0.1:8765**. Для остановки — Ctrl+C. Режим `--demo` генерирует временные 10+10 синтетических эпизодов и удаляет их после остановки.

Для уже готового исследовательского датасета с `evaluation/summary.json`:

~~~bash
python3.11 -m ledgergym.dashboard --dataset /ПУТЬ/К/ДАТАСЕТУ --port 8765
~~~

## Проверка P0 на новой ветке

~~~bash
python -m pytest -q -rs
python scripts/verify_integration.py --mode full --report integration-lg029.json
python -m pytest -q -rs tests/test_isolated_runner.py tests/test_role3_runtime.py
~~~

Три команды являются **рекомендуемыми, но результат на текущей ветке пока НЕ ЗАПУЩЕН**. Родительская ветка ранее локально прошла full integration на Python 3.14, 22 Docker-теста, 45 тестов установленного wheel на Python 3.11.18 и 9 этапов офлайн-поставки. Не переносить эти PASS на новый коммит без проверки.

### Ресурсный отчёт

~~~bash
python3.11 scripts/profile_local_resources.py \
  --report /tmp/ledgergym-resource-lg029.json --timeout 120 -- \
  python3.11 -m ledgergym.company_dataset /tmp/ledgergym-profile-lg029-NEW \
  --evaluate --settlement-hard-negatives
cat /tmp/ledgergym-resource-lg029.json
~~~

При повторе выбери **новые имена** для датасета и отчёта; существующие пути не перезаписываются. Никаких неизвестных лимитов жюри не предполагаем.

## Что остаётся вне этой реализации

1. Человеческая сверка контрактов/финансовых допусков с **первоисточником FinTech кейса**; скрытые проверки организатора не проводились.
2. GitHub Actions — проблема назначения runner (issue #29); код репозитория не даёт автоматического исправления учётных настроек.
3. Лицензия собственного кода, точное раскрытие AI/OSS, review всех stacked PR и разрешение капитана на merge.
4. Видео до 3 минут, презентация, документ со ссылками и фактическая сдача с проверенным доступом жюри.
5. P1: полные EQT/FAA, расширенные anti-shortcut эксперименты и активный UI для управления агентом. Сейчас браузерная часть является **просмотрщиком**, а не полноценным интерфейсом управления RL-агентом.

Дедлайн по `docs/SUBMISSION_CHECKLIST.md`: **22 ноября 2026, 23:59 Астана**. Никакая функция не считается конкурсно сертифицированной до проверки и согласования.
