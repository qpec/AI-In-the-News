"""Synthetic complete inputs and actual fixed algorithms; no owner/account/model I/O."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research/cybercrime_nl/runtime'))
import final_validation_fixed_slots as subject  # noqa: E402
import final_validation_history_closure as closure  # noqa: E402
from test_final_validation_packets import case  # noqa: E402
from test_final_validation_history_closure import minimal  # noqa: E402
from test_final_validation_history import reference  # noqa: E402


@pytest.fixture(scope="module")
def counter():
    return subject.original.load_token_counter(evidence_record=digest("synthetic-fixed-tokenizer"), expected_identity={
        "encoding": "cl100k_base", "library": "tiktoken", "version": importlib.metadata.version("tiktoken")})


def fixture(counter, size=8):
    frame, schedule, docs, old = case(counter, size)
    args = list(minimal())
    args[0] = frame.index
    projection = closure._compile(*args)
    legacy = deepcopy(old['history_inventory'])
    legacy.update(complete=False, global_gap=True)
    bindings = {key: digest(['synthetic-fixed-scope', key]) for key in subject.BINDINGS}
    values = dict(selection={'kind': 'initial'}, legacy_records=[], legacy_inventory=legacy,
        closure_evidence=subject.bind_closure_projection(projection), order_seed=old['order_seed'], bindings=bindings,
        token_counter=counter, cli_profile=old['cli_profile'], resources=old['resources'],
        user_instruction_sha256=old['user_instruction_sha256'])
    rebind(values)
    return frame, schedule, docs, values


def rebind(values):
    values['bindings'].update(closure_projection_sha256=values['closure_evidence'].digest,
        legacy_records_sha256=digest(values['legacy_records']), legacy_inventory_sha256=digest(values['legacy_inventory']),
        order_seed_artifact=digest(subject.original.order_seed_payload(values['order_seed'])),
        tokenizer_evidence_record=values['token_counter'].evidence_record)


def prepare(data, **changes):
    return subject.prepare_fixed_slots(*data[:3], **(data[3] | changes))


def projection(data, update):
    value = data[3]['closure_evidence'].projection
    update(value)
    regions = value['unresolved_regions']
    value['scoped_certificate'].update(complete=not regions,
        global_gap=any(r['affected_input_sha256'] is None for r in regions),
        unknown_input_sha256=sorted({h for r in regions for h in (r['affected_input_sha256'] or [])}))
    data[3]['closure_evidence'] = subject.bind_closure_projection(value)
    rebind(data[3])


def region(inputs, role=None):
    return {'reason_code': 'unclassified_full_event', 'owner_sha256': digest('synthetic-owner'),
        'evidence_sha256': digest(['synthetic-gap', inputs]), 'affected_input_sha256': inputs, 'role': role}


def blocker(data, rank, *, role='primary', batch=False):
    positions = subject.pair_from_rank(len(data[0].index.inputs), rank)
    inputs = sorted(data[0].index.inputs[i].input_sha256 for i in positions)
    ref = {'producer': 'main_task_scope', 'attempt_id': digest('original-attempt')}
    if batch:
        ref = {'physical_id': digest('one-original-batch'), 'logical_slot_id': digest(['slot', rank]),
            'request_artifact': digest('batch-request'), 'dispatch_artifact': digest('batch-dispatch'),
            'family': 'synthetic-exact-batch'}
    return {'pair_key': digest({'input_sha256': inputs, 'role': role}), 'input_sha256': inputs,
        'role': role, 'references': [ref]}


def later(data):
    ceilings = {'maximum_cumulative_invocations': 10000, 'maximum_cumulative_token_reservations': 100000000,
        'maximum_tranche_primary': 40, 'maximum_tranche_invocations': 60}
    start = len(data[1].manifest['initial_prefix']['primary_ranks'])
    plan = subject.kernel.bounded_segment(data[1], start=start, ceilings=ceilings)
    plan.update(previous_manifest=digest('original-manifest'), prior_census_sha256=digest('durable-census'))
    return {'kind': 'later', 'plan': plan, 'ceilings': ceilings, 'primary_limit': 40}


def test_actual_closure_initial_full_packets_and_original_execution_manifest(counter):
    data = fixture(counter)
    before = canonical(data[3]['legacy_inventory'])
    prepared = prepare(data)
    value = prepared.payload
    assert before == canonical(data[3]['legacy_inventory'])
    assert value['history_envelope']['legacy_inventory']['global_gap']
    assert not value['derived_history_inventory']['global_gap']
    assert not value['source_history_seed_and_authority_provenance_verified'] and not value['dispatch_authorized']
    assert prepared.resources == data[3]['resources']
    assert [(t['pair_rank'], t['role']) for t in prepared.tasks] == [(s['pair_rank'], s['kind'])
        for s in data[1].manifest['initial_prefix']['tasks']]
    for task, details in zip(prepared.tasks, value['slot_resource_details'], strict=True):
        positions = subject.pair_from_rank(len(data[2]), task['pair_rank'])
        assert {(d['title'], d['body']) for d in task['packet']['documents']} == {
            (data[2][i]['title'], data[2][i]['body']) for i in positions}
        stdin = task['packet']['stdin']
        assert 'PRIVATE/' not in stdin and 'MUST_NOT_ENTER_WIRE' not in stdin
        assert 'prior_exposure' not in stdin and 'pair_rank' not in stdin
        assert details['stdin_bytes'] == len(stdin.encode())
        assert details['input_tokens_proxy'] == counter.count(stdin)
        assert json.loads(prepared.artifacts[details['packet_artifact']]) == task['packet']
    manifest = prepared.build_execution_manifest(digest('synthetic-admission'))
    assert subject.execution.validate_manifest(manifest) == manifest
    assert manifest['planned_new_invocations'] == len(prepared.tasks)
    assert manifest['account_dollar_cost'] is None
    assert digest(prepared.catalog) == manifest['slot_catalog_sha256']
    assert 'Complete synthetic source' not in canonical(prepared.catalog)


def test_later_contiguous_roles_share_inventory_namespace_and_frozen_orders(counter):
    data = fixture(counter, 12)
    first = prepare(data)
    selection = later(data)
    result = prepare(data, selection=selection)
    plan = selection['plan']
    assert [(t['pair_rank'], t['role']) for t in result.tasks] == plan['slots']
    assert not any(t['role'] == 'uncertain_adjudication' for t in result.tasks)
    assert {t['history']['inventory_sha256'] for t in first.tasks} == {t['history']['inventory_sha256'] for t in result.tasks}
    assert first.payload['history_envelope_sha256'] == result.payload['history_envelope_sha256']
    normalized = subject.kernel._normalize_tasks(result.tasks, plan['slots'], data[0],
        first.payload['execution_scope'], data[3]['resources']['output_token_allowance'])
    assert all(t['logical_task_id'] == digest([subject.execution.METHOD, 'logical-pair-role',
        digest(first.payload['execution_scope']), t['history']['source_identity'], t['role']]) for t in normalized)
    assert not ({(t['pair_rank'], t['role']) for t in first.tasks} & {(t['pair_rank'], t['role']) for t in result.tasks})
    assert prepare(data, selection=selection).payload_json == result.payload_json
    with pytest.raises(ResearchError, match='later_uses_registered_series'):
        result.build_execution_manifest(digest('not-an-initial-admission'))


@pytest.mark.parametrize('fault', ['rank', 'role', 'start', 'diagnostic', 'order', 'count', 'bool'])
def test_later_cannot_redraw_replace_prefix_or_add_diagnostics(counter, fault):
    data = fixture(counter, 12)
    selected = later(data)
    plan = selected['plan']
    if fault == 'rank':
        plan['slots'][0] = (0, 'primary')
    elif fault == 'role':
        plan['slots'][0] = (plan['slots'][0][0], 'qc')
    elif fault == 'start':
        plan['start'] = 0
    elif fault == 'diagnostic':
        plan['diagnostic_identities_added'] = [plan['primary_ranks'][0]]
    elif fault == 'order':
        plan['slots'].reverse()
    elif fault == 'count':
        plan['stop'] += 1
    else:
        plan['statistical_look'] = 0
    with pytest.raises(ResearchError, match='later_'):
        prepare(data, selection=selected)


def test_global_no_retry_gap_preserves_all_fixed_slots_without_packets_or_fake_attempts(counter):
    data = fixture(counter)
    projection(data, lambda p: p['unresolved_regions'].append(region(None)))
    result = prepare(data)
    assert len(result.tasks) == len(data[1].manifest['initial_prefix']['tasks'])
    assert all(t['packet'] is None and t['history']['state'] == 'prior_attempt_unavailable'
        and t['history']['positive'] is None and not t['history']['diagnostic_eligible']
        and not t['history']['physical_attempts'] for t in result.tasks)
    assert result.payload['resource_census']['planned_token_reservations'] == 0
    assert result.build_execution_manifest(digest('synthetic-admission'))['planned_new_invocations'] == 0


def test_bounded_gap_blocks_intersections_and_exposure_unknown_does_not(counter):
    data = fixture(counter)
    affected = data[0].index.inputs[0].input_sha256
    projection(data, lambda p: p['unresolved_regions'].append(region([affected])))
    result = prepare(data)
    fresh = 0
    for task in result.tasks:
        blocked = affected in {s['input_sha256'] for s in task['history']['source_identity']}
        assert (task['packet'] is None) == blocked
        fresh += not blocked
    assert 0 < fresh < len(result.tasks)


def test_exact_old_pair_role_blocks_without_creating_label_or_blocking_other_roles(counter):
    data = fixture(counter)
    rank = next(s['pair_rank'] for s in data[1].manifest['initial_prefix']['tasks'] if s['kind'] == 'qc')
    row = blocker(data, rank)
    projection(data, lambda p: p['pair_role_blockers'].append(row))
    result = prepare(data)
    pair = [t for t in result.tasks if t['pair_rank'] == rank]
    assert next(t for t in pair if t['role'] == 'primary')['packet'] is None
    assert all(t['packet'] is not None for t in pair if t['role'] != 'primary')
    assert all(t['history']['positive'] is None and not t['history']['physical_attempts'] for t in pair)
    maps = json.loads(result.artifacts[result.payload['physical_reference_maps_artifact']])
    assert maps['pair_role_blockers'] == [row]


def test_one_batch_remains_external_map_with_conservative_endpoint_regions(counter):
    data = fixture(counter)
    ranks = data[1].manifest['initial_prefix']['primary_ranks'][:2]
    rows = [blocker(data, rank, batch=True) for rank in ranks]
    projection(data, lambda p: p['pair_role_blockers'].extend(rows))
    result = prepare(data)
    endpoints = {h for row in rows for h in row['input_sha256']}
    for task in result.tasks:
        blocked = bool(endpoints & {s['input_sha256'] for s in task['history']['source_identity']})
        assert (task['packet'] is None) == blocked
        assert not task['history']['physical_attempts'] and task['history']['positive'] is None
    maps = json.loads(result.artifacts[result.payload['physical_reference_maps_artifact']])
    assert len({ref['physical_id'] for row in maps['pair_role_blockers'] for ref in row['references']}) == 1
    assert result.payload['history_envelope']['batch_endpoint_exclusion_sha256'] == sorted(endpoints)


def test_compatible_ordinary_reference_reuse_and_prior_intent_remain_original(counter):
    data = fixture(counter)
    primary = [t for t in prepare(data).tasks if t['role'] == 'primary'][:2]
    records = [reference(t['packet'], identity=str(i)) for i, t in enumerate(primary)]
    records[1].update(attempt_state='intent', payload=None, provenance=None)
    data[3]['legacy_records'] = records
    rebind(data[3])
    result = prepare(data)
    by_rank = {t['pair_rank']: t for t in result.tasks if t['role'] == 'primary'}
    assert by_rank[primary[0]['pair_rank']]['history']['state'] == 'reused_resolved'
    assert by_rank[primary[1]['pair_rank']]['history']['state'] == 'prior_attempt_unavailable'
    for original, record in zip(primary, records, strict=True):
        row = by_rank[original['pair_rank']]
        assert row['packet'] is None
        assert row['history']['physical_attempts'] == [{k: record[k] for k in ('owner_sha256', 'attempt_id')}]
    assert result.build_execution_manifest(digest('admission'))['planned_new_invocations'] == len(result.tasks) - 2


def test_same_ordinary_physical_judgment_cannot_be_remapped_to_an_independent_role(counter):
    data = fixture(counter)
    task = next(t for t in prepare(data).tasks if t['role'] == 'qc')
    records = [reference(task['packet'], role=role) for role in ('primary', 'qc')]
    records[1]['record_id'] = digest('second-view')
    data[3]['legacy_records'] = records
    rebind(data[3])
    with pytest.raises(ResearchError, match='conflicting_physical'):
        prepare(data)


def test_capacity_preserves_exact_full_stdin_and_fixed_conditional_denominators(counter):
    data = fixture(counter)
    result = prepare(data, max_input_tokens=1)
    assert len(result.tasks) == len(data[1].manifest['initial_prefix']['tasks'])
    for task in result.tasks:
        assert task['packet'] is None and task['history']['state'] == 'fresh_unattempted'
        proof = json.loads(result.artifacts[task['capacity_unavailable']['evidence_sha256']])
        stdin = result.artifacts[proof['stdin_artifact']].decode()
        assert counter.count(stdin) == proof['input_tokens_proxy'] > 1
        assert proof['input_bytes'] == len(stdin.encode()) and proof['no_truncation']
        assert not proof['provider_attempted'] and proof['new_model_calls'] == 0
        articles = json.loads(json.loads(stdin)['evidence'][0]['text'])['articles']
        positions = subject.pair_from_rank(len(data[2]), task['pair_rank'])
        assert {(a['title'], a['body']) for a in articles} == {(data[2][i]['title'], data[2][i]['body']) for i in positions}
    assert result.build_execution_manifest(digest('admission'))['planned_new_invocations'] == 0


def test_noncapacity_contract_error_propagates(counter, monkeypatch):
    def fail(*args, **kwargs):
        raise ResearchError('synthetic_integrity_failure')
    monkeypatch.setattr(subject.contract, 'request', fail)
    with pytest.raises(ResearchError, match='synthetic_integrity_failure'):
        prepare(fixture(counter))


@pytest.mark.parametrize('fault', ['legacy', 'closure_hash', 'order', 'tokenizer', 'extra_complete', 'index', 'document', 'bytes'])
def test_source_history_order_and_proof_substitution_fails(counter, fault):
    data = fixture(counter)
    options = data[3]
    if fault == 'legacy':
        options['legacy_inventory']['global_gap'] = False
    elif fault == 'closure_hash':
        options['bindings']['closure_projection_sha256'] = digest('wrong')
    elif fault == 'order':
        options['order_seed'] += '-changed'
    elif fault == 'tokenizer':
        options['bindings']['tokenizer_evidence_record'] = digest('wrong')
    elif fault == 'extra_complete':
        options['bindings']['complete'] = True
    elif fault == 'index':
        value = options['closure_evidence'].projection
        value['input_index_digest'] = digest('wrong')
        options['closure_evidence'] = subject.bind_closure_projection(value)
        rebind(options)
    elif fault == 'document':
        data[2][-1]['body'] += 'omitted tail'
    else:
        evidence = options['closure_evidence']
        options['closure_evidence'] = replace(evidence, projection_json=evidence.projection_json + b' ')
    with pytest.raises(ResearchError):
        prepare(data)


@pytest.mark.parametrize('fault', ['flags', 'outside', 'key', 'root', 'head', 'additional'])
def test_self_consistent_hash_cannot_override_structural_closure_gaps(counter, fault):
    data = fixture(counter)
    value = data[3]['closure_evidence'].projection
    if fault == 'flags':
        value['unresolved_regions'].append(region(None))
    elif fault == 'outside':
        value['unresolved_regions'].append(region([digest('not-current-input')]))
    elif fault == 'key':
        row = blocker(data, 0)
        row['pair_key'] = digest('wrong-pair-role')
        value['pair_role_blockers'].append(row)
    elif fault == 'root':
        value['root_dispositions'][0]['status'] = 'matched_basename_only'
    elif fault == 'head':
        next(iter(value['owner_partitions'].values()))['source_head'][0] += 1
    else:
        value['complete_override'] = True
    data[3]['closure_evidence'] = subject.bind_closure_projection(value)
    rebind(data[3])
    with pytest.raises(ResearchError):
        prepare(data)


def test_payload_artifacts_are_immutable_and_reopen_preserves_exact_wire(counter, tmp_path):
    result = prepare(fixture(counter))
    value = result.payload
    value['tasks'].clear()
    assert result.tasks
    with pytest.raises(TypeError):
        result.artifacts[digest('new')] = b'other'
    for key, raw in result.artifacts.items():
        assert hashlib.sha256(raw).hexdigest() == key
        (tmp_path / key).write_bytes(raw)
    reopened = subject.PreparedFixedSlots(result.payload_json, {k: (tmp_path / k).read_bytes() for k in result.artifacts}, result.digest)
    assert reopened.build_execution_manifest(digest('admission')) == result.build_execution_manifest(digest('admission'))
    bad = replace(result, payload_json=subject._bytes({**result.payload, 'new_model_calls': 1}))
    with pytest.raises(ResearchError, match='preparation_digest'):
        bad.build_execution_manifest(digest('admission'))


def test_output_resources_are_reservations_not_remote_generation_or_dollar_claims(counter):
    result = prepare(fixture(counter))
    census = result.payload['resource_census']
    assert census['account_dollar_cost'] is None and not census['generation_token_cap_enforced']
    assert census['coordinator_invocations_not_remote_requests']
    assert census['planned_token_reservations'] == sum(d['input_tokens_proxy'] + d['output_token_allowance']
        for d in result.payload['slot_resource_details'])
    data = fixture(counter)
    data[3]['resources']['maximum_token_reservations'] = 1
    with pytest.raises(ResearchError, match='resource_token_limit'):
        prepare(data)


def test_prior_exposure_unknown_is_a_stratum_not_a_reference_gap(counter):
    data = fixture(counter)
    frames = subject.original
    from final_validation_frame import build_probability_frame
    from final_validation_design import pair_count
    frame = build_probability_frame(data[0].index, ({'pair_rank': rank, 'candidate_exposure': 'unknown',
        'prior_exposure': 'unknown', 'cosine_band': None} for rank in range(pair_count(len(data[2])))),
        derivation_binding=digest('synthetic-unknown-exposure'))
    seeds = {'primary': 'synthetic-primary', 'qc': 'synthetic-qc', 'diagnostic': 'synthetic-diagnostic'}
    schedule = frames.schedules.assemble_schedule(frame, seeds=seeds, seed_binding={
        'record': digest('synthetic-seeds'), 'artifact': digest(frames.schedules.seed_payload(seeds))})
    result = prepare((frame, schedule, data[2], data[3]))
    assert result.payload['resource_census']['fresh_potential_invocations'] == len(result.tasks)
    assert all(t['history']['state'] == 'fresh_unattempted' for t in result.tasks)
    assert not result.payload['derived_history_inventory']['global_gap']


def test_unselected_full_input_cannot_be_omitted_or_changed(counter):
    data = fixture(counter, 90)
    selected = {i for t in data[1].manifest['initial_prefix']['tasks']
        for i in subject.pair_from_rank(90, t['pair_rank'])}
    untouched = next(i for i in range(90) if i not in selected)
    data[2][untouched]['body'] += ' changed full tail'
    with pytest.raises(ResearchError, match='document_hash_binding'):
        prepare(data)
