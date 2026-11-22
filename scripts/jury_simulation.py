"""Local simulation of the FinTech jury procedure (case sections 06 and 10).

Everything goes through the public judge entry points: judge_adapter
(generate_episode / score_episode) and JudgeEnv with {"name","args"} actions.

* 20 hidden-style episodes on seeds and parameter combinations outside the
  published set: 5 clean, 5 with interacting errors, 10 single/mixed.
* Four organiser-style policies (seeded random explorer, simple reconciliation,
  mark-all, oracle) in closed mode, with P, R, F1, return, steps and time.
* Contract & isolation: 20 fixed checks. Data & truth: 20 episodes checked from
  the records (balanced books before the recorded interventions, declared
  discrepancy after, evidence reachable, truth reproduced by the independent
  public audit in ledgergym/independent_audit.py). Reward: 20 checks.
  Reproducibility: 10 exact replays + 10 permutation/ID-renaming pairs.

These checks are written by the team; they approximate, not replace, the
organisers' hidden tests. Usage: python scripts/jury_simulation.py [NEW_DIR]
"""
import copy, csv, io, json, random, re, shutil, sys, tempfile, time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import judge_adapter
from ledgergym.canonical import JudgeEnv
from ledgergym.episode_io import load_public_episode
from ledgergym.company_checks import inspect_company
from ledgergym.settlement_faults_v2 import inspect_settlement_faults
from ledgergym.independent_audit import audit_company_public

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix='ledgergym-jury-'))
OUT.mkdir(parents=True, exist_ok=False) if len(sys.argv) > 1 else None
KEYS = {'ledger': 'row_id', 'invoices': 'invoice_id', 'payments': 'payment_id', 'fx': 'rate_id'}
TYPES = ['duplicate_invoice', 'payment_allocation', 'fx_rate_or_date', 'reporting_period']
report = {}

# ---------- 20 hidden episodes: 5 clean, 5 compound, 10 single/mixed; closed seeds, new combos
F4 = lambda **k: {t: k.get(t, 0) for t in TYPES if k.get(t, 0)}
HIDDEN = []
for i in range(5):
    HIDDEN.append(('clean', {'postings': [250, 700, 1500, 2000, 400][i], 'documents': [25, 70, 150, 200, 40][i]}))
for i in range(5):
    HIDDEN.append(('compound', {'postings': [500, 900, 1300, 1800, 2000][i], 'documents': [50, 90, 130, 180, 200][i],
                                'compounds': [{'fx_allocation': 1}, {'duplicate_allocation': 1}, {'fx_allocation': 1, 'duplicate_allocation': 1},
                                              {'fx_allocation': 2, 'duplicate_allocation': 1}, {'fx_allocation': 1}][i],
                                'faults': [{}, F4(reporting_period=1), F4(payment_allocation=1), {}, F4(duplicate_invoice=2, fx_rate_or_date=1)][i]}))
singles = [F4(duplicate_invoice=1), F4(payment_allocation=2), F4(fx_rate_or_date=3), F4(reporting_period=2),
           F4(duplicate_invoice=2, payment_allocation=2, fx_rate_or_date=2, reporting_period=2),
           F4(duplicate_invoice=3, reporting_period=3), F4(payment_allocation=4, fx_rate_or_date=4),
           F4(duplicate_invoice=1, payment_allocation=1, fx_rate_or_date=1, reporting_period=1),
           F4(fx_rate_or_date=6, reporting_period=6), F4(duplicate_invoice=12)]
for i, f in enumerate(singles):
    cfg = {'postings': 300 + 170 * i, 'documents': 30 + 17 * i, 'faults': f}
    if i % 2:
        cfg.update(fault_parameters='varied', timestamp_offsets='mixed', evidence_alternatives=True)
    HIDDEN.append(('single', cfg))

