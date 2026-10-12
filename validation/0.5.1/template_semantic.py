"""Select new title-only blind reviews from the frozen missing-reference pool.

Offline sampling only. Slots are sampling features, never semantic labels.
"""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import re
import sys

from structure_audit import DIRECT

WORK = Path(__file__).resolve().parent
OUT = WORK / 'template-semantic'
SEED = 2026101202
RARE_LIMIT = 12
BOUNDARY = set('等人位名同志董理事高管任资格批复核准意和及与')
CONNECTORS = set('等人位名和及与')


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def save(name, values):
    (OUT / name).write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def prepare():
    data = [v for v in read(WORK / 'audit-r56.jsonl') if v['comparison_state'] == 'missing_reference']
    strata = defaultdict(list)
    chars = Counter()
    for v in data:
        match = DIRECT.fullmatch(v['title'])
        if not match:
            raise ValueError(f"Existing direct-template population changed: {v['row']}")
        v['slot'] = match['subject']
        v['template'] = v['title'][:match.start('subject')] + '<姓名槽位>' + v['title'][match.end('subject'):]
        strata[v['template']].append(v)
        chars.update(set(v['slot']))
    selected = {}
    reasons = defaultdict(set)

    def add(v, reason):
        selected[v['row']] = v
        reasons[v['row']].add(reason)

    rng = random.Random(SEED)
    statistics = []
    for template, group in sorted(strata.items(), key=lambda x: (len(x[1]), x[0])):
        group.sort(key=lambda v: v['row'])
        features = defaultdict(list)
        for v in group:
            slot = v['slot']
            features[f'length:{len(slot)}'].append(v)
            for position, ch in (('first', slot[0]), ('last', slot[-1])):
                if ch in BOUNDARY:
                    features[f'boundary:{position}:{ch}'].append(v)
            if any(chars[ch] <= 2 for ch in slot):
                features['rare_character_title_frequency_le_2'].append(v)
            # Any actual list/omission-like character is reviewed in full.
            if set(slot) & CONNECTORS:
                add(v, 'connector_or_count_character')
            if re.search(r'同志|董事|理事|高管|任职|资格|核准|批复|同意', slot):
                add(v, 'whole_grammar_token_in_slot')
        if len(group) <= RARE_LIMIT:
            for v in group:
                add(v, 'rare_template_census')
        else:
            # Sample grows with template frequency; no preset global total.
            for v in rng.sample(group, math.ceil(math.log2(len(group) + 1))):
                add(v, 'seeded_random_within_template')
            for feature, candidates in sorted(features.items()):
                add(rng.choice(candidates), feature)
        slots = [v['slot'] for v in group]
        selected_group = [v for v in group if v['row'] in selected]
        statistics.append(dict(
            template=template, titles=len(group), mapped_rows=sum(len(v['rows']) for v in group),
            length_distribution=dict(Counter(map(len, slots))),
            slot_character_distribution=dict(Counter(''.join(slots))),
            boundary_character_title_counts={k: len(v) for k, v in features.items() if k.startswith('boundary:')},
            connector_or_count_character_titles=sum(bool(set(s) & CONNECTORS) for s in slots),
            non_han_or_punctuation_titles=sum(bool(re.search(r'[^\u4e00-\u9fff]', s)) for s in slots),
            rare_character_titles=sum(any(chars[c] <= 2 for c in s) for s in slots),
            rarity='rare_census' if len(group) <= RARE_LIMIT else 'sampled',
            selected_titles=len(selected_group), selected_rows=[v['row'] for v in selected_group],
        ))
    OUT.mkdir(exist_ok=True)
    ordered = sorted(selected.values(), key=lambda v: v['row'])
    save('template-statistics.jsonl', statistics)
    save('selection.jsonl', [dict(row=v['row'], rows=v['rows'], title=v['title'], template=v['template'],
                                 slot=v['slot'], reasons=sorted(reasons[v['row']])) for v in ordered])
    blind = [dict(row=v['row'], title=v['title']) for v in ordered]
    rng.shuffle(blind)
    save('blind.jsonl', blind)
    summary = dict(
        baseline_rules='r56', source='audit-r56.jsonl frozen before new labeling', seed=SEED,
        missing_reference_titles=len(data), missing_reference_rows=sum(len(v['rows']) for v in data),
        templates=len(strata), rare_limit=RARE_LIMIT,
        rare_templates=sum(v['rarity'] == 'rare_census' for v in statistics),
        rare_template_titles=sum(v['titles'] for v in statistics if v['rarity'] == 'rare_census'),
        slot_lengths=dict(Counter(len(v['slot']) for v in data)),
        selected_titles=len(ordered), selected_mapped_rows=sum(len(v['rows']) for v in ordered),
        selection_reason_counts=dict(Counter(r for rs in reasons.values() for r in rs)),
        selection_policy='Census templates <=12 titles; ceil(log2(n+1)) seeded random titles per other template; '
                         'cover each length, grammar-character first/last boundary, rare-character presence per template; '
                         'census list/count characters and complete grammar tokens within slots. Overlapping selections deduplicated.',
        boundary_characters=''.join(sorted(BOUNDARY)), connector_count_characters=''.join(sorted(CONNECTORS)),
        rare_character_definition='Character appears in <=2 unique missing-reference titles; not a surname/name rule.',
        non_han_or_punctuation_titles=0,
        interpretation='Purposeful semantic-error search, not a representative accuracy estimate. '
                       'Blind input includes only original title and identifier; no slot, template, risk or script output.'
    )
    (OUT / 'selection-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def evaluate():
    # Reuse the project's independent output contract and historical-reference
    # comparison. Do not run or change extraction and keep its frozen audit.
    sys.path.insert(0, str(WORK.parents[1] / 'scripts'))
    import full
    from validate import check

    blind = read(OUT / 'blind.jsonl')
    selected = {v['row']: v for v in read(OUT / 'selection.jsonl')}
    titles = {v['row']: v['title'] for v in blind}
    channels = {}
    for channel in ('a', 'b'):
        values = read(WORK / 'labels' / f'template-semantic-{channel}-01.jsonl')
        if len(values) != len(titles) or {v['row'] for v in values} != titles.keys():
            raise ValueError(f'{channel}: incomplete or repeated first-answer identifiers')
        for v in values:
            if v['title'] != titles[v['row']] or not v.get('reason') or not v.get('person_count_evidence'):
                raise ValueError(f"{channel}: missing original title or evidence at {v['row']}")
            failures = check(v['title'], v)['failures']
            if failures:
                raise ValueError(f"{channel}: invalid label at {v['row']}: {failures}")
        channels[channel] = {v['row']: v for v in values}
    frozen = read(WORK / 'audit-r56.jsonl')
    population = {v['row']: v for v in frozen}
    comparison = []
    for row, selection in sorted(selected.items()):
        item = population[row]
        if item['comparison_state'] != 'missing_reference':
            raise ValueError(f'Not a new blind title: {row}')
        av, bv = channels['a'][row], channels['b'][row]
        comparison.append(dict(selection, ai_a=av, ai_b=bv, frozen_result=item['result'],
                               first_answers_agree=(av['names'], av['status']) == (bv['names'], bv['status']),
                               comparison_state=full.comparison_state(item, av, bv)))
    save('comparison.jsonl', comparison)
    save('new-ai-references.jsonl', [v for v in comparison if v['comparison_state'] not in
                                   ('disputed_reference', 'invalid_reference', 'missing_reference', 'single_channel')])
    save('new-ai-exclusions.jsonl', [v for v in comparison if v['comparison_state'] in
                                   ('disputed_reference', 'invalid_reference', 'missing_reference', 'single_channel')])
    all_a, all_b = full.labels('a'), full.labels('b')
    all_comparisons = Counter(full.comparison_state(v, all_a.get(v['row']), all_b.get(v['row'])) for v in frozen)
    old_frozen = {v['row']: v for v in read(WORK / 'script-r55.jsonl')}
    changed = sum((v['result']['names'], v['result']['status']) !=
                  (old_frozen[v['row']]['result']['names'], old_frozen[v['row']]['result']['status']) for v in frozen)
    summary = dict(
        rules='r56', selected_titles=len(comparison), selected_mapped_rows=sum(len(v['rows']) for v in comparison),
        templates_covered=len({v['template'] for v in comparison}),
        first_answers_agree=sum(v['first_answers_agree'] for v in comparison),
        first_answer_comparison_states=dict(Counter(v['comparison_state'] for v in comparison)),
        explicit_person_count_evidence={c: sum(v['person_count_evidence'] != 'none' for v in channels[c].values())
                                        for c in ('a', 'b')},
        corrections=0, labels_added_per_channel=len(comparison),
        full_unique_titles=len(frozen), full_mapped_rows=sum(len(v['rows']) for v in frozen),
        full_comparison_states_with_new_labels=dict(all_comparisons),
        ai_coverage_titles_with_new_labels={'a':len(all_a), 'b':len(all_b)},
        script_status_titles=dict(Counter(v['result']['status'] for v in frozen)),
        script_status_rows=dict(Counter(v['result']['status'] for v in frozen for _ in v['rows'])),
        frozen_full_output_contract_failures=sum(bool(check(v['title'], v['result'])['failures']) for v in frozen),
        frozen_output_changes_from_r55=changed, production_changes=0,
        true_accuracy=None, human_review_performed=False,
        evidence_limit='Two independent contexts with the inherited parent model/configuration, not two different models '
                       'or human truth. Selected sample is targeted and cannot estimate population accuracy. '
                       'Existing r56 audit/comparison snapshots retained; updated coverage is reported here.',
    )
    stats = read(OUT / 'template-statistics.jsonl')
    by_template = defaultdict(Counter)
    for v in comparison:
        by_template[v['template']][v['comparison_state']] += 1
    save('template-results.jsonl', [dict(v, comparison_states=dict(by_template[v['template']])) for v in stats])
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'evaluate':
        evaluate()
    else:
        prepare()
