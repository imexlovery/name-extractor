"""Reproduce frozen structural comparisons; labels never feed the extractor."""
import importlib.util
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def evaluate(prefix, a_file, b_file, versions):
    a = read(WORK/a_file)
    b = {v['id']: v for v in read(WORK/b_file)}
    summaries = {}
    for version in versions:
        spec = importlib.util.spec_from_file_location('frozen_' + version, WORK/f'extract-{version}.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = []
        for av in a:
            bv = b[av['id']]
            result = module.extract(av['title'])
            agreement = (av['names'], av['status']) == (bv['names'], bv['status'])
            match = result['status'] == av['status'] and (av['status'] == 'uncertain' or result['names'] == av['names'])
            output.append(dict(id=av['id'], title=av['title'], script=result, ai_a=av, ai_b=bv,
                               reference_agreement=agreement, match_to_a=match))
        (WORK/f'{prefix}-{version}.jsonl').write_text(''.join(json.dumps(v, ensure_ascii=False)+'\n' for v in output))
        agreed = [v for v in output if v['reference_agreement']]
        summaries[version] = dict(total=len(output), reference_agreement=len(agreed),
            matched_agreed=sum(v['match_to_a'] for v in agreed),
            determinate_mismatches=[v['id'] for v in agreed if not v['match_to_a'] and v['script']['status'] != 'uncertain'],
            conservative_abstentions=[v['id'] for v in agreed if not v['match_to_a'] and v['script']['status'] == 'uncertain'],
            reference_disagreements=[v['id'] for v in output if not v['reference_agreement']])
    return summaries

if __name__ == '__main__':
    summary = {
        'development': evaluate('structure-development', 'structure-holdout-reference.jsonl', 'structure-holdout-reference-b.jsonl', ['r47','r48','r51']),
        'fresh_then_revealed': evaluate('structure-fresh', 'structure-fresh-reference-a.jsonl', 'structure-fresh-reference-b.jsonl', ['r48','r50','r51']),
        'final_then_revealed': evaluate('final-structure', 'final-structure-reference-a.jsonl', 'final-structure-reference-b.jsonl', ['r50','r51']),
        'interpretation': 'All sets are synthetic combinations. Once revealed they are development regressions, not unseen proof. Uncertain candidate fragments are not confirmed names. Same-model independent AI contexts are not human ground truth.'
    }
    write(WORK/'structure-evaluation-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