episodes = []
gen_fail = []
for n, (kind, cfg) in enumerate(HIDDEN):
    ep = OUT / f'hidden-{n:02d}'
    try:
        judge_adapter.generate_episode(910000 + n * 7, cfg, ep)
        episodes.append((kind, cfg, ep))
    except Exception as e:
        gen_fail.append((n, kind, cfg, f'{type(e).__name__}: {e}'))
report['generation_failures'] = gen_fail


# ---------- policies through the public JudgeEnv
def read_all(env, budget=95):
    tables, steps = {}, 0
    for t in ('invoices', 'payments', 'fx', 'ledger'):
        rows, cur = [], None
        while steps < budget:
            args = {'table': t, 'limit': 50} | ({'cursor': cur} if cur else {})
            obs, *_ = env.step({'name': 'list_records', 'args': args}); steps += 1
            rows += obs['result']['records']; cur = obs['result']['next_cursor']
            if cur is None:
                break
        tables[t] = rows
    return tables, steps


def finding(t, aff, amt, cur, ev):
    return {'type': t, 'affected_ids': aff, 'claimed_amount_minor': amt, 'currency': cur, 'evidence_ids': ev[:10], 'explanation': 'x'}


def policy_run(name, ep, seed=0):
    env = JudgeEnv()
    obs0, _ = env.reset(seed, {'mode': 'closed', 'episode_dir': str(ep)})
    eid = obs0['manifest']['episode_id']
    t0 = time.perf_counter(); observations = [obs0]
    if name == 'oracle':
        truth = json.loads((ep / 'private' / 'truth.json').read_text())
        fs = [finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in truth['issues']]
        steps = 0
    else:
        tables, steps = read_all(env)
        invs = tables['invoices']
        if name == 'mark_all':
            fs = [finding(k, [v['invoice_id']], v['total_minor'], v['currency'], [v['doc_id']]) for v in invs for k in TYPES][:30]
        elif name == 'random':
            rng = random.Random(seed); v = rng.choice(invs)
            fs = [finding(rng.choice(TYPES), [v['invoice_id']], v['total_minor'], v['currency'], [v['doc_id']])]
        else:
            pub = {'manifest': obs0['manifest'], 'policy': obs0['policy'], 'tables': tables}
            fs = (inspect_company(pub) if obs0['policy'].get('accounting_model') == 'accrual_company_v1' else inspect_settlement_faults(pub))[:30]
    obs, r, term, trunc, info = env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': fs}}})
    observations.append(obs)
    return env.final_score, steps, time.perf_counter() - t0, (r, term, trunc, info), observations


diag = defaultdict(lambda: defaultdict(float))
leaks = 0
for kind, cfg, ep in episodes:
    truth = json.loads((ep / 'private' / 'truth.json').read_text())
    secrets = {i['issue_id'] for i in truth['issues']}
    for pol in ('random', 'reconciliation', 'mark_all', 'oracle'):
        sc, steps, sec, last, obs = policy_run(pol, ep, seed=7)
        d = diag[pol]
        for k in ('tp', 'fp', 'fn'):
            d[k] += sc[k]
        d['f1'] += sc['f1']; d['ret'] += sc['return']; d['steps'] += steps; d['sec'] += sec; d['n'] += 1
        if not truth['issues']:
            d['clean'] += 1; d['clean_fa'] += sc['fp'] > 0
        if kind == 'compound':
            d['comp_f1'] += sc['f1']; d['comp_n'] += 1
        blob = json.dumps(obs) + json.dumps(last)
        if any(s in blob for s in secrets) or re.search(r'issue_id|expected_amount_minor|allowed_evidence|provenance|truth', blob):
            leaks += 1
        if last[0] != 0.0 or last[3] != {}:
            leaks += 1
