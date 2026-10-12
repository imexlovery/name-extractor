"""Compare r56, human feedback and every saved rule trial; no runtime backfill."""
from collections import Counter
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from pilot import read_jsonl, write_json, write_jsonl
from extract import VERSION
from full import comparison_state, labels
from validate import check

WORK = Path(__file__).resolve().parent


def surname_candidates(fragment, resource):
    """Shape hints only. The entire fragment always remains a competing option."""
    surnames = resource['single'] + resource['compound']
    def parts(start):
        if start == len(fragment):
            return [[]]
        results = []
        for surname in surnames:
            if fragment.startswith(surname, start):
                for length in (len(surname) + 1, len(surname) + 2):
                    end = start + length
                    if end <= len(fragment):
                        results.extend([[fragment[start:end]] + tail for tail in parts(end)])
        return results
    return [list(v) for v in sorted({tuple(p) for p in parts(0) if len(p) > 1})]


def title_reason(item):
    result = item['result']
    if result['status'] == 'names':
        if result.get('conjoined_names') or result['rule'] == 'complete_person_clauses':
            return '完整姓名槽位中括号外连接词/名单分项引出全部主体；各侧不含机构岗位残片，未按长度或姓氏创建边界'
        if result['rule'] == 'person_before_generic_bank':
            return '姓名候选＋完整银行类型＋已消费完的明确岗位；没有完整机构锚点竞争，固定数据人工候选一致；泛称不能保证未来陌生机构泛化'
        return '完整机构锚点先于类型后缀，机构前候选与完整岗位相配；采用可复用机构资源而非标题姓名答案'
    note = result['note']
    if '长连续汉字' in note or '连接词关系' in note:
        return '候选范围已保留；长姓名与缺分隔的名单均可能落在该槽位，当前通用规则尚不能判定人数。仅有长度风险，不声称已证明标题不可判断'
    if '外文括号外' in note:
        return '完整外文候选保留：逗号可能表示同人姓/名顺序，也可能分隔多人；标题无人数或分别任职信息，正文核验不是通用生产条件'
    if '任字' in note or '任可能' in note:
        return '机构/岗位前的任既可作姓名末字，也可作任职动词；标题无显式分隔，人工更新答案另存不回填'
    if '泛称金融机构' in note:
        return '机构前片段可能是王菲米兰完整姓名，也可能含米兰地区修饰；泛称未证明姓名与地点的边界'
    return note


