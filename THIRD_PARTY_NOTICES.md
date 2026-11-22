# Сторонние компоненты

LedgerGym runtime использует стандартную библиотеку Python; сторонние runtime-зависимости отсутствуют. Указанные ниже пакеты применяются для тестирования и сборки. В офлайн-поставке их wheel-файлы сохраняются без изменения, SHA-256 зафиксированы в `requirements-dev.lock` и `requirements-build.lock`. Тексты лицензий и доступные в wheel уведомления скопированы в `third_party_licenses/<package-version>/` с сохранением исходных путей.

| Компонент и источник | Версия | Лицензия верхнего уровня | Применение |
| --- | --- | --- | --- |
| [pytest](https://pypi.org/project/pytest/8.4.2/) | 8.4.2 | MIT | Тестовый runner |
| [iniconfig](https://pypi.org/project/iniconfig/2.3.1/) | 2.3.1 | MIT | Зависимость pytest |
| [packaging](https://pypi.org/project/packaging/26.3/) | 26.3 | Apache-2.0 OR BSD-2-Clause | Зависимость pytest |
| [pluggy](https://pypi.org/project/pluggy/1.7.0/) | 1.7.0 | MIT | Зависимость pytest |
| [Pygments](https://pypi.org/project/Pygments/2.21.0/) | 2.21.0 | BSD-2-Clause | Вывод pytest |
| [colorama](https://pypi.org/project/colorama/0.4.6/) | 0.4.6 | BSD-3-Clause | Зависимость pytest на Windows |
| [setuptools](https://pypi.org/project/setuptools/80.9.0/) | 80.9.0 | MIT | Сборка wheel/sdist |
| [wheel](https://pypi.org/project/wheel/0.45.1/) | 0.45.1 | MIT | Инструмент сборки |

В setuptools и wheel есть вложенные компоненты со своими уведомлениями. Таблица не заменяет полные тексты: они сохранены вместе с вложенными LICENSE/NOTICE/AUTHORS из wheel. Код этих инструментов не переносился в модули LedgerGym.

Внешнее окружение, не включённое в архив: CPython 3.11.11, pip, Docker Desktop/Engine и точный образ из `ledgergym/isolated_runner.py`. Для локального получения CPython использовался uv 0.13.9 и его сборка python-build-standalone. uv, интерпретатор и контейнерные слои не распространяются в нашем офлайн-архиве; их происхождение/версии фиксируются в отчёте lg-015. При распространении самого runtime или Docker-образа нужен отдельный учёт всех включённых компонентов.

В корне репозитория находится `LICENSE` с текстом MIT для собственного кода LedgerGym. Этот документ описывает лицензии сторонних компонентов и не заменяет `LICENSE`. Правомерность указания всех правообладателей и согласие участников с выбранной лицензией должны быть подтверждены командой перед конкурсной сдачей. Пакет подготовлен для локальной проверки и review; на PyPI он не опубликован. Использование ИИ: `docs/PROVENANCE_AND_AI_DISCLOSURE.md`.
