# LG-010 — первый минимальный сквозной прототип LedgerGym

**Статус:** TRAINING-ONLY REFERENCE IMPLEMENTATION. Не является конкурсным P0 или безопасным RL-окружением для недоверенных программ.

**Принятое ограничение области:** Tech Lead / интеграция; остальные модули команды не затронуты. Правила конкурса см. docs/COMPETITION_RULES.md; персональный scope — docs/SCOPE.md. Нельзя сливать PR или сдавать без отдельного согласования.

## Запуск из корня репозитория (Python 3.11+)

    python -m integration_reference.smoke
    python -m unittest discover -s tests -v

Никакие внешние библиотеки, API-ключи или интернет для данного прототипа не нужны.

### Зафиксированный результат локального запуска (21.11.2026)
На локальной копии идентичного кода запущено **11 unittest-проверок: PASS (11/11)**.

Результат команды demo с seed=7:
- episode_id = ep-00000007;
- 3 inspection steps: list_records + два get_document;
- finding type = duplicate_invoice, affected_ids = две сгенерированные накладные;
- evidence_ids = два доступных публичных документа;
- TP=1, FP=0, FN=0; F1=1;
- terminal reward = 2*1 - 1 - 0.002*3 = **0.994**;
- terminated=true, truncated=false.

Другие тесты: seed replay, чистый случай, отсутствие truth в JSON наблюдениях, дубли findings -> FP, недостаточный evidence -> не TP, unknown ID, 100 шагов/truncated, submit на последнем шаге, калькулятор Decimal без исполнения Python, malformed submit.

## Что демонстрирует прототип
1. Детерминированный минимальный генератор синтетических invoice/payment/ledger и открытого manifest.
2. Баланс debit_minor==credit_minor в toy fixture.
3. Одно контролируемое нарушение duplicate_invoice; для clean episode truth пуст.
4. JSON-compatible reset/step и пять команд list_records/get_record/get_document/calculator/submit.
5. Промежуточная reward=0, счётчик 100 шагов, терминальный official score.
6. Reference 1:1 maximal matching с полной проверкой набора evidence IDs.
7. Один сквозной автотест и дополнительные граничные tests.

## Критические ограничения (не скрывать)
- **Private truth находится в экземпляре ReferenceEnvironment.** Это НЕ граница безопасности для произвольного Python-агента; сам объект нельзя давать чужому коду. Продакшн-оценщик должен работать в отдельном доверенном процессе, а агент получать только сериализованные JSON observations. Тест отсутствия truth в agent JSON проверяет только конкретные ответы; не доказывает изоляцию процесса.
- Набор слишком мал: 6 ledger rows и 3 документа вместо конкурсного диапазона 200–2000 и 20–200.
- Только duplicate_invoice; missing allocation, FX и period cutoff ещё не реализованы.
- Отсутствуют два compound, hard negatives, официальный train/dev корпус, 4 baselines, траектории и контейнер.
- Не реализованы полноценная учётная политика, FX, Decimal при создании финансовых историй, Solvability Gate, CAB/EQT/FAA.
- Точная схема production truth, canonical affected IDs, допуск сумм и правила extras ещё на Gate 0. Здесь используется демонстрационный exact amount и subset evidence.
- Пагинация и tool validation — черновая реализация; нет строгой валидации всех входных JSON типов. Нельзя применять как boundary для потенциально вредоносного процесса.
- Не запущена CI GitHub Actions; PASS относится к локальному Python unittest.

## Что интегрировать дальше
1. Утвердить docs/INTERFACES.md и docs/GATE0_DECISIONS.md, заполнить командные полномочия.
2. Заменить generate_fixture() на отдельный LedgerWorld/LedgerFault через публичный EpisodeContract.
3. Заменить in-process private truth на независимый evaluator-side процесс; только JSON-wire для агента.
4. Заменить reference official_score на отдельно тестируемый LedgerScore с production validation.
5. Добавить allocation fault и clean/hard negative до расширения сценариев.
6. Подключить 10 train, 10 dev, baselines, trajectory recorder; провести P0 suite.

**Никакого заявления о выполнении конкурсных требований P0 на основании LG-010 делать нельзя.**