def main():
    data = read_jsonl(WORK / f'script-{VERSION}.jsonl')
    baseline = {v['row']: v for v in read_jsonl(ROOT / 'validation/0.5.1/script-r56.jsonl')}
    feedback = {v['row']: v for v in read_jsonl(WORK / 'human-review.jsonl')}
    changes = read_jsonl(WORK / f'changes-from-r56-{VERSION}.jsonl')
    resource = json.loads((WORK / 'surname-candidates-resource.json').read_text())
    comparisons = []
    for item in data:
        if item['row'] not in feedback and item['row'] not in {v['row'] for v in changes}:
            continue
        human = feedback.get(item['row'])
        confirmed = (human or {}).get('user_confirmed_correction')
        expected = confirmed or (human or {}).get('conversation_correction') or (human or {}).get('updated_judgment')
        result = item['result']
        matches = expected is not None and (result['status'], result['names']) == (expected['status'], expected['names'])
        candidates = surname_candidates(result['names'][0], resource) if result['status'] == 'uncertain' and len(result['names']) == 1 and all('\u4e00' <= c <= '\u9fff' for c in result['names'][0]) else []
        title_supported_correction = item['row'] == 25395 and result['names'] == ['肖云瑞', '钱锦']
        comparisons.append(dict(row=item['row'], rows=item['rows'], title=item['title'],
            before=baseline[item['row']]['result'], result=result, human_expected=expected,
            matches_existing_human_judgment=matches, title_reason=title_reason(item),
            surname_split_candidates=candidates, whole_candidate_preserved=True,
            surname_candidates_confirm_output=False, reviewed_by='Codex标题结构及既有人工反馈比较',
            post_change_human_review_complete=bool(confirmed),
            title_supported_human_correction=('用户已确认钱锦，人工初答误把理事首字带入姓名；原C值保留，更正独立记录' if title_supported_correction else None),
            review_state='支持确定结果' if result['status'] == 'names' and (matches or title_supported_correction) else '继续未决' if result['status'] == 'uncertain' else '需要人工判断'))
    write_jsonl(WORK / 'human-comparison.jsonl', comparisons)
    by_row = {v['row']: v for v in comparisons}
    review = [dict(v, **{k: by_row[v['row']][k] for k in ('review_state', 'title_reason', 'matches_existing_human_judgment', 'post_change_human_review_complete')}) for v in changes]
    write_jsonl(WORK / f'change-review-{VERSION}.jsonl', review)
    known_errors = [v for v in changes if v['result']['status'] == 'names' and by_row[v['row']]['review_state'] != '支持确定结果']
    if known_errors:
        raise ValueError(f'Unreviewed or conflicting determinate changes: {[v["row"] for v in known_errors]}')
    with (WORK / '变化标题-人工复核.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['完整标题', 'r56状态', '当前状态', '脚本候选（未决不写入Excel）', '已有人工更新判断', '标题依据', '变化后人工结论（待填写）', '原Excel行号'])
        for v in review:
            human = by_row[v['row']]['human_expected']
            writer.writerow([v['title'], v['before']['status'], v['result']['status'], '；'.join(v['result']['names']), '；'.join(human['names']) if human else '', v['title_reason'], '用户已确认：肖云瑞；钱锦（2026-10-12）' if by_row[v['row']]['post_change_human_review_complete'] else '', '；'.join(map(str, v['rows']))])
    write_jsonl(WORK / 'remaining-unresolved.jsonl', [v for v in comparisons if v['result']['status'] == 'uncertain'])
    rounds = []
    for version in ('r57', 'r58', 'r59', 'r60'):
        round_data = read_jsonl(WORK / f'changes-from-r56-{version}.jsonl')
        rounds.append(dict(version=version, changed_titles=len(round_data), changed_rows=sum(len(v['rows']) for v in round_data),
                           accepted=version != 'r58', observed_error_rows=[25132] if version == 'r58' else [],
                           note='明确一人且片段重复时保留整个连接表达；真实输出相对r59无变化' if version == 'r60' else 'r58误拆带外文别名的坂内和隆；r59修复并全量复验' if version in ('r58', 'r59') else '机构类型与7个完整机构补充'))
    solved = [v for v in changes if v['before']['status'] == 'uncertain' and v['result']['status'] == 'names']
    frozen_changes = [v for v in changes if v['row'] in {r['row'] for r in read_jsonl(WORK / 'random-human-frozen.jsonl')}]
    a, b = labels('a'), labels('b')
    summary = dict(version=VERSION, release_version='0.6.0', rounds=rounds,
        unique_titles=len(data), mapped_rows=sum(len(v['rows']) for v in data),
        status_titles=dict(Counter(v['result']['status'] for v in data)),
        status_rows={status:sum(len(v['rows']) for v in data if v['result']['status'] == status) for status in ('names', 'no_name', 'uncertain')},
        hard_failure_titles=sum(bool(check(v['title'], v['result'])['failures']) for v in data),
        supported_solutions_titles=len(solved), supported_solutions_rows=sum(len(v['rows']) for v in solved),
        solutions_evidence='标题结构检查＋已有人工反馈一致；变化后人工复核尚未完成，非独立准确率真值',
        solutions_matching_human_titles=sum(by_row[v['row']]['matches_existing_human_judgment'] for v in solved),
        solutions_matching_human_rows=sum(len(v['rows']) for v in solved if by_row[v['row']]['matches_existing_human_judgment']),
        title_supported_human_corrections_rows=[25395],
        corrected_original_errors_rows=0, known_new_errors_remaining_rows=len(known_errors),
        previously_determinate_changes=sum(v['before']['status'] != 'uncertain' for v in changes),
        post_change_human_review_complete=False, random_sample_changes=len(frozen_changes),
        all_human_review_complete=False, true_accuracy=None,
        comparison_titles=dict(Counter(comparison_state(v, a.get(v['row']), b.get(v['row'])) for v in data)),
        surname_experiment=dict(production_enabled=False, resource='surname-candidates-resource.json',
            uncertain_titles_with_candidates=sum(bool(v['surname_split_candidates']) for v in comparisons),
            conclusion='整段始终是竞争候选，唯一词表切分不证明人数；不进入生产'),
        long_and_foreign_experiment=dict(production_relaxation=False,
            conclusion='完整槽位保留；无可靠通用单人数条件，不用正文答案放行。显式人数现有路径继续有效'),
        human_review_scope=json.loads((WORK / 'human-review-scope.json').read_text()))
    write_json(WORK / 'stage-report.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