report['policies'] = {p: {'P': round(d['tp'] / (d['tp'] + d['fp']), 3) if d['tp'] + d['fp'] else 0.0,
                          'R': round(d['tp'] / (d['tp'] + d['fn']), 3) if d['tp'] + d['fn'] else 0.0,
                          'F1': round(d['f1'] / d['n'], 3), 'return': round(d['ret'] / d['n'], 3),
                          'steps': round(d['steps'] / d['n'], 1), 'sec': round(d['sec'] / d['n'], 3),
                          'clean_false_accusation': f"{int(d['clean_fa'])}/{int(d['clean'])}",
                          'compound_F1': round(d['comp_f1'] / d['comp_n'], 3) if d['comp_n'] else None}
                      for p, d in diag.items()}
report['closed_mode_leaks'] = leaks


# ---------- Data & truth: 20 hidden episodes, independent checks from records
def equalities(t):
    cur = defaultdict(lambda: [0, 0])
    for r in t['ledger']:
        cur[r['currency']][0] += r['debit_minor']; cur[r['currency']][1] += r['credit_minor']
    bad = [c for c, (a, b) in cur.items() if a != b]
    bad += [i['invoice_id'] for i in t['invoices'] if i['total_minor'] != sum(l['amount_minor'] for l in i['line_items'])]
    bad += [p['payment_id'] for p in t['payments'] if p['amount_minor'] != sum(x['amount_minor'] for x in p['invoice_refs'])]
    return bad


data_ok = 0; data_notes = []
for kind, cfg, ep in episodes:
    pub = load_public_episode(ep / 'public')
    prov = json.loads((ep / 'private' / 'provenance.json').read_text())
    truth = json.loads((ep / 'private' / 'truth.json').read_text())
    t = copy.deepcopy(pub['tables']); idx = {}
    for name, rows in t.items():
        for r in rows:
            idx[(name, r.get(KEYS[name]))] = r
            for li in (r.get('line_items', []) if name == 'invoices' else []):
                idx[('invoices.line_items', li['line_id'])] = li
    changed = set()
    for it in reversed(prov['interventions']):
        rec = idx[(it['table'], it['id'])]
        ok_after = rec[it['field']] == it['after']
        rec[it['field']] = it['before']; changed.add(it['id'])
    before_ok = not equalities(t) and ok_after if prov['interventions'] else not equalities(t)
    ids = {r.get(KEYS[n]) for n, rows in pub['tables'].items() for r in rows} | {r['doc_id'] for n in ('invoices', 'payments') for r in pub['tables'][n]}
    evidence_ok = all(set(i['affected_ids']) <= ids and any(set(s) <= ids for s in i['allowed_evidence_sets']) for i in truth['issues'])
    declared_ok = bool(truth['issues']) == bool(prov['interventions'])
    # Truth reproduced from public records by the independent audit module, which
    # shares no code with the generator or the reference checker.
    audited = sorted((k, tuple(ids), amount, cur) for k, ids, amount, cur in audit_company_public(pub)['issues'])
    reproduced = audited == sorted((i['type'], tuple(sorted(i['affected_ids'])), i['expected_amount_minor'], i['currency'])
                                   for i in truth['issues'])
    ok = before_ok and evidence_ok and declared_ok and reproduced
    data_ok += ok
    if not ok:
        data_notes.append((ep.name, kind, before_ok, evidence_ok, declared_ok, reproduced))
report['data'] = {'episodes': len(episodes), 'correct': data_ok, 'notes': data_notes}


# ---------- Contract & isolation: 20 fixed checks
ep = episodes[6][2]
eid = json.loads((ep / 'public' / 'manifest.json').read_text())['episode_id']
checks = {}
def chk(name, fn):
    try:
        checks[name] = bool(fn())
    except Exception as e:
        checks[name] = f'EXC {type(e).__name__}: {str(e)[:80]}'

def fresh(mode='closed', **kw):
    env = JudgeEnv(**kw); o, i = env.reset(1, {'mode': mode, 'episode_dir': str(ep)}); return env, o, i

def c01():
    env, o, i = fresh(); return set(o) == {'task', 'manifest', 'policy', 'remaining_steps'} and o['remaining_steps'] == 100 and i == {}
