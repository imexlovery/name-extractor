import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import extract as rules
from evaluate import category, check_source, evaluate, evaluate_unseen, read_reference
from validate import check


class GenericRules(unittest.TestCase):
    def test_title_forms_and_character_counts(self):
        for title, names, length in [
            ('关于核准梁晓芝任职资格的批复', ['梁晓芝'], 3),
            ('关于秦铖、蒲涛任职资格的批复', ['秦铖', '蒲涛'], 4),
            ('关于GohYihYee（吴子宇）任职资格的批复', ['GohYihYee（吴子宇）'], 12),
            ('关于陈料挥（CHEN,LIAO-HUEI）任职资格的批复', ['陈料挥（CHEN,LIAO-HUEI）'], 15),
            ('关于𠮷田松彦一人任职资格的批复', ['𠮷田松彦'], 4),
        ]:
            with self.subTest(title=title):
                result = rules.extract(title)
                self.assertEqual((result['status'], result['names']), ('names', names))
                self.assertEqual(sum(map(rules.name_length, names)), length)
                self.assertEqual(check(title, result)['failures'], [])

    def test_unfamiliar_institution_suffix_and_unknown_prefix(self):
        after = rules.extract('关于虚构新域银行股份有限公司李华董事任职资格的批复')
        self.assertEqual((after['status'], after['names']), ('names', ['李华']))
        before = rules.extract('关于李华虚构新域银行股份有限公司董事任职资格的批复')
        self.assertEqual(before['status'], 'uncertain')
        # An explicit institution type remains a rule input, without a company dictionary.
        result = rules.extract('关于李华村镇银行董事任职资格的批复')
        self.assertEqual((result['status'], result['names']), ('names', ['李华']))

    def test_regulatory_template_consumes_the_whole_title(self):
        for subject in ['银保监会', '中国银行保险监督管理委员会', '金融监督管理总局']:
            title = subject + '开展银行保险机构股权专项整治'
            self.assertEqual(rules.extract(title)['status'], 'no_name')
            self.assertNotEqual(rules.extract(title + '张明发言')['status'], 'no_name')

    def test_department_words_do_not_shorten_the_institution_span(self):
        for title, name in [
            ('关于核准张欣四川省唯品富邦消费金融有限公司财务总监任职资格的批复', '张欣'),
            ('关于核准袁庆江西永新农村商业银行股份有限公司财务会计部总经理任职资格的批复', '袁庆'),
            ('关于农行西藏分行马全发同志任职资格的批复', '马全发'),
        ]:
            result = rules.extract(title)
            self.assertEqual((result['status'], result['names']), ('names', [name]))

    def test_extractor_runs_alone_without_resources_or_references(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'extract.py'
            shutil.copyfile(Path(rules.__file__), path)
            code = ("import importlib.util,json; "
                    "s=importlib.util.spec_from_file_location('alone'," + repr(str(path)) + "); "
                    "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                    "print(json.dumps(m.extract('关于李华任职资格的批复'),ensure_ascii=False))")
            result = subprocess.run([sys.executable, '-I', '-B', '-c', code], cwd=directory,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['names'], ['李华'])
            self.assertEqual([item.name for item in Path(directory).iterdir()], ['extract.py'])


class LightweightEvaluation(unittest.TestCase):
    def record(self, row=2, title='关于李华任职资格的批复', status='names', names=None):
        return dict(row=row, title=title, status=status,
                    names=['李华'] if names is None else names)

    def test_reference_unresolved_never_counts_as_correct(self):
        reference = self.record(status='uncertain', names=[])
        result = dict(status='uncertain', names=[])
        self.assertEqual(category(result, reference), 'unresolved_reference')
        self.assertEqual(category(result, reference, ['invalid']), 'invalid_script')

    def test_original_rows_weight_repeated_titles(self):
        records = [self.record(row=2), self.record(row=3),
                   self.record(row=4, status='no_name', names=[])]
        calls = []
        extractor = SimpleNamespace(VERSION='test', name_length=rules.name_length)
        def extract(title):
            calls.append(title)
            return dict(status='names', names=['李华'], rule='test', note='')
        extractor.extract = extract
        summary, errors, _ = evaluate(records, extractor)
        self.assertEqual(summary['source_rows'], 3)
        self.assertEqual(summary['unique_titles'], 1)
        self.assertEqual(summary['categories_rows'], {'match': 2, 'count_or_split_difference': 1})
        self.assertEqual(summary['reference_agreement'], 2 / 3)
        self.assertEqual(len(errors), 1)
        self.assertEqual(len(calls), 1)

    def test_references_cannot_backfill_production(self):
        summary, _, production = evaluate([self.record(names=['另一个答案'])], rules)
        self.assertEqual(summary['confirmed_matching_rows'], 0)
        self.assertEqual(production, [dict(row=2, name='李华', length=2)])

    def test_abstention_stays_blank_even_when_reference_agrees_on_candidate(self):
        record = self.record(title='关于林远张瑞陈琳任职资格的批复', names=['林远张瑞陈琳'])
        summary, _, production = evaluate([record], rules)
        self.assertEqual(summary['categories_rows'], {'script_unresolved_confirmed_reference': 1})
        self.assertEqual(production, [dict(row=2, name=None, length=None)])

    def test_no_name_exports_numeric_zero(self):
        record = self.record(title='关于董事任职资格的批复', status='no_name', names=[])
        summary, _, production = evaluate([record], rules)
        self.assertEqual(summary['categories_rows'], {'match': 1})
        self.assertEqual(production, [dict(row=2, name='', length=0)])

    def test_physical_jsonl_preserves_unicode_line_separator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.jsonl'
            record = self.record(title='关于李华\u2028任职资格的批复')
            path.write_text(json.dumps(record, ensure_ascii=False) + '\n', encoding='utf-8')
            self.assertEqual(read_reference(path), [record])

    def test_empty_and_duplicate_row_references_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.jsonl'
            for text in ['', json.dumps(self.record()) + '\n' + json.dumps(self.record()) + '\n']:
                path.write_text(text)
                with self.assertRaises(ValueError):
                    read_reference(path)

    def test_seen_titles_cannot_be_reported_as_unseen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unseen.jsonl'
            path.write_text(json.dumps(self.record()) + '\n')
            with self.assertRaisesRegex(ValueError, 'overlap'):
                evaluate_unseen(path, [self.record()], rules)

    def test_unseen_scoring_and_unresolved_label_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'unseen.jsonl'
            record = self.record(title='关于周宁任职资格的批复', names=['周宁'])
            path.write_text(json.dumps(record) + '\n')
            summary, _, _ = evaluate_unseen(path, [self.record()], rules)
            self.assertEqual(summary['reference_agreement'], 1)
            path.write_text(json.dumps(dict(record, status='uncertain')) + '\n')
            with self.assertRaisesRegex(ValueError, 'resolved'):
                evaluate_unseen(path, [self.record()], rules)

    def test_source_title_and_row_verification(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.xlsx'
            book = Workbook()
            sheet = book.active
            sheet.title = 'Sheet1'
            sheet.append(['标题'])
            sheet.append(['关于李华任职资格的批复'])
            book.save(path)
            book.close()
            self.assertEqual(check_source(path, [self.record()])['original_titles_verified'], 1)
            with self.assertRaisesRegex(ValueError, 'differs'):
                check_source(path, [self.record(title='关于周宁任职资格的批复')])


if __name__ == '__main__':
    unittest.main()
