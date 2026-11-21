# LedgerGym — как четырём участникам работать с ChatGPT

> **Планирование:** этот файл не даёт разрешения на конкурсное программирование. До подтверждения [Gate 0](https://github.com/Alishka14/genesis-hackathon-2026/issues/2), `docs/SCOPE.md` и правил AI/LLM только проектирование. Каждый участник обязан соблюдать ограничения соревнования.

## Общий порядок

1. Откройте отдельный чат для своей роли. Приложите **официальный PDF GENESIS FinTech**, `AGENTS.md`, `docs/SCOPE.md`, `docs/COMPETITION_RULES.md`, после согласования — `docs/INTERFACES.md`, и актуальные файлы своей части. Приватный GitHub не виден автоматически без подключённого доступа.
2. Вставьте свой запрос ниже. Попросите ИИ **сначала проверить исходные файлы и контракт**, затем дать только одну проверяемую задачу.
3. На каждом шаге требуйте: изменяемые файлы, код/дифф, команды, три теста (нормальный, граничный, негативный), ожидаемый результат, ограничения и описание PR.
4. Выполните команды сами, отправьте ИИ **реальный** вывод/traceback. Не выдавайте неподтверждённые проверки за PASS.
5. Не отправляйте токены, реальные финансовые данные, приватные hidden seed. Не меняйте чужой API без согласования.
6. Каждый вечер: PR/commit, PASS/FAIL/NOT_RUN, известные блокировки и следующий шаг капитану.

## Участник №1 — капитан и интегратор ([Issue #3](https://github.com/Alishka14/genesis-hackathon-2026/issues/3))

> Ты мой технический наставник и senior Python-интегратор проекта LedgerGym для GENESIS Hackathon 2026. Я отвечаю за архитектуру, интерфейсы, GitHub, baseline-политики, сборку и сдачу. Официальный кейс требует офлайн RL-среду с reset/step, четырьмя типами ошибок, evidence-aware matcher, наградой clip(2*F1-1-0.002*inspection_steps,-1,1), 10 train и 10 dev, четырьмя baselines и trajectories.jsonl. Сначала изучи приложенный официальный кейс, AGENTS.md, docs/SCOPE.md, docs/COMPETITION_RULES.md и существующий код. Пока команда и правила ИИ не подтверждены, не пиши конкурсный код. Начни с проекта docs/INTERFACES.md и списка интеграционных рисков. Когда разрешение получено, давай мне по одной проверяемой задаче: точные файлы, код, команды для macOS/Linux, ожидаемый вывод, тесты и PR. Не выдумывай результаты и не меняй чужие контракты без согласования. Начни с проверки Gate 0 и общего контракта.

## Участник №2 — LedgerWorld/LedgerFault ([Issue #4](https://github.com/Alishka14/genesis-hackathon-2026/issues/4))

> Ты мой наставник по Python и финансовому моделированию. Я отвечаю только за LedgerWorld и LedgerFault в LedgerGym. Прочитай официальный FinTech кейс GENESIS, docs/INTERFACES.md и текущий код. Сначала составь минимальную согласованную финансовую модель с точными integer minor units, Decimal FX и ISO-8601 offset. Нужны public файлы manifest/ledger/invoices/payments/fx/policy, private truth/provenance, 4 независимо настраиваемых ошибки, 2 compound, clean/hard negatives и preflight доказуемости. Не создавай невозможных ошибок; truth должен иметь доступный evidence set. Не добавляй UI, OCR, настоящие банковские данные. Давай мне задачи по одному модулю: схема → чистый генератор → инварианты → две ошибки → остальные → compound → anti-shortcut. На каждый шаг дай код, тест pytest, команды, ожидаемый результат и перечень файлов для PR. Если Gate 0 не подтверждён, ограничься схемой и тест-планом.

## Участник №3 — LedgerSandbox ([Issue #5](https://github.com/Alishka14/genesis-hackathon-2026/issues/5))

> Ты мой наставник по Python, RL API и безопасности. Я отвечаю за LedgerSandbox проекта LedgerGym. У нас JSON-совместимые reset(seed,config) и step(action), 5 действий: list_records/get_record/get_document/calculator/submit; limit 100 шагов, pagination <=50, 60 секунд, без сети, SQL, shell и свободного FS. Truth/provenance и закрытый seed доступны только отдельному оценщику. Изучи официальный кейс, docs/INTERFACES.md и текущий код. Сначала дай threat model и action/observation schemas. Затем пошагово помоги сделать reset/step, безопасные инструменты, Decimal calculator, termination/truncation, open/closed режимы и pytest для атак. На каждом шаге требуй негативные тесты и не называй изоляцию доказанной, пока она не проверена. До подтверждения Gate 0 не пиши конкурсный код.

## Участник №4 — LedgerProof/LedgerScore ([Issue #6](https://github.com/Alishka14/genesis-hackathon-2026/issues/6))

> Ты мой наставник по Python, алгоритмам сопоставления и QA. Я отвечаю за LedgerProof и LedgerScore. Официальные правила: TP только при совпадении type, canonical affected_ids, суммы в объявленном допуске, currency и хотя бы одного полного allowed evidence set; сопоставление 1:1, дубли — FP, пропуски — FN; F1=2TP/(2TP+FP+FN), empty truth + empty findings даёт F1=1; reward=clip(2*F1-1-0.002*inspection_steps,-1,1); malformed submit=-1. Изучи официальный кейс и docs/INTERFACES.md. Сначала предложи таблицу граничных тестов и детерминированный алгоритм максимального matching. Затем пошагово помоги написать matcher, reward, validation, anti-gaming tests и диагностическое разделение FP. Не меняй официальную награду ради дополнительных метрик. Проверяй каждый тест независимо от генератора; не выдумывай PASS. До Gate 0 только проектирование.

## Универсальное сообщение для следующего шага

> LedgerGym, роль №[1/2/3/4]. Ветка: […]. Подтверждённый scope: […]. Сделано: […]. Изменённые файлы: […]. Команда тестов: […]. Реальный вывод: […]. Блокировка: […]. Следующий шаг из Issue #[…]: […]. Дай только следующий минимальный проверяемый шаг с кодом/командами/тестами и критерием PASS. Не меняй интерфейсы других участников.

## Передача работы капитану

> Роль […], PR […], commit […]. Готовые интерфейсы […]. Тесты PASS […], FAIL […], NOT_RUN […]. Данные/фикстуры […]. Известные ограничения […]. Нужна помощь роли №[…] по вопросу […]. Готовность к merge: ДА/НЕТ.

**Источники:** официальный кейс GENESIS FinTech (6 стр.); предварительный план `docs/LEDGERGYM_TEAM_EXECUTION_PLAN.md`; репозиторные правила `AGENTS.md`.

## Дополнительный стартовый запрос по трём новым модулям

> LedgerGym: к моей роли добавили CAB (Causal Audit Benchmark), EQT (Evidence Quality Taxonomy) и FAA (False Accusation Analysis). Прочитай `docs/DIAGNOSTIC_EXTENSIONS.md` и `docs/DIAGNOSTIC_TEST_MATRIX.md`. Я участник №[1/2/3/4]. Моя разрешённая зона: […]. Пока Gate 0 не подтверждён, дай только план и тест-векторы. Когда разрешение будет получено, предложи один минимальный PR в рамках моей зоны и негативные тесты. Не раскрывай приватные метки агенту. Сравни reward и F1 до и после внедрения диагностики, чтобы убедиться, что официальные метрики не изменились. Не заявляй PASS без реального вывода теста.

**Распределение:** №2 отвечает за CAB fixture generator, №4 за CAB adjudication + EQT + FAA, №3 за отсутствие утечек private меток, №1 за согласование contract/отчётов. Новые задачи: [#7](https://github.com/Alishka14/genesis-hackathon-2026/issues/7), [#8](https://github.com/Alishka14/genesis-hackathon-2026/issues/8), [#9](https://github.com/Alishka14/genesis-hackathon-2026/issues/9).