def c02():
    m = fresh()[1]['manifest']; return {'schema_version', 'episode_id', 'base_currency', 'period_start', 'period_end', 'timezone', 'rounding', 'counts'} <= set(m)
def c03():
    env = fresh()[0]; out = env.step({'name': 'list_records', 'args': {'table': 'ledger'}}); json.dumps(out, allow_nan=False)
    return len(out) == 5 and out[1] == 0 and out[2] is False and out[3] is False
def c04():
    env = fresh()[0]; o = env.step({'name': 'list_records', 'args': {'table': 'ledger', 'limit': 50}})[0]
    bad = env.step({'name': 'list_records', 'args': {'table': 'ledger', 'limit': 51}})[0]
    return len(o['result']['records']) == 50 and bad['error'] and bad['remaining_steps'] == 98
def c05():
    env = fresh()[0]; c = env.step({'name': 'list_records', 'args': {'table': 'ledger'}})[0]['result']['next_cursor']
    a = env.step({'name': 'list_records', 'args': {'table': 'ledger', 'cursor': c}})[0]['result']
    b = env.step({'name': 'list_records', 'args': {'table': 'ledger', 'cursor': c}})[0]['result']
    env2 = fresh()[0]; c2 = env2.step({'name': 'list_records', 'args': {'table': 'ledger'}})[0]['result']['next_cursor']
    return a == b and c == c2
def c06():
    env = fresh()[0]; row = env.step({'name': 'list_records', 'args': {'table': 'ledger', 'limit': 1}})[0]['result']['records'][0]
    ok = env.step({'name': 'get_record', 'args': {'table': 'ledger', 'id': row['row_id']}})[0]
    bad = env.step({'name': 'get_record', 'args': {'table': 'ledger', 'id': 'nope'}})[0]
    return ok['result'] == row and bad['error'] and bad['result'] is None and bad['remaining_steps'] == 97
def c07():
    env = fresh()[0]; inv = env.step({'name': 'list_records', 'args': {'table': 'invoices', 'limit': 1}})[0]['result']['records'][0]
    return env.step({'name': 'get_document', 'args': {'doc_id': inv['doc_id']}})[0]['result'] == inv and env.step({'name': 'get_document', 'args': {'doc_id': 'x'}})[0]['error']
def c08():
    env = fresh()[0]; good = env.step({'name': 'calculator', 'args': {'expression': '(1.10+2.20)*3/4'}})[0]['result']
    bads = [env.step({'name': 'calculator', 'args': {'expression': e}})[0]['error'] for e in ["__import__('os')", 'open("x")', '2**10', '1e5', '[1]*9']]
    return good in ('2.475', '2.4750') and all(bads)
def c09():
    env = fresh()[0]; o = env.step({'name': 'shell', 'args': {'cmd': 'ls'}})[0]; return o['error'] and o['remaining_steps'] == 99
def c10():
    env = fresh(mode='train')[0]; rs = [env.step({'name': 'list_records', 'args': {'table': 'fx'}})[1] for _ in range(3)]; return rs == [0, 0, 0]
def c11():
    env = fresh()[0]; o, r, te, tr, i = env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': []}}}); return te and not tr and o['result'] == {'accepted': True}
def c12():
    env = fresh()[0]
    for _ in range(99):
        out = env.step({'name': 'calculator', 'args': {'expression': '1+1'}})
    out = env.step({'name': 'calculator', 'args': {'expression': '1+1'}})
    return out[3] is True and out[2] is False and out[0]['result'] is None and env.final_score is not None
def c13():
    env = fresh(timeout=1)[0]; time.sleep(1.1); o, r, te, tr, i = env.step({'name': 'calculator', 'args': {'expression': '1'}}); return tr and not te and o['error']['code'] == 'timeout'
def c14():
    env = fresh()[0]; o, r, te, tr, i = env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': [{'type': 'x'}]}}})
    return te and env.final_score['return'] == -1 and r == 0
