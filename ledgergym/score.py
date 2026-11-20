"""Evidence-aware evaluator; call only within the trusted evaluator boundary."""

TYPES = {"duplicate_invoice", "payment_allocation", "fx_rate_or_date", "reporting_period"}


def validate_submission(submission, episode_id):
    """Return a boolean without echoing untrusted input or private data."""
    if not isinstance(submission, dict) or set(submission) != {"episode_id", "findings"}:
        return False
    findings = submission["findings"]
    if submission["episode_id"] != episode_id or not isinstance(findings, list) or len(findings) > 30:
        return False
    for item in findings:
        if not isinstance(item, dict) or set(item) != {"type", "affected_ids", "claimed_amount_minor", "currency", "evidence_ids", "explanation"}:
            return False
        if not isinstance(item["type"], str) or item["type"] not in TYPES or type(item["claimed_amount_minor"]) is not int or item["claimed_amount_minor"] < 0:
            return False
        if not isinstance(item["currency"], str) or len(item["currency"]) != 3 or not item["currency"].isascii() or not item["currency"].isupper() or not item["currency"].isalpha():
            return False
        if not isinstance(item["explanation"], str) or len(item["explanation"]) > 1000:
            return False
        for name, limit in (("affected_ids", 50), ("evidence_ids", 10)):
            ids = item[name]
            if not isinstance(ids, list) or not ids or len(ids) > limit or not all(isinstance(x, str) and 0 < len(x) <= 128 for x in ids) or len(set(ids)) != len(ids):
                return False
    return True


def evaluate(issues, findings, public_ids, inspection_steps):
    """Maximum-cardinality 1:1 match; unknown public IDs never qualify."""
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
    paired = {}
    def augment(i, seen):
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in paired or augment(paired[j], seen):
                paired[j] = i
                return True
        return False
    for i in range(len(findings)):
        augment(i, set())
    tp = len(paired)
    fp, fn = len(findings) - tp, len(issues) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0
    reward = max(-1.0, min(1.0, 2 * f1 - 1 - 0.002 * inspection_steps))
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1, "reward": reward}
