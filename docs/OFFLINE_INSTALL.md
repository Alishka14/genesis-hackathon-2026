# Офлайн-поставка LedgerGym 0.1.0.dev16

Архив содержит wheel LedgerGym, исходный sdist, восемь универсальных wheels тестовых/сборочных зависимостей, тесты, примеры, документы, лицензии и SHA-256. Нужен заранее установленный Python 3.11 с `venv` и `pip`. Интерпретатор и Docker-образ в архив не входят. Целевая проверенная версия — CPython 3.11.11. Поддержка Windows не проверена; colorama включена для полноты зависимостей pytest.

## После LG-030–034: обновлённый набор тестов установленного wheel

В исследовательской ветке к offline gate добавлены source-тесты EQT, FAA, actual 10+10 analysis, v1/v2 CAB, replay и frontend. Новое ожидаемое число тестов необходимо измерить, **не использовать исторические 45/45** как новый результат. Frontend assets должны пройти отдельную installed_dashboard_assets стадию; режим total stages ожидает 10. Подробности: [GATE3_RESEARCH](verification/GATE3_RESEARCH_2026-11-21.md). Данные должны быть с чистой текущей ветки и новый bundle нужен для каждого прогона.

## Актуальная проверка перед конкурсной сдачей (LG-027)

**Текущий статус:** полная локальная интеграция на macOS/Python 3.14 прошла, отдельно подтверждены 22 Docker-теста. **Офлайн-пакет из последней ветки пока не испытан на Python 3.11**. Процедура ниже фиксирует результат в JSON; успешное выполнение нельзя объявлять заранее.

Офлайн-поставка собирается **только CPython 3.11**, хотя основной исследовательский проект допускает Python 3.11 и выше. Сначала проверь:

```sh
python3.11 --version
```

Если на Mac доступен только Python 3.14, установи отдельный Python 3.11 (например, `brew install python@3.11`) и повтори команду.

Из корневого каталога **ветки `agent/release/lg-027-offline-package`**:

```sh
# ЭТА ПОДГОТОВКА ИСПОЛЬЗУЕТ СЕТЬ для загрузки восьми pinned wheels.
# Она выполняется отдельно от последующей офлайн-проверки.
python scripts/prepare_wheelhouse.py "$HOME/ledgergym-wheelhouse-2026"

# Следующий этап не вызывает pip index и не скачивает зависимости.
# Все три пути должны быть доступны; каталог bundle должен быть новым.
python3.11 scripts/verify_offline_release.py \
  --wheelhouse "$HOME/ledgergym-wheelhouse-2026" \
  --bundle "$HOME/ledgergym-offline-final-2026" \
  --report "$HOME/ledgergym-offline-report.json"

cat "$HOME/ledgergym-offline-report.json"
```

Если каталог wheelhouse или bundle уже существует, выбери **новое имя**, не удаляй старый каталог с результатами. Для повторной проверки нового bundle требуется новый путь.

Проверка создаёт отдельные virtualenv для сборки и установленного пакета, использует `pip --no-index --require-hashes`, проверяет точный список файлов и SHA-256 в поставке, запускает набор тестов **из установленного wheel**, локальное демо с повторным воспроизведением и экспорт 10+10. Всё выполняется **вне исходного checkout**. В отчёте `success=true` означает только успешную офлайн-установку и эти тесты: `contest_certified=false`, `docker_isolation_covered=false`, `network_isolation_enforced=false`. Отдельная Docker-проверка на Mac была выполнена ранее и записана в PR №28, а сетевой запрет здесь обеспечен для pip флагом `--no-index`, не механизмами ядра.

После проверки можно упаковать созданный каталог архиватором, но необходимо сохранить без изменений файл `SHA256SUMS.json` и повторно вызвать `verify_bundle.py` в распакованной копии.

Для подробных проверок и ограничений см. [OFFLINE_RELEASE_GATE.md](verification/OFFLINE_RELEASE_GATE.md).

## Установка и запуск

Из распакованного каталога офлайн-поставки (macOS/Linux). Следующие команды относятся к **каталогу готового bundle** и не требуют исходного checkout:

```sh
python3.11 verify_bundle.py
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links wheels --require-hashes --only-binary=:all: -r requirements-runtime.lock
.venv/bin/ledgergym
.venv/bin/ledgergym-company company-run --evaluate
```

`company-run` должен быть новым каталогом. Команда создаёт 10 train + 10 dev, четыре baseline и проверяет 60 переносимых траекторий. В наборе есть `private/truth.json` и `private/provenance.json`: это открытые данные разработки. Каталог целиком не передаётся недоверенному агенту. Baseline reconciliation использует общий публичный checker; его F1 не является независимой benchmark-оценкой.

## Тесты

```sh
.venv/bin/python -m pip install --no-index --find-links wheels --require-hashes --only-binary=:all: -r requirements-dev.lock
.venv/bin/python -m pip check
.venv/bin/python -I -m pytest tests -q -rs
```

Тесты запускаются против установленного пакета вне исходного дерева. `--no-index` запрещает pip обращаться к индексу, `--require-hashes` проверяет архивы зависимостей. `verify_bundle.py` проверяет исходные файлы поставки по манифесту; он не удостоверяет личность автора и допускает появление новых файлов после установки/генерации.

Контейнерные тесты пропускаются, если daemon или закреплённый образ недоступны. Для их выполнения заранее, с сетью, подготовьте Docker и образ:

```sh
docker pull python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5
.venv/bin/python -I -m pytest tests/test_isolated_runner.py -q -rs
```

Runner использует `--pull=never` и `--network none`; оценщик остаётся на хосте. Эти проверки покрывают конкретные попытки доступа к файлу хоста/сети, read-only root, отсутствие Docker socket, тайм-аут, ограничение входа, скрытый feedback и чтение большого эпизода. Они не заменяют независимый аудит безопасности и проверку инфраструктуры жюри.

## Повторная сборка

Исходный архив находится в `source/`. После распаковки sdist можно собрать wheel без сети:

```sh
.venv/bin/python -m pip install --no-index --find-links wheels --require-hashes --only-binary=:all: -r requirements-build.lock
.venv/bin/python -m pip wheel --no-index --no-deps --no-build-isolation --wheel-dir rebuilt source/ledgergym-0.1.0.dev16.tar.gz
```

Для создания аналогичного полного каталога из checkout: сначала установить закреплённые build-зависимости, затем `python scripts/build_offline_bundle.py /путь/к/wheels /новый/каталог`. Скрипт проверяет hashes всех восьми сторонних wheels, собирает wheel/sdist и отказывается перезаписывать существующий каталог. Подготовка wheelhouse из интернета — отдельный предварительный шаг; скачайте все восемь версий из lock-файлов, включая colorama независимо от ОС сборки. Функциональная повторяемость проверяется тестами; побайтовая воспроизводимость архивов не заявляется.

Лицензия собственного кода команды ещё не выбрана. Сторонние лицензии и версии: `THIRD_PARTY_NOTICES.md` и `third_party_licenses/`. Это промежуточная поставка для review, не конкурсная отправка.