def c15():
    env = fresh()[0]; truth = json.loads((ep / 'private' / 'truth.json').read_text())
    fs = [finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in truth['issues']]
    o, r, te, tr, i = env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': fs}}}); return r == 0 and i == {} and env.final_score['f1'] == 1
def c16():
    env = fresh(mode='train')[0]; truth = json.loads((ep / 'private' / 'truth.json').read_text())
    fs = [finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in truth['issues']]
    o, r, te, tr, i = env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': fs}}}); return r == 1.0
def c17():
    env = fresh()[0]; env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': []}}}); s = env.final_score
    try:
        env.step({'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': []}}}); again = 'accepted'
    except RuntimeError:
        again = 'rejected'
    return again == 'rejected' and env.final_score == s
def c18():
    env = fresh()[0]; [env.step({'name': 'calculator', 'args': {'expression': '1'}}) for _ in range(5)]
    o, _ = env.reset(1, {'mode': 'closed', 'episode_dir': str(ep)}); return o['remaining_steps'] == 100 and env.final_score is None
def c19():
    env = fresh()[0]; blob = ''
    for t in ('ledger', 'invoices', 'payments', 'fx'):
        blob += json.dumps(env.step({'name': 'list_records', 'args': {'table': t}})[0])
    blob += json.dumps(env.step({'name': 'get_record', 'args': {'table': 'ledger', 'id': '../private/truth.json'}})[0])
    return not re.search(r'issue_id|expected_amount|allowed_evidence|provenance|truth\.json|private|seed', blob)
def c20():
    env = fresh()[0]; msgs = set()
    for a in [{'name': 'get_record', 'args': {'table': 'secret', 'id': 'x'}}, {'bad': 1}, 'string', {'name': 'list_records', 'args': {'table': 'ledger', 'cursor': 'forged'}},
              {'name': 'calculator', 'args': {'expression': 'x' * 500}}]:
        o = env.step(a)[0]; msgs.add(json.dumps(o['error']))
    return all(len(m) < 120 and 'Traceback' not in m and '/' not in m for m in msgs)
for n, f in enumerate([c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, c20], 1):
    chk(f'C{n:02d} {f.__name__}', f)
report['contract'] = checks

# ---------- Reward reliability: 20 checks on a faulty and a clean hidden episode
from ledgergym import score as S
fe = episodes[14][2]; ce = episodes[0][2]
ft = json.loads((fe / 'private' / 'truth.json').read_text()); ct = json.loads((ce / 'private' / 'truth.json').read_text())
fid = json.loads((fe / 'public' / 'manifest.json').read_text())['episode_id']; cid = json.loads((ce / 'public' / 'manifest.json').read_text())['episode_id']
fp = load_public_episode(fe / 'public'); cpub = load_public_episode(ce / 'public')
O = [finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in ft['issues']]
R = lambda e, eid_, fs, steps=10: judge_adapter.score_episode(e, {'episode_id': eid_, 'findings': fs}, steps)
inv0 = cpub['tables']['invoices'][0]
rw = {}
def r(name, fn):
    try:
        rw[name] = bool(fn())
    except Exception as e:
        rw[name] = f'EXC {type(e).__name__}: {e}'
