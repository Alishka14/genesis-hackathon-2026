import copy
import itertools
import json
import sys

import pytest

from ledgergym import score
from ledgergym.env import LedgerSandbox
from ledgergym.generator import generate_episode
from ledgergym.runtime import create_episode


def finding(issue, extra=()):
    return {'type': issue['type'], 'affected_ids': issue['affected_ids'],
            'claimed_amount_minor': issue['expected_amount_minor'], 'currency': issue['currency'],
            'evidence_ids': issue['allowed_evidence_sets'][0] + list(extra), 'explanation': ''}


def assignment(issues, findings, ids):
    # Inspect trusted diagnostics only; no assignment is added to public scores.
    observed = {}
    def capture(frame, event, arg):
        if event == 'return' and frame.f_code is score.evaluate.__code__:
            observed.update({issues[j]['issue_id']: i for j, i in frame.f_locals['paired'].items()})
    prior = sys.getprofile()
    try:
        sys.setprofile(capture)
        result = score.evaluate(issues, findings, ids, 0)
    finally:
        sys.setprofile(prior)
    return observed, result


def test_tie_break_prefers_issue_id_then_original_finding_index():
    common = {'type': 'duplicate_invoice', 'affected_ids': ['i'], 'expected_amount_minor': 1,
              'currency': 'KZT', 'allowed_evidence_sets': [['d']]}
    issues = [dict(common, issue_id=k) for k in ('B', 'A')]
    answers = [finding(issues[0])] * 2
    original = copy.deepcopy((issues, answers))
    for ordered in (issues, list(reversed(issues))):
        paired, result = assignment(ordered, answers, {'i', 'd'})
        assert paired == {'A': 0, 'B': 1}
        assert result['tp'] == 2 and result['reward'] == 1
        assert set(result) == {'tp', 'fp', 'fn', 'precision', 'recall', 'f1', 'reward'}
    assert (issues, answers) == original


def test_all_three_by_three_graphs_match_independent_exhaustive_oracle():
    # Evidence alternatives encode arbitrary eligibility graphs. Brute force does
    # not use the production matching helper or augmenting-path algorithm.
    for mask in range(1 << 9):
        common = {'type': 'duplicate_invoice', 'affected_ids': ['i'], 'expected_amount_minor': 1, 'currency': 'KZT'}
        issues = [dict(common, issue_id=f'I{j}', allowed_evidence_sets=[[f'd{i}'] for i in range(3) if mask & (1 << (i * 3 + j))]) for j in range(3)]
        answers = [dict(type='duplicate_invoice', affected_ids=['i'], claimed_amount_minor=1, currency='KZT', evidence_ids=[f'd{i}'], explanation='') for i in range(3)]
        candidates = []
        for vector in itertools.product(range(4), repeat=3):
            chosen = [i for i in vector if i != 3]
            if len(chosen) != len(set(chosen)):
                continue
            if all(i == 3 or mask & (1 << (i * 3 + j)) for j, i in enumerate(vector)):
                candidates.append(vector)
        expected = min(candidates, key=lambda v: (-sum(i != 3 for i in v), v))
        paired, result = assignment(list(reversed(issues)), answers, {'i', 'd0', 'd1', 'd2'})
        assert tuple(paired.get(f'I{j}', 3) for j in range(3)) == expected, mask
        assert result['tp'] == sum(i != 3 for i in expected), mask


@pytest.mark.parametrize('scenario', ['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period'])
def test_native_and_file_judge_reject_foreign_key_as_extra_evidence(tmp_path, scenario):
    import judge_adapter
    config = {'scenario': scenario, 'fault': True}
    public, evaluate = create_episode(6, config)
    _, truth = generate_episode(6, config)
    entity = public['tables']['invoices'][0]['entity_id']
    answers = [finding(truth['issues'][0], [entity])]
    path = tmp_path / 'episode'
    judge_adapter.generate_episode(6, config, path)
    envelope = {'episode_id': public['manifest']['episode_id'], 'findings': answers}
    canonical = judge_adapter.score_episode(path, envelope, 0)
    native = evaluate(answers, 0)
    assert (native['tp'], native['fp'], native['fn']) == (0, 1, 1)
    assert {k: native[k] for k in ('tp', 'fp', 'fn')} == {k: canonical[k] for k in ('tp', 'fp', 'fn')}
    env = LedgerSandbox()
    env.reset(seed=6, config=config)
    _, reward, ended, truncated, info = env.step(dict(action='submit', **envelope))
    assert ended and not truncated and reward == -1 and info['score']['tp'] == 0


def test_record_addressability_matches_public_reader_not_foreign_keys():
    from ledgergym.record_ids import addressable_ids
    public, _ = generate_episode(7, {'scenario': 'duplicate_invoice', 'fault': False})
    public['tables']['ledger'] = [{'row_id': 'duplicate', 'invoice_id': 'dangling'}, {'row_id': 'duplicate'}, {'row_id': 'unique'}]
    public['tables']['fx'] = [{'date': '2026-01-01', 'source_currency': 'USD', 'target_currency': 'KZT', 'rate': '500'}]
    public['tables']['secret'] = [{'row_id': 'not-public'}]
    ids = addressable_ids(public)
    assert 'unique' in ids and '2026-01-01:USD:KZT' in ids
    assert not {'duplicate', 'dangling', 'not-public'} & ids
    assert public['tables']['invoices'][0]['entity_id'] not in ids
    env = LedgerSandbox(public, lambda *args: {'reward': 0})
    env.reset()
    for identity in ids:
        results = [env.step({'action': 'get_record', 'table': table, 'id': identity})[0] for table in ('ledger', 'invoices', 'payments', 'fx')]
        results.append(env.step({'action': 'get_document', 'doc_id': identity})[0])
        assert any('error' not in result for result in results), identity
