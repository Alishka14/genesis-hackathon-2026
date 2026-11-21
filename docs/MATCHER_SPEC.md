# LedgerGym — формальная спецификация matcher и official reward

**Статус:** PROPOSED / НЕ реализовано. **Приоритет:** P0. Официальная формула неизменна. Соответствует обязательному one-to-one evidence matching GENESIS FinTech. Не считать тестовые примеры результатами выполнения.

## 1. Входы
- Trust boundary: private truth list T из evaluator-side хранилища. Agent runtime не имеет права его читать.
- Public submit: episode_id, findings[]; каждый finding содержит type, affected_ids[], claimed_amount_minor, currency, evidence_ids[], explanation.
- Evaluator получает inspection_steps; число шагов берётся из доверенной среды, не из поля агента.
- Лимиты: максимум 30 findings, 10 evidence IDs на finding, 1000 символов explanation; invalid submit => terminal reward -1, запись в приватном журнале.
- Официальные допустимые строки type, canonical affected_ids, amount tolerance, поведение extras в evidence должны быть утверждены в docs/INTERFACES.md.

## 2. Candidate edges (F_i, T_j)
Пара может быть зачтена только если:
1. type соответствует одному из четырёх поддерживаемых fault families;
2. canonical affected_ids полностью соответствуют truth, без суффиксных подсказок; duplicates in affected_ids должны иметь определённую политику;
3. валюты идентичны; сравнение денег без currency conversion не выполнять;
4. claimed_amount_minor попадает в **опубликованный** допуск amount_tolerance_minor для этой категории, определённый заранее; отсутствие допуска => нельзя самовольно выбирать процентную погрешность;
5. evidence_ids содержит минимум один полный допустимый набор публичных ID из truth.allowed_evidence_sets; контекст набора был доступен агенту через read-only actions.

Extra evidence IDs: по смыслу «хотя бы один полный набор» extras не препятствуют TP, если нет отдельного опубликованного официального запрета; нерелевантность таких extra IDs отмечается только в диагностике EQT. Это до Gate 0 зафиксировать в интерфейсе. Explanation не заменяет evidence.

## 3. 1:1 Matching
Строим двудольный граф G=(F,T,E), где рёбра существуют только для полностью валидных кандидатных пар. Находим **максимальное по мощности** сопоставление. Нельзя использовать жадный алгоритм, где выбор первого finding может лишить другого TP. Для воспроизводимости tie-break лексикографически по стабильным нормализованным ключам и original index только при идентичных остальных атрибутах.

TP = число рёбер matching; FP = len(F) − TP; FN = len(T) − TP. Повторные findings за один truth дают ровно один TP, остальные FP. При прочих равных перестановка F не меняет TP, FP, FN, F1 и reward. Полную арифметику производить с неизменными целыми и Decimal.

## 4. Формула [OFFICIAL]
P = TP/(TP+FP) если знаменатель > 0, иначе 0.
R = TP/(TP+FN) если знаменатель > 0, иначе 0.
F1 = 2TP/(2TP+FP+FN).
Если truth empty и findings empty => F1=1; truth empty и findings nonempty => F1=0. Во всех остальных случаях с нулевым знаменателем F1=0.

Terminal reward = clip(2 * F1 - 1 - 0.002 * inspection_steps, -1, 1).
Intermediate reward = 0.
Malformed submit = -1.
Соответствие числа inspection_steps: считать исследовательские действия до submit по опубликованной policy, не позволять агенту отправить собственное число.

## 5. Test vectors — рассчитать вручную до кода
| ID | Truth | Findings | Steps | Ожидаемое |
| --- | --- | --- | ---: | --- |
| M-01 | none | none | 0 | F1=1; reward=1 |
| M-02 | none | one false | 0 | TP=0, FP=1, FN=0; F1=0; reward=-1 |
| M-03 | one | complete correct finding | 10 | TP=1 FP=0 FN=0; F1=1; reward=0.98 |
| M-04 | one | no findings | 3 | TP=0 FP=0 FN=1; F1=0; reward=-1 clip |
| M-05 | one | two identical correct findings | 10 | TP=1 FP=1 FN=0; F1=2/3; reward≈0.3133333333 |
| M-06 | one | wrong currency or amount | 5 | TP=0 FP=1 FN=1; F1=0; reward=-1 clip |
| M-07 | one | matching fields, missing required evidence | 5 | TP=0 FP=1 FN=1; F1=0; reward=-1 clip |
| M-08 | one | full evidence + unrelated extra evidence | 5 | TP=1 under proposed interpretation; EQT flags irrelevant |
| M-09 | ambiguous bipartite candidates | two findings | 5 | max matching, not order-sensitive greedy |
| M-10 | one | malformed submit | 3 | reward=-1; evaluator-side validation error |
| M-11 | multiple | correct oracle reordered IDs and order | equal steps | same TP/FP/FN/F1/reward after canonical mapping |
| M-12 | none | fabricated IDs | 4 | FP count; FAA = unattributed, not invented case mapping |

**Arithmetic note:** M-05: 2*(2/3)-1-0.002*10 = 1/3 - 0.02 = 0.3133333333 (approximately).

## 6. Данные и диагностика
- В private truth минимум один allowed evidence set на каждый issue.
- Отдельный solvability preflight гарантирует public reachability evidence до запуска агента.
- EQT labels (INCOMPLETE_CHAIN, IRRELEVANT_EVIDENCE, TEMPORALLY_INVALID, CONTRADICTORY_EVIDENCE, SUFFICIENT, UNDETERMINED) — только диагностика.
- FAA метки FP (standard_valid, suspicious_but_valid, duplicate, unattributed) классифицируют каждый FP ровно в один primary bucket, сумма == FP; не влияют на reward.
- CAB paired accuracy и invariance оценивают на отдельных наборах; ни private pair labels, ни hidden expected status не возвращаются агенту.

## 7. Gate 0 для реализации
- [ ] Утвердить type enumeration, ID normalization, amount tolerance, evidence semantics.
- [ ] Утвердить unknown/excess fields и ошибочные данные (не молча coercion).
- [ ] Утвердить политику tie-break и классификации дублей.
- [ ] Утвердить что evaluator действительно находится за доверенной границей.
- [ ] Реализовать тесты M-01..M-12 **независимо от generator**.
- [ ] Проверить что official score побитово тот же с включёнными/выключенными CAB/EQT/FAA.

**Тесты:** NOT_RUN. **Источники:** официальный FinTech-кейс; docs/DIAGNOSTIC_EXTENSIONS.md; docs/DIAGNOSTIC_TEST_MATRIX.md.