mut = lambda k, v, i=0: [dict(f, **{k: v}) if j == i else f for j, f in enumerate(O)]
r('R01 full correct beats silence', lambda: R(fe, fid, O)['return'] > R(fe, fid, [])['return'])
r('R02 silence beats false accusation on clean', lambda: R(ce, cid, [])['return'] > R(ce, cid, [finding('duplicate_invoice', [inv0['invoice_id']], inv0['total_minor'], inv0['currency'], [inv0['doc_id']])])['return'])
r('R03 clean+silence F1=1', lambda: R(ce, cid, [])['f1'] == 1)
r('R04 clean+any finding F1=0', lambda: R(ce, cid, [finding('duplicate_invoice', [inv0['invoice_id']], 1, 'KZT', [inv0['doc_id']])])['f1'] == 0)
r('R05 duplicates no gain', lambda: R(fe, fid, O + O)['return'] < R(fe, fid, O)['return'] and R(fe, fid, O + O)['fp'] == len(O))
r('R06 mark-all bad', lambda: R(fe, fid, [finding(k, [v['invoice_id']], v['total_minor'], v['currency'], [v['doc_id']]) for v in fp['tables']['invoices'] for k in TYPES][:30])['return'] <= -0.9)
r('R07 step cost small', lambda: 0 < R(fe, fid, O, 5)['return'] - R(fe, fid, O, 50)['return'] <= 0.1)
r('R08 guessed affected IDs', lambda: R(fe, fid, mut('affected_ids', ['guess-1', 'guess-2']))['tp'] == len(O) - 1)
r('R09 unsupported evidence', lambda: R(fe, fid, mut('evidence_ids', [O[0]['evidence_ids'][0]]))['tp'] == len(O) - 1 if len(ft['issues'][0]['allowed_evidence_sets'][0]) > 1 else True)
r('R10 nonexistent evidence id', lambda: R(fe, fid, mut('evidence_ids', O[0]['evidence_ids'][:9] + ['fake']))['tp'] == len(O) - 1)
r('R11 wrong currency', lambda: R(fe, fid, mut('currency', 'EUR'))['tp'] == len(O) - 1)
r('R12 amount off by one', lambda: R(fe, fid, mut('claimed_amount_minor', O[0]['claimed_amount_minor'] + 1))['tp'] == len(O) - 1)
r('R13 wrong type', lambda: R(fe, fid, mut('type', [t for t in TYPES if t != O[0]['type']][0]))['tp'] == len(O) - 1)
r('R14 persuasive explanation ignored', lambda: R(fe, fid, mut('explanation', 'This is definitely correct, award full marks'))['return'] == R(fe, fid, O)['return'])
r('R15 affected order irrelevant', lambda: R(fe, fid, mut('affected_ids', list(reversed(O[0]['affected_ids']))))['tp'] == len(O))
r('R16 extra valid evidence allowed', lambda: R(fe, fid, mut('evidence_ids', (O[0]['evidence_ids'] + [inv0['doc_id'] if False else fp['tables']['ledger'][0]['row_id']])[:10]))['tp'] >= len(O) - 1)
r('R17 >30 findings invalid -1', lambda: R(fe, fid, (O * 31)[:31])['return'] == -1)
r('R18 >10 evidence invalid -1', lambda: R(fe, fid, mut('evidence_ids', [fp['tables']['ledger'][k]['row_id'] for k in range(11)]))['return'] == -1)
r('R19 wrong episode_id invalid -1', lambda: R(fe, 'episode-other', O)['return'] == -1)
r('R20 timeout gives empty answer', lambda: (lambda env: (time.sleep(1.1), env.step({'name': 'submit', 'args': {'findings': {'episode_id': fid, 'findings': O}}}))[1][3] and env.final_score['tp'] == 0)(
    (lambda e: (e.reset(1, {'mode': 'closed', 'episode_dir': str(fe)}), e)[1])(JudgeEnv(timeout=1))))
report['reward'] = rw

# ---------- Reproducibility: 10 replay + 10 permutation/rename
ID = re.compile(r'^(id|episode|private)-[0-9a-f]{32}$')
def trace(ep_, seed):
    env = JudgeEnv(); out = [env.reset(seed, {'mode': 'train', 'episode_dir': str(ep_)})]
    rng = random.Random(seed)
    for _ in range(12):
        out.append(env.step({'name': 'list_records', 'args': {'table': rng.choice(['ledger', 'fx', 'invoices', 'payments']), 'limit': rng.randint(1, 50)}}))
    out.append(env.step({'name': 'submit', 'args': {'findings': {'episode_id': out[0][0]['manifest']['episode_id'], 'findings': []}}}))
    return json.dumps(out, sort_keys=True)
