"""Independently authored file-fed examples and expected policy answers."""
import csv
import json


def write_case(root, number=1, *, reverse=False, rename=False, large=False, duplicate=None):
    """Exercise transport using clean, single-error and compound synthetic inputs."""
    public = root / "public"
    private = root / "private"
    public.mkdir(parents=True)
    private.mkdir()
    def identifier(s):
        return f"ext/{number:02d} {s}" if not rename else f"{s[::-1]}@{number:02d}"
    def dump(folder, name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    def csv_table(name, fields, rows):
        with (public / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    def json_lines(name, rows):
        (public / name).write_text("".join(json.dumps(x) + "\n" for x in rows), encoding="utf-8")
    episode = identifier("book")
    count = 104 if large else 6
    amount = 15700 + number
    instant = "2026-01-31T17:00:00+05:00"
    invoice_id, doc_id = identifier("iA"), identifier("D1")
    other_id, other_doc = identifier("iB"), identifier("D2")
    payment_id, payment_doc = identifier("pay"), identifier("P1")
    ledgers = []
    accounts = ("expense", "payable", "expense", "payable", "payable", "bank")
    references = (invoice_id, invoice_id, other_id, other_id, invoice_id, invoice_id)
    for n in range(count):
        ledgers.append({"row_id": identifier(f"R{n:03}"), "timestamp": instant,
                        "account": accounts[n] if n < 6 else ("bank", "cash")[n % 2],
                        "debit_minor": amount if n % 2 == 0 else 0,
                        "credit_minor": amount if n % 2 else 0,
                        "currency": "KZT", "entity_id": identifier("company"),
                        "invoice_id": references[n] if n < 6 else None,
                        "payment_id": payment_id if n in (4, 5) else None})
    if duplicate is None:
        duplicate = 6 <= number <= 8 or number >= 16
    invoices = [{"doc_id": doc, "invoice_id": inv, "entity_id": identifier("company"),
                 "issued_at": instant, "due_at": instant, "currency": "KZT",
                 "total_minor": amount, "line_items": [{"service_ref": service, "amount_minor": amount}]}
                for inv, doc, service in [(invoice_id, doc_id, "service A"),
                                          (other_id, other_doc, "service A" if duplicate else "service B")]]
    payment = {"doc_id": payment_doc, "payment_id": payment_id, "timestamp": instant,
               "currency": "KZT", "amount_minor": amount,
               "invoice_refs": [{"invoice_id": invoice_id, "amount_minor": amount - 30 if number >= 9 else amount}]}
    rates = [{"rate_id": identifier("fx"), "date": "2026-01-31", "source_currency": "USD",
              "target_currency": "KZT", "rate": "497.0100"}]
    if reverse:
        ledgers.reverse()
        invoices.reverse()
    tables = {"ledger": ledgers, "invoices": invoices, "payments": [payment], "fx": rates}
    manifest = {"schema_version": "test-1", "episode_id": episode, "base_currency": "KZT",
                "period_start": "2026-01-01T00:00:00+05:00", "period_end": "2026-01-31T23:59:59+05:00",
                "timezone": "Asia/Almaty",
                "record_counts": {name: len(rows) for name, rows in tables.items()},
                "document_count": 3, "rounding": "ROUND_HALF_EVEN"}
    dump(public, "manifest.json", manifest)
    dump(public, "policy.json", {"rounding": "ROUND_HALF_EVEN", "amount_tolerance_minor": 0})
    csv_table("ledger.csv", list(ledgers[0]), ledgers)
    csv_table("fx.csv", list(rates[0]), rates)
    json_lines("invoices.jsonl", invoices)
    json_lines("payments.jsonl", [payment])
    # Independent public oracle values are explicit; no generator, matcher or truth reader.
    answers = []
    issues = []
    if duplicate:
        answers.append({"type": "duplicate_invoice", "affected_ids": [invoice_id, other_id],
                        "claimed_amount_minor": amount, "currency": "KZT", "evidence_ids": [doc_id, other_doc],
                        "explanation": "Both invoices charge for service A."})
        issues.append({"issue_id": "hidden-dupe", "type": "duplicate_invoice", "affected_ids": [other_id, invoice_id],
                       "expected_amount_minor": amount, "currency": "KZT", "allowed_evidence_sets": [[other_doc, doc_id]]})
    if number >= 9:
        answers.append({"type": "payment_allocation", "affected_ids": [payment_id],
                        "claimed_amount_minor": 30, "currency": "KZT", "evidence_ids": [payment_doc],
                        "explanation": "The remittance exceeds its allocation by 30 minor units."})
        issues.append({"issue_id": "hidden-partial", "type": "payment_allocation", "affected_ids": [payment_id],
                       "expected_amount_minor": 30, "currency": "KZT", "allowed_evidence_sets": [[payment_doc]]})
    dump(private, "truth.json", {"issues": issues})
    dump(private, "provenance.json", {"seed": "SECRET-PROVENANCE"})
    return {"episode_id": episode, "findings": answers}, tables
