"""Evaluator-only research diagnostics for LedgerGym.

EQT and FAA are explanatory postprocessors. They NEVER mutate financial records,
official score, evidence sets, findings or the closed-mode agent protocol.

This module must run only within the trusted evaluator. Its outputs can contain
sensitive labels (which records are valid/false) and are not agent observations.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from .score import _maximum_cardinality, evaluate


EQT = (
    "SUFFICIENT", "INCOMPLETE_CHAIN", "IRRELEVANT_EVIDENCE",
    "TEMPORALLY_INVALID", "CONTRADICTORY_EVIDENCE",
    "FABRICATED_ID", "UNDETERMINED",
)
FP_TYPES = (
    "FP_standard_valid", "FP_hard_negative",
    "FP_duplicate", "FP_unattributed",
)
STANDARD_VALID = "STANDARD_VALID"
SUSPICIOUS_BUT_VALID = "SUSPICIOUS_BUT_VALID"


def _core(finding, issue):
    return (
        finding["type"] == issue["type"]
        and set(finding["affected_ids"]) == set(issue["affected_ids"])
        and finding["claimed_amount_minor"] == issue["expected_amount_minor"]
        and finding["currency"] == issue["currency"]
    )


def _valid_match(finding, issue, public_ids):
    evidence = set(finding["evidence_ids"])
    return (
        _core(finding, issue)
        and set(finding["affected_ids"]) <= public_ids
        and evidence <= public_ids
        and any(set(allowed) <= evidence for allowed in issue["allowed_evidence_sets"])
    )


def exact_matching(issues, findings, public_ids):
    """Same maximum-cardinality tie-break as the official scoring matcher.

    Returns evaluator-side finding-index -> issue-index. Do NOT return this
    assignment to an untrusted agent or its observation channel.
    """
    edges = [
        [j for j, issue in enumerate(issues)
         if _valid_match(finding, issue, public_ids)]
        for finding in findings
    ]
    all_findings = list(range(len(findings)))
    ordered_issues = sorted(
        range(len(issues)), key=lambda j: (str(issues[j].get("issue_id", "")), j))
    max_size = _maximum_cardinality(edges, all_findings, ordered_issues)
    matching = {}
    used = set()
    for position, j in enumerate(ordered_issues):
        free = [i for i in all_findings if i not in used]
        future = ordered_issues[position + 1:]
        outstanding = max_size - len(matching)
        for i in free:
            if j not in edges[i]:
                continue
            remaining = _maximum_cardinality(
                edges, [k for k in free if k != i], future)
            if 1 + remaining == outstanding:
                matching[i] = j
                used.add(i)
                break
    if len(matching) != max_size:
        raise ValueError("matching contract diverged")
    return matching, edges


def evidence_taxonomy(issues, findings, public_ids, *,
                      temporally_invalid_ids=(), contradictory_ids=()):
    """Tag evidence without redefining official eligibility.

    TEMPORALLY_INVALID and CONTRADICTORY_EVIDENCE require externally verified
    public-policy evidence IDs. They are NEVER inferred from an issue label.
    A complete valid evidence chain may coexist with an irrelevant extra ID.
    """
    public_ids = set(public_ids)
    temporal = set(temporally_invalid_ids)
    contradiction = set(contradictory_ids)
    if not temporal <= public_ids or not contradiction <= public_ids:
        raise ValueError("explicit evidence tags must refer to public IDs")
    tagged = []
    for finding in findings:
        evidence = set(finding["evidence_ids"])
        related = [issue for issue in issues if _core(finding, issue)]
        categories = set()
        if evidence - public_ids or set(finding["affected_ids"]) - public_ids:
            categories.add("FABRICATED_ID")
        if evidence & temporal:
            categories.add("TEMPORALLY_INVALID")
        if evidence & contradiction:
            categories.add("CONTRADICTORY_EVIDENCE")
        if related:
            relevant = set().union(
                *(set(allowed) for issue in related
                  for allowed in issue["allowed_evidence_sets"]))
            if evidence - relevant:
                categories.add("IRRELEVANT_EVIDENCE")
            if any(
                set(finding["affected_ids"]) <= public_ids
                and evidence <= public_ids
                and any(set(allowed) <= evidence
                        for allowed in issue["allowed_evidence_sets"])
                for issue in related
            ):
                categories.add("SUFFICIENT")
            else:
                categories.add("INCOMPLETE_CHAIN")
        if not categories:
            categories.add("UNDETERMINED")
        tagged.append([tag for tag in EQT if tag in categories])
    counts = {tag: sum(tag in tags for tags in tagged) for tag in EQT}
    return {
        "method": "evaluator_only_eqt_v1",
        "items": tagged, "counts": counts,
        "official_score_modified": False,
        "explicit_temporal_validation_only": True,
    }


def _normalized_cases(case_annotations, public_ids):
    """Private evaluator labels, one case -> (kind, identifiers).

    A case can contain multiple public IDs; case-level FPR counts it once.
    """
    if case_annotations is None:
        return {}
    if not isinstance(case_annotations, Mapping):
        raise TypeError("case annotations must be a mapping")
    cases = {}
    for case_id, case in case_annotations.items():
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("invalid case id")
        if not isinstance(case, Mapping) or set(case) != {"kind", "affected_ids"}:
            raise ValueError("invalid case annotation")
        kind = case["kind"]
        ids = case["affected_ids"]
        if (kind not in (STANDARD_VALID, SUSPICIOUS_BUT_VALID)
                or not isinstance(ids, (tuple, list, set))
                or not ids or not set(ids) <= public_ids
                or not all(isinstance(i, str) for i in ids)):
            raise ValueError("invalid annotated public IDs")
        cases[case_id] = (kind, frozenset(ids))
    return cases


def false_accusation_analysis(issues, findings, public_ids, *,
                              case_annotations=None, inspection_steps=0):
    """Partition the *official* FP with strict, mutually exclusive priority.

    Priority: duplicate of a true match > fabricated/unattributable ID >
    annotated hard negative > annotated standard-valid > unattributed.

    Case labels are evaluator-only research metadata, not sent to policies.
    When the source supplies no labels, unknown cases remain UNATTRIBUTED,
    not silently classified as STANDARD_VALID.
    """
    public_ids = set(public_ids)
    cases = _normalized_cases(case_annotations, public_ids)
    score = evaluate(issues, findings, public_ids, inspection_steps)
    matched, edges = exact_matching(issues, findings, public_ids)
    if len(matched) != score["tp"]:
        raise ValueError("diagnostic matching disagrees with official TP")
    counts = Counter({tag: 0 for tag in FP_TYPES})
    details = []
    affected_cases = set()
    for index, finding in enumerate(findings):
        if index in matched:
            details.append(None)
            continue
        affected = set(finding["affected_ids"])
        evidence = set(finding["evidence_ids"])
        if edges[index]:
            category = "FP_duplicate"
        elif not affected <= public_ids or not evidence <= public_ids:
            category = "FP_unattributed"
        else:
            hits = [
                (case_id, kind)
                for case_id, (kind, ids) in cases.items()
                if affected & ids
            ]
            if any(kind == SUSPICIOUS_BUT_VALID for _, kind in hits):
                category = "FP_hard_negative"
            elif any(kind == STANDARD_VALID for _, kind in hits):
                category = "FP_standard_valid"
            else:
                category = "FP_unattributed"
            affected_cases.update(case_id for case_id, _ in hits)
        counts[category] += 1
        details.append(category)
    if sum(counts.values()) != score["fp"]:
        raise ValueError("FAA partition does not equal official FP")
    denominators = {
        STANDARD_VALID: sum(kind == STANDARD_VALID for kind, _ in cases.values()),
        SUSPICIOUS_BUT_VALID: sum(
            kind == SUSPICIOUS_BUT_VALID for kind, _ in cases.values()),
    }
    rates = {}
    affected = {}
    for kind, field in (
        (STANDARD_VALID, "standard_valid_case_fpr"),
        (SUSPICIOUS_BUT_VALID, "hard_negative_case_fpr"),
    ):
        cases_with_fp = sum(
            case_id in affected_cases and tagged_kind == kind
            for case_id, (tagged_kind, _) in cases.items())
        affected[field] = {"opportunities": denominators[kind],
                           "cases_with_fp": cases_with_fp}
        rates[field] = (cases_with_fp / denominators[kind]
                        if denominators[kind] else None)
    return {
        "method": "evaluator_only_faa_v1",
        "fp_subtypes": dict(counts),
        "fp_classification_by_finding": details,
        "case_level": affected,
        "rates": rates,
        "official_fp": score["fp"],
        "official_reward_unchanged": score["reward"],
    }
