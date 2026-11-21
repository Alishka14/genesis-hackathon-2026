# Офлайн-поставка LedgerGym 0.1.0.dev16

Архив содержит wheel LedgerGym, исходный sdist, восемь универсальных wheels тестовых/сборочных зависимостей, тесты, примеры, документы, лицензии и SHA-256. Нужен заранее установленный Python 3.11 с `venv` и `pip`. Интерпретатор и Docker-образ в архив не входят. Целевая проверенная версия — CPython 3.11.11. Поддержка Windows не проверена; colorama включена для полноты зависимостей pytest.

## Установка и запуск

Из распакованного каталога архива (macOS/Linux):

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