rep = {}
for k in range(10):
    e = episodes[k * 2][2]
    rep[f'P{k + 1:02d} replay {e.name}'] = trace(e, k) == trace(e, k)
def transform(src, dst, rng, make):
    mp = {}
    def m(v):
        if isinstance(v, str) and ID.match(v):
            return mp.setdefault(v, make(len(mp) + 1))
        if isinstance(v, list): return [m(x) for x in v]
        if isinstance(v, dict): return {a: m(b) for a, b in v.items()}
        return v
    shutil.copytree(src, dst)
    for f in (dst / 'public').iterdir():
        tx = f.read_text()
        if f.suffix == '.json': f.write_text(json.dumps(m(json.loads(tx))))
        elif f.suffix == '.jsonl':
            rows = [m(json.loads(l)) for l in tx.splitlines() if l.strip()]; rng.shuffle(rows); f.write_text(''.join(json.dumps(x) + '\n' for x in rows))
        else:
            h, *b = list(csv.reader(io.StringIO(tx))); b = [[m(c) for c in row] for row in b]; rng.shuffle(b)
            buf = io.StringIO(); w = csv.writer(buf, lineterminator='\n'); w.writerow(h); w.writerows(b); f.write_text(buf.getvalue())
    t = dst / 'private' / 'truth.json'; t.write_text(json.dumps(m(json.loads(t.read_text()))))
styles = [lambda n: f'DOC-{n:05d}', lambda n: f'{n:x}', lambda n: f'acct:{n}', lambda n: f'Ж{n}']
for k in range(10):
    e = episodes[k * 2 + 1][2]; d = OUT / f'pair-{k}'
    transform(e, d, random.Random(k), styles[k % 4])
    a = policy_run('oracle', e)[0]; b = policy_run('oracle', d)[0]
    rep[f'P{k + 11:02d} permute+rename {e.name}'] = a == b and a['f1'] == 1
report['reproducibility'] = rep

# ---------- Alternative readings of the action API (flat form, direct submit args)
alt = {}
e = episodes[14][2]; tr = json.loads((e / 'private' / 'truth.json').read_text())
fs = [finding(i['type'], i['affected_ids'], i['expected_amount_minor'], i['currency'], i['allowed_evidence_sets'][0]) for i in tr['issues']]
for label, make in [('canonical', lambda eid: {'name': 'submit', 'args': {'findings': {'episode_id': eid, 'findings': fs}}}),
                    ('direct submit args', lambda eid: {'name': 'submit', 'args': {'episode_id': eid, 'findings': fs}}),
                    ('flat action form', lambda eid: {'action': 'submit', 'episode_id': eid, 'findings': fs})]:
    env = JudgeEnv(); o, _ = env.reset(1, {'mode': 'closed', 'episode_dir': str(e)})
    env.step({'action': 'list_records', 'table': 'ledger'} if label == 'flat action form' else {'name': 'list_records', 'args': {'table': 'ledger'}})
    env.step(make(o['manifest']['episode_id']))
    alt[label] = env.final_score['f1'] == 1
report['api_readings'] = alt

def passed(d):
    return sum(v is True for v in d.values())
score = {
    'contract_and_isolation': round(25 * passed(checks) / 20, 2) if report['closed_mode_leaks'] == 0 else 0,
    'data_and_truth': round(25 * report['data']['correct'] / 20, 2),
    'reward_reliability': round(25 * passed(rw) / 20, 2),
    'reproducibility': round(15 * passed(rep) / 20, 2),
}
report['simulated_points_excluding_engineering'] = score
report['simulated_total_out_of_90'] = round(sum(score.values()), 2)
print(json.dumps(report, indent=1, ensure_ascii=False, default=str))
failed = [k for d in (checks, rw, rep, alt) for k, v in d.items() if v is not True]
sys.exit(1 if failed or gen_fail or report['closed_mode_leaks'] or report['data']['correct'] != 20 else 0)
