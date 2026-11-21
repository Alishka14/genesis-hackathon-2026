# LG-036 — публичный пакет FinTech (для review, не отправлен)

Дата: 21 ноября 2026. Статус: **отдельная ветка, code review и Mac acceptance ещё нужны**.

## Зачем

Исходный генератор \`ledgergym.company_dataset\` создаёт open development набор 10 train + 10 dev с отдельными \`public/\` и \`private/\` каталогами. Проверка \`--evaluate\` добавляет 60 action-only replay и **полные** семипольные траектории в \`evaluation/submission/trajectories.jsonl\`. Прямое размещение всего каталога на общем Google Drive раскрывает \`private/truth.json\` и \`private/provenance.json\`. Новый \`scripts/export_submission.py\` формирует **только публичную копию**, не изменяя источник.

## Содержимое выходного каталога

- \`index.json\` с 10 train + 10 dev.
- \`train/episode-XX/public/\` и \`dev/episode-XX/public/\`: только \`manifest.json\`, \`policy.json\`, \`ledger.csv\`, \`invoices.jsonl\`, \`payments.jsonl\`, \`fx.csv\`.
- \`trajectories.jsonl\`: запись каждого действия с полями \`episode_id\`, \`step\`, \`action\`, \`observation\`, \`reward\`, \`terminated\`, \`truncated\`. **Не** подменять этим файлом закрытую политику агента; terminal reward относится к открытому development-режиму.
- \`trace_index.json\` с 60 не-oracle базовыми траекториями.
- \`README_SUBMISSION.md\` с границами воспроизводимости.
- \`SHA256SUMS.json\` с SHA-256 всех остальных экспортируемых файлов.

Экспорт отказывается продолжать работу при отсутствующих эпизодах, нарушении schema/step последовательности, неполных trace, лишних evaluator-only полях \`seed\`/\`issue_id\`/\`truth\`/\`provenance\`, недоверенных символических ссылках и повторном использовании каталога выхода. Файлы \`private/\` не перебираются и не переносятся.

## Запуск на Mac (после Git review)

\`\`\`bash
cd ~/genesis-hackathon-2026-ledgergym
source .venv/bin/activate
git status --short
git fetch origin agent/submission/lg-036-public-export
git switch -c agent/submission/lg-036-public-export --track origin/agent/submission/lg-036-public-export

python -m pytest -q -rs tests/test_export_submission.py

RUN="$HOME/ledgergym-dev-$(date +%Y%m%d-%H%M%S)"
PUBLIC="$HOME/ledgergym-public-submission-$(date +%Y%m%d-%H%M%S)"

python3.11 -m ledgergym.company_dataset "$RUN" --evaluate --settlement-hard-negatives
python scripts/export_submission.py "$RUN" "$PUBLIC"

find "$PUBLIC" -type f | wc -l
test ! -e "$PUBLIC/train/episode-00/private/truth.json"
tar -czf "$PUBLIC.tar.gz" -C "$(dirname "$PUBLIC")" "$(basename "$PUBLIC")"
\`\`\`

**Важно:** Путь \`RUN\` содержит private evaluator truth и никогда не должен передаваться жюри целиком. Внешнему жюри предоставляется только архив из \`PUBLIC\` вместе с репозиторием, тестами, базовыми политиками, проектной запиской и инструкцией. Проверить, что файлы реально открываются из архива, и повторно выполнить профиль P0 на final SHA перед релизом.

## Тестирование и ограничения

Изолированные фикстуры экспортёра: **4 PASS** в независимом локальном Python окружении разработки функции. Проверки охватывают: копирование 20 публичных эпизодов и 60 траекторий, SHA-256, отказ от перезаписи, rejection embedded provenance/seed, неполный trace, symlink на private, path traversal. Эти 4 теста **не являются** выполнением полного source pytest проекта или проверкой общего Mac environment.

Новый код в PR, следовательно исторический \`success=true\` от \`c488465a13778a89979bdaeaf2366e6732f9346b\` **не распространяется автоматически на новый SHA**. Точный исходный коммит, состояние веток и успешные сборки капитан фиксирует перед окончательной отправкой.

Экспорт проверяет публичную структуру и запрещённые ключи; он не служит криптографической защитой от изменяющегося во время копирования чужого процесса и не заменяет ручной осмотр по требованиям конкурса. Контроль жюри и \`contest_certified\` остаются **NOT_VERIFIED**.

## Незакрытый Gate 4

LICENSE команды, утверждение авторства/роли капитана, выбор final branch и доступ GitHub, презентация в Drive, запись видео до трёх минут, проверка всех ссылок, сдача через Genesis до **22.11.2026 23:59 (Астана)**. Никакие действия по публичной публикации, merge и отправке здесь не выполнялись.
