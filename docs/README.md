# Документация LedgerGym — что читать

Актуальное состояние на 22.11.2026 — в первом разделе. Остальные файлы — история разработки по этапам. Они сохранены как след работы и раскрытия использования ИИ, а их цифры и статусы относятся к своему этапу.

## Актуально для жюри

| Документ | Что в нём |
| --- | --- |
| [../README.md](../README.md) | Что это, запуск, проверка одной командой, результаты, ограничения |
| [DESIGN_NOTE.md](DESIGN_NOTE.md) | Записка о дизайне: архитектура, границы доверия, измеренные результаты |
| [INTERFACES.md](INTERFACES.md) | Контракт reset/step, формат действий и находок, правила оценки, конфигурация генератора |
| [COMPANY_MODEL.md](COMPANY_MODEL.md) | Финансовая модель компании и семантика сумм |
| [SCENARIO_CATALOG.md](SCENARIO_CATALOG.md) | Типы ошибок, связанные сценарии, чистые случаи и «ловушки» |
| [FINANCIAL_AUDIT_REPORT.md](FINANCIAL_AUDIT_REPORT.md) | Воспроизводимая матрица финансовой проверки (700 миров) |
| [verification/JURY_SIMULATION_2026-11-22.md](verification/JURY_SIMULATION_2026-11-22.md) | Симуляция процедуры жюри §06/§10: 80 из 80 проверок |
| [verification/P0_FULL_RUN_2026-11-22.md](verification/P0_FULL_RUN_2026-11-22.md) | Полный релизный гейт с Docker |
| [OFFLINE_INSTALL.md](OFFLINE_INSTALL.md) | Установка без сети из закреплённых wheel |
| [PROVENANCE_AND_AI_DISCLOSURE.md](PROVENANCE_AND_AI_DISCLOSURE.md) | Что сделано с помощью ИИ (Codex, ChatGPT, Claude Code), сторонние компоненты |
| [TEAM.md](TEAM.md) | Команда и вклад каждого участника |
| [COMPETITION_RULES.md](COMPETITION_RULES.md) | Выдержка из положения хакатона |

## Спецификации и отчёты по отдельным частям

[MATCHER_SPEC.md](MATCHER_SPEC.md), [MATCHING_SPEC.md](MATCHING_SPEC.md), [ROLE3_DESIGN.md](ROLE3_DESIGN.md), [DIAGNOSTIC_EXTENSIONS.md](DIAGNOSTIC_EXTENSIONS.md), [DIAGNOSTIC_TEST_MATRIX.md](DIAGNOSTIC_TEST_MATRIX.md), [DESIGN_REFERENCE.md](DESIGN_REFERENCE.md). Отдельные отчёты о проверках — в `verification/`: изоляция и red team ([ROLE4_REDTEAM_REPORT.md](verification/ROLE4_REDTEAM_REPORT.md)), «ловушки» с частичными оплатами и возвратами ([HARD_NEGATIVE_SETTLEMENTS.md](verification/HARD_NEGATIVE_SETTLEMENTS.md)), причинные пары ([V2_CAUSAL_PAIRS.md](verification/V2_CAUSAL_PAIRS.md)), локальная финансовая матрица ([LOCAL_FINANCIAL_MATRIX.md](verification/LOCAL_FINANCIAL_MATRIX.md)), офлайн-гейт ([OFFLINE_RELEASE_GATE.md](verification/OFFLINE_RELEASE_GATE.md)).

## История разработки (не актуальное состояние)

- **Планы и организация:** MASTER_PLAN_V2.md, MASTER_PLAN_V2_STATUS.md, P0_PLAN.md, WORK_PLAN.md, LEDGERGYM_TEAM_EXECUTION_PLAN.md, GATE0_DECISIONS.md, SCOPE.md, STATUS.md, SUBMISSION_CHECKLIST.md, CHATGPT_ROLE_PROMPTS.md.
- **Отчёты этапов:** LG010_REFERENCE_README.md, LG013_REPORT.md, LG014_REPORT.md, LG015_REPORT.md, PLAN2_PAYMENT_MATCHING_REPORT.md, P0_INTEGRATION_GATE.md, REPOSITORY_AUDIT.md, ROLE3_PHASE1_VERIFICATION.md, ROLE3_PHASE2_SECURITY.md, ROLE3_FINAL_VERIFICATION.md, ROLE3_INTEGRATION_READINESS.md.
- **Передачи между этапами 21.11 в `verification/`:** файлы с датой 2026-11-21, `FINAL_AUDIT_FIX_REPORT.md`, `LG036`–`LG038`, `MIXED_CLEAN_BASELINES.md`, `SETTLEMENT_COMPANY_V2.md`, `p0-owner-review.md`, JSON-свидетельства `role3-*.json` и проверочные скрипты `p0-matcher-probe.py`, `role3-company-smoke.py`.
- **Прежний README целиком:** [README_HISTORY.md](README_HISTORY.md).
- **Архив:** `legacy/` (ранние варианты интерфейсов и плана 2), `superpowers/` (рабочий план роли 3).
