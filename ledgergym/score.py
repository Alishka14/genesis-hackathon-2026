"""Evidence-aware evaluator; call only within the trusted evaluator boundary."""

from collections import Counter

TYPES = {"duplicate_invoice", "payment_allocation", "fx_rate_or_date", "reporting_period"}


def accessible_evidence_ids(public):
    """Only public record/document IDs that can be retrieved through the read tools."""
    table_keys = {"ledger": "row_id", "invoices": "invoice_id",
                  "payments": "payment_id", "fx": "rate_id"}
    ids = set()
    doc_ids = Counter()
    for table, key in table_keys.items():
        records = public["tables"][table]
        record_ids = Counter()
        for record in records:
            natural = record.get(key)
            if table == "fx" and not natural:
                try:
                    natural = ":".join(record[k] for k in ("date", "source_currency", "target_currency"))
                except (KeyError, TypeError):
                    natural = None
            if isinstance(natural, str) and natural:
                record_ids[natural] += 1
            if table in ("invoices", "payments"):
                doc_id = record.get("doc_id")
                if isinstance(doc_id, str) and doc_id:
                    doc_ids[doc_id] += 1
        ids.update(value for value, count in record_ids.items() if count == 1)
    ids.update(value for value, count in doc_ids.items() if count == 1)
    return ids


def validate_submission(submission, episode_id):
    """Reject malformed shape; unknown type/currency are scored as false findings."""
    if not isinstance(submission, dict) or set(submission) != {"episode_id", "findings"}:
        return False
    findings = submission["findings"]
    if submission["episode_id"] != episode_id or not isinstance(findings, list) or len(findings) > 30:
        return False
    for item in findings:
        if not isinstance(item, dict) or set(item) != {"type", "affected_ids", "claimed_amount_minor", "currency", "evidence_ids", "explanation"}:
            return False
        if not isinstance(item["type"], str) or not 0 < len(item["type"]) <= 128 or type(item["claimed_amount_minor"]) is not int or item["claimed_amount_minor"] < 0:
            return False
        if not isinstance(item["currency"], str) or len(item["currency"]) != 3 or not item["currency"].isascii()  or not item["currency"].isalpha():
            return False
        if not isinstance(item["explanation"], str) or len(item["explanation"]) > 1000:
            return False
        for name, limit in (("affected_ids", 50), ("evidence_ids", 10)):
            ids = item[name]
            if not isinstance(ids, list) or not ids or len(ids) > limit or not all(isinstance(x, str) and 0 < len(x) <= 128 for x in ids):
                return False
    return True


def _maximum_cardinality(edges, eligible_findings, eligible_issues):
    """Maximum number of disjoint matches available on these vertices."""
    allowed = set(eligible_issues)
    paired = {}

    def augment(i, seen):
        for j in edges[i]:
            if j not in allowed or j in seen:
                continue
            seen.add(j)
            if j not in paired or augment(paired[j], seen):
                paired[j] = i
                return True
        return False

    for i in eligible_findings:
        augment(i, set())
    return len(paired)


def evaluate(issues, findings, public_ids, inspection_steps):
    """Maximal-cardinality 1:1 matching; issue_id then finding index tie-break."""
    def matches(finding, issue):
        evidence = set(finding["evidence_ids"])
        return (finding["type"] == issue["type"]
                and set(finding["affected_ids"]) == set(issue["affected_ids"])
                and set(finding["affected_ids"]) <= public_ids
                and evidence <= public_ids
                and finding["claimed_amount_minor"] == issue["expected_amount_minor"]
                and finding["currency"] == issue["currency"]
                and any(set(allowed) <= evidence for allowed in issue["allowed_evidence_sets"]))

    edges = [[j for j, issue in enumerate(issues) if matches(finding, issue)] for finding in findings]
    all_findings = list(range(len(findings)))
    ordered_issues = sorted(range(len(issues)), key=lambda j: (str(issues[j].get("issue_id", "")), j))
    max_size = _maximum_cardinality(edges, all_findings, ordered_issues)
    paired = {}  # issue index -> finding index; diagnostic probe can inspect assignment
    used_findings = set()
    for position, issue_index in enumerate(ordered_issues):
        free = [i for i in all_findings if i not in used_findings]
        future = ordered_issues[position + 1:]
        remaining_target = max_size - len(paired)
        for finding_index in free:
            if issue_index not in edges[finding_index]:
                continue
            future_cardinality = _maximum_cardinality(
                edges, [i for i in free if i != finding_index], future)
            if 1 + future_cardinality == remaining_target:
                paired[issue_index] = finding_index
                used_findings.add(finding_index)
                break
    tp = len(paired)
    fp, fn = len(findings) - tp, len(issues) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0
    reward = max(-1.0, min(1.0, 2 * f1 - 1 - 0.002 * inspection_steps))
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1, "reward": reward}
