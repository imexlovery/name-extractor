#!/usr/bin/env python3
"""r65 institution-anchor ablation: original vs removing learned anchor JSON.

Run from the root of imexlovery/name-extractor:
    python /path/to/name_extractor_ablation.py
or
    python /path/to/name_extractor_ablation.py --repo /path/to/name-extractor

Only reads source repo. Writes new ablation output into validation/0.7.0/ablation-no-learned-institutions/.
Does not alter production scripts, dictionaries, Excel, or original validation files.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import time


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact(result: dict) -> tuple[str, tuple[str, ...]]:
    return result.get('status', ''), tuple(result.get('names', []))


def category(result, reference, failures=()):
    if failures:
        return 'invalid_script'
    if reference[0] not in ('names', 'no_name'):
        return 'unresolved_reference'
    if result == reference:
        return 'match'
    if result[0] == 'uncertain':
        return 'script_unresolved_confirmed_reference'
    if len(result[1]) != len(reference[1]):
        return 'count_or_split_difference'
    return 'name_or_status_difference'


def main():
    parser = argparse.ArgumentParser(description='Ablate learned institution anchors, without changing repo')
    parser.add_argument('--repo', type=Path, default=Path.cwd(), help='name-extractor repo root')
    parser.add_argument('--output', type=Path, default=None, help='destination for report (default within validation/0.7.0)')
    args = parser.parse_args()
    root = args.repo.resolve()
    scripts = root / 'scripts'
    snapshot = root / 'validation/0.7.0/script-r65.jsonl'
    reference_path = root / 'validation/0.7.0/final-acceptance/fixed-row-reference.jsonl'
    source = scripts / 'extract.py'
    anchor = scripts / 'institution_anchors_r65.json'
    ambiguity = scripts / 'title_ambiguities_r61.json'
    manifest_path = reference_path.with_name('reference-manifest.json')
    validator_path = scripts / 'validate.py'
    for path in (source, anchor, ambiguity, snapshot, reference_path, manifest_path, validator_path):
        if not path.is_file():
            parser.error(f'Missing required r65 file: {path}')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['version'] != 'v3' or manifest['row_count'] != 52146:
        parser.error('Expected frozen v3 reference with 52146 rows')
    validator = load_module(validator_path, 'ablation_validator')
    baseline_anchors = json.loads(anchor.read_text(encoding='utf-8'))
    if not isinstance(baseline_anchors, list) or len(baseline_anchors) < 1000:
        parser.error('Expected large learned anchor list; this may not be the r65 repo')

    outdir = (args.output or (root / 'validation/0.7.0/ablation-no-learned-institutions')).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    reference = {}
    with reference_path.open(encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                item = json.loads(line)
                if item['excel_row'] in reference or item.get('reference_version') != 'v3':
                    raise RuntimeError('Duplicate row or non-v3 fixed reference')
                reference[item['excel_row']] = compact(item)
    if len(reference) != 52146:
        raise RuntimeError(f'Expected 52146 fixed-v3 references, got {len(reference)}')

    baseline = load_module(source, 'r65_original_extract')
    if getattr(baseline, 'VERSION', None) != 'r65':
        parser.error(f"Expected r65, got {getattr(baseline, 'VERSION', 'unknown')}")

    with tempfile.TemporaryDirectory(prefix='no_anchor_r65_') as work:
        tmp = Path(work)
        shutil.copyfile(source, tmp / source.name)
        shutil.copyfile(ambiguity, tmp / ambiguity.name)
        (tmp / anchor.name).write_text('[]\n', encoding='utf-8')
        modified = load_module(tmp / source.name, 'r65_without_learned_anchors')
        if getattr(modified, 'VERSION', None) != baseline.VERSION:
            raise RuntimeError('Experiment unexpectedly changed algorithm version')

        summary = {
            'comparison': 'r65 original versus r65 without learned institution_anchors_r65.json',
            'learned_anchors_removed': len(baseline_anchors),
            'original_runtime_anchors': len(baseline._INSTITUTION_STARTS),
            'retained_runtime_anchors': len(modified._INSTITUTION_STARTS),
            'title_ambiguity_resource_retained': ambiguity.name,
            'builtin_anchors_retained': True,
            'generic_institution_suffix_rules_retained': True,
            'source_snapshot': str(snapshot.relative_to(root)),
        }
        baseline_status, ablated_status = Counter(), Counter()
        baseline_title_status, ablated_title_status = Counter(), Counter()
        baseline_categories, ablated_categories = Counter(), Counter()
        contract_failure_titles = Counter()
        transitions, change_types = Counter(), Counter()
        seen_rows, seen_titles = set(), set()
        examples = []
        num_titles = num_rows = num_changed_titles = num_changed_rows = 0
        frozen_mismatches = []
        baseline_match_rows = ablated_match_rows = 0
        confirmed_reference_rows = 0
        changed_name_titles = changed_name_rows = 0
        reference_effect = Counter()
        all_changes_path = outdir / 'changed_titles.csv'
        start = time.perf_counter()
        with snapshot.open(encoding='utf-8') as handle, all_changes_path.open('w', encoding='utf-8-sig', newline='') as file, (outdir / 'changed_rows.jsonl').open('w', encoding='utf-8') as details:
            writer = csv.writer(file)
            writer.writerow(['原始首行号', '原始行数', '原标题', '原版状态', '原版姓名', '去词库状态', '去词库姓名', '变化类型'])
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                title = item['title']
                rows = item['rows']
                if title in seen_titles or len(set(rows)) != len(rows) or seen_rows.intersection(rows):
                    raise RuntimeError('Duplicate title or original row in snapshot')
                seen_titles.add(title)
                seen_rows.update(rows)
                weight = len(rows)
                recorded = compact(item['result'])
                original_result = baseline.extract(title)
                original_result.update(length=sum(map(baseline.name_length, original_result['names'])), extracted_name='；'.join(original_result['names']))
                original = compact(original_result)
                if recorded != original or any(item['result'][key] != original_result[key] for key in ('length', 'extracted_name')):
                    frozen_mismatches.append((item['row'], title, recorded, original))
                    if len(frozen_mismatches) >= 10:
                        raise RuntimeError('Original source no longer reproduces frozen r65 snapshot. '
                                           f'First mismatches: {frozen_mismatches[:3]}')
                    continue
                ablated_result = modified.extract(title)
                ablated_result.update(length=sum(map(modified.name_length, ablated_result['names'])), extracted_name='；'.join(ablated_result['names']))
                no_anchors = compact(ablated_result)
                a_failures = validator.check(title, original_result)['failures']
                b_failures = validator.check(title, ablated_result)['failures']
                contract_failure_titles['original'] += bool(a_failures)
                contract_failure_titles['without_anchors'] += bool(b_failures)
                num_titles += 1
                num_rows += weight
                baseline_status[original[0]] += weight
                ablated_status[no_anchors[0]] += weight
                baseline_title_status[original[0]] += 1
                ablated_title_status[no_anchors[0]] += 1
                for row in rows:
                    ref = reference[row]
                    determined = ref[0] in ('names', 'no_name')
                    a_category = category(original, ref, a_failures)
                    b_category = category(no_anchors, ref, b_failures)
                    baseline_categories[a_category] += 1
                    ablated_categories[b_category] += 1
                    a_good = a_category == 'match'
                    b_good = b_category == 'match'
                    confirmed_reference_rows += int(determined)
                    baseline_match_rows += int(a_good)
                    ablated_match_rows += int(b_good)
                    if original != no_anchors:
                        details.write(json.dumps(dict(excel_row=row, title=title, original=original_result,
                            without_anchors=ablated_result, reference={'status': ref[0], 'names': ref[1]},
                            original_category=a_category, without_anchors_category=b_category,
                            contract_failures=b_failures), ensure_ascii=False) + '\n')
                    if a_good and not b_good: reference_effect['previously_matching_now_mismatch'] += 1
                    if b_good and not a_good: reference_effect['previously_mismatching_now_match'] += 1
                transitions[f'{original[0]} -> {no_anchors[0]}'] += weight
                if no_anchors == original:
                    continue
                num_changed_titles += 1
                num_changed_rows += weight
                if original[1] != no_anchors[1]:
                    changed_name_titles += 1
                    changed_name_rows += weight
                if original[0] != no_anchors[0]:
                    kind = f'{original[0]} -> {no_anchors[0]}'
                else:
                    kind = 'same_status_different_names'
                change_types[kind] += weight
                writer.writerow([item['row'], weight, title, original[0], '；'.join(original[1]),
                                 no_anchors[0], '；'.join(no_anchors[1]), kind])
                if len(examples) < 20:
                    examples.append({'row':item['row'], 'title':title, 'before':original, 'after':no_anchors,'rows':weight})

        if frozen_mismatches:
            raise RuntimeError(f'Frozen r65 snapshot has {len(frozen_mismatches)} mismatches: {frozen_mismatches[:3]}')
        if (num_titles, num_rows) != (46760, 52146):
            raise RuntimeError(f'Unexpected input size: {(num_titles,num_rows)}; expected (46760,52146)')
        if seen_rows != set(reference):
            raise RuntimeError('Original row coverage differs from fixed reference')
        summary.update({
            'unique_titles':num_titles,
            'original_rows':num_rows,
            'original_status_rows':dict(baseline_status),
            'without_learned_anchors_status_rows':dict(ablated_status),
            'original_status_titles':dict(baseline_title_status),
            'without_learned_anchors_status_titles':dict(ablated_title_status),
            'contract_failure_titles':dict(contract_failure_titles),
            'original_reference_categories_rows':dict(baseline_categories),
            'without_anchors_reference_categories_rows':dict(ablated_categories),
            'changed_unique_titles':num_changed_titles,
            'changed_original_rows':num_changed_rows,
            'changed_name_list_titles':changed_name_titles,
            'changed_name_list_rows':changed_name_rows,
            'unchanged_original_rows':num_rows - num_changed_rows,
            'status_transitions_original_rows':dict(transitions),
            'change_types_original_rows':dict(change_types),
            'fixed_v3_reference':{
                'determinate_rows':confirmed_reference_rows,
                'original_match_rows':baseline_match_rows,
                'original_agreement_all_rows':round(baseline_match_rows / num_rows, 8),
                'without_anchors_match_rows':ablated_match_rows,
                'without_anchors_agreement_all_rows':round(ablated_match_rows / num_rows, 8),
                'original_agreement_confirmed_rows':baseline_match_rows / confirmed_reference_rows,
                'without_anchors_agreement_confirmed_rows':ablated_match_rows / confirmed_reference_rows,
                'delta_percentage_points':round((ablated_match_rows-baseline_match_rows)/num_rows*100, 4),
                'impact_on_reference':dict(reference_effect),
                'not_a_true_accuracy_estimate':True,
            },
            'examples':examples,
            'seconds':round(time.perf_counter()-start, 2),
            'true_accuracy':None,
            'interpretation_note':'Measures learned-resource dependence on the existing corpus against fixed v3 references. It is neither a true-accuracy estimate nor an unseen-data generalization test; built-in specific institutions and title ambiguities remain.'
        })
        if baseline_match_rows != 52067:
            raise RuntimeError(f'Expected current r65-v3 agreement 52067 rows, got {baseline_match_rows}. Check reference versions.')
        (outdir / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in summary.items() if k not in ('examples',)},ensure_ascii=False,indent=2))
        print(f'\nDetailed differences: {all_changes_path}')
        print(f'Summary: {outdir / "summary.json"}')


if __name__ == '__main__':
    main()
