# LedgerGym — script for a truthful demo video (target 2:40–2:55)

**Recording status:** not recorded. **Verified evidence:** operator's local macOS Python 3.14 integration PASS, Docker 22/22 PASS; installed-wheel offline gate PASS under Python 3.11.18, 45/45 tests, 145 hash-checked files, 20 episodes/60 replays. These are **local reports**, not official organizer results.

## Recording prerequisites

- Screen-record a clean Terminal or editor. Avoid showing local usernames, absolute personal paths, tokens, Docker environment variables, private evaluator truth, or credentials.
- From repository branch `agent/submission/lg-028-demo-handoff`, run `python3.11 --version` and `git rev-parse --short HEAD`. Record the exact tested commit; do not claim a later commit inherits all earlier tests without checking it.
- Keep `$HOME/ledgergym-offline-report.json` as an internal source of the aggregate statistics. It is acceptable to show aggregate status, not raw synthetic private labels.
- **Critical distinction:** `python3.11 -m ledgergym.role3_demo local` uses a *clean* duplicate-invoice episode, and the supplied `examples/role3_policy.py` **always submits an empty findings list**. Thus `F1=1.0` with TP=FP=FN=0 here confirms correct behavior on a clean episode, **not demonstrated fault detection**.

## Narrative with shot plan (Russian)

| Time | On screen — real commands / artifacts | Narration guidance |
| --- | --- | --- |
| 0:00–0:18 | Project name LedgerGym and financial audit scenario summary | «Финансовый аудит зависит от доказательств: одинаковые суммы сами по себе ещё не означают ошибку. Мы создали синтетическую среду, в которой можно безопасно проверять расследование платежей и документов». |
| 0:18–0:42 | `README.md` and `docs/INTERFACES.md`; public six-file schema `ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`, `policy.json`, `manifest.json` | «Генератор создаёт согласованную историю компании. Агент получает публичные документы и работает через ограниченный интерфейс, а эталон ответов остаётся в доверенном оценщике». |
| 0:42–1:12 | Run `python3.11 -m ledgergym`; **inspect actual JSON first**; only if returned TP=1, point to a synthetic duplicate and score | «В учебном примере два счёта описывают одну услугу. Агент проверяет записи и предъявляет связанные доказательства». Do not call this the canonical closed-mode baseline: it is an older trusted local prototype. |
| 1:12–1:40 | Run `python3.11 -m ledgergym.role3_demo local`. Show `VERIFIED_PASS`, `replay: exact`, actions `list_records` → `get_document` → `calculator` → `submit` | «Другой контрольный пример содержит ноль нарушений. Правильный результат здесь — не выдумывать ошибки. Действия и оценка воспроизводятся точно». |
| 1:40–2:05 | Show sanitized `integration-full.json` in editor (from local operator) and 20 train/dev, 60 trajectories, 6 causal pairs | «В интеграционной проверке мы построили 20 эпизодов, воспроизвели 60 траекторий и проверили шесть причинных пар. В контрольных парах не было ложных обвинений». Keep benchmark scope explicit; no claims about external generalization. |
| 2:05–2:25 | Capture a terminal running `python -m pytest -q -rs tests/test_isolated_runner.py tests/test_role3_runtime.py` **only if time permits**, or show the already observed `22 passed` result. | «Мы отдельно протестировали изоляцию агента: ограничения сети, файловой системы и очистку контейнера. 22 локальных Docker-теста прошли». |
| 2:25–2:45 | Open sanitized `ledgergym-offline-report.json`, show `success: true`, `45 executed`, `145 verified files`, `replay: exact` | «Пакет также собран и проверен в чистой среде Python 3.11 без обращения к каталогу пакетов при установке». |
| 2:45–2:55 | End screen with README launch instructions and exact commit | «Все инструкции, ограничения и использованные библиотеки указаны в репозитории». |

## Dry-run commands (Mac, no video editing performed here)

```bash
python3.11 --version
git rev-parse --short HEAD
python3.11 -m ledgergym
python3.11 -m ledgergym.role3_demo local
```

The first `ledgergym` example is expected to investigate a **faulty synthetic duplicate invoice**, while `role3_demo local` is a **clean canonical control**. Run both and read the actual JSON outputs *before recording*. If the former does not report a correct detected duplicate, do not claim that it did; instead show the verified company/causal dataset and state what was actually observed.

The local full integration and offline release reports have already been tested separately. Do not re-run heavyweight processes merely for a smooth recording; an honest captured Terminal result and its origin is sufficient. Avoid presenting the oracle policy as an autonomous agent: it receives evaluator information and is intended only as an upper-bound control.

## Recording acceptance

- Actual screen capture with continuous/clearly labeled cuts and the output corresponding to the displayed command.
- Under **3:00** including title/credits; verify file plays without codec problems.
- No secrets, private evaluation material, personal home-directory paths, or real financial data.
- Narration accurately separates trusted prototype, clean canonical demo, synthetic generator benchmarks, and real Docker sandbox checks.
- Final shared video URL and access check must be completed by the team; not supplied by this doc.
