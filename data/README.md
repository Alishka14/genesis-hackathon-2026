# Открытые эпизоды 10 train + 10 dev

`ledgergym-public-10plus10.zip` — опубликованный открытый набор для FinTech-кейса (§09 «Эпизоды» и «Траектории»).

- SHA-256 архива: `127b024b9e00f36bd065e677315162274b7d9286cc5988b55a648fd4f2a98561`
- 20 синтетических компаний (`train/episode-00…09`, `dev/episode-00…09`), в каждой только публичные файлы: `manifest.json`, `policy.json`, `ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`.
- `trajectories.jsonl` — 60 траекторий трёх неоракульных базовых политик, 1 488 переходов, 7 полей на шаг: `episode_id`, `step`, `action`, `observation`, `reward`, `terminated`, `truncated`. `trace_index.json` указывает строки каждой траектории.
- `SHA256SUMS.json` — хэши всех 125 файлов. Эталон (`private/truth.json`) и история внесённых ошибок (`private/provenance.json`) **не включены**.

Проверка после распаковки:

```bash
unzip -q data/ledgergym-public-10plus10.zip -d /tmp/ledgergym-public
```

```bash
python3 scripts/verify_submission_package.py /tmp/ledgergym-public/ledgergym-public-10plus10
```

Ожидаемый результат: `"status": "PASS"`, `"private_truth_exported": false`.

Тот же набор детерминированно воспроизводится из исходников; содержимое совпадает побайтно:

```bash
python3 -m ledgergym.company_dataset "$HOME/ledgergym-run" --evaluate --settlement-hard-negatives
```

```bash
python3 scripts/export_submission.py "$HOME/ledgergym-run" "$HOME/ledgergym-public"
```

Данные полностью синтетические. Это открытый набор для разработки, а не закрытый тест организаторов.
