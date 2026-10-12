import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract import extract
from validate import check


class IncompleteTitlesAndInstitutionLinker(unittest.TestCase):
    def test_incomplete_institution_is_not_confirmed_no_name(self):
        for title in [
            '关于同意民生人寿保险股份有限公司河南分公司',
            '关于同意中原农业保险股份有限公司河南省分公司',
            '关于同意中国人民健康保险股份有限公司新乡中心支公司',
            '关于中国工商银行辽宁省分行',
            '关于同意国元农业保险股份有限公司河南分公司',
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('uncertain', []), title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '关于同意民生人寿保险股份有限公司河南分公司的批复',
            '关于同意民生人寿保险股份有限公司河南分公司开业的批复',
            '关于民生人寿保险股份有限公司河南分公司总经理任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'no_name', title)

    def test_linker_requires_complete_institution_and_consumed_post(self):
        for title, name in [
            ('关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司总经理的批复', '叶建中'),
            ('关于核准杨兴的渤海财产保险股份有限公司乌兰察布市中心支公司总经理的批复', '杨兴'),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', [name]), title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司任职资格的批复',
            '关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司总经理李华任职资格的批复',
        ]:
            self.assertEqual(extract(title)['status'], 'uncertain', title)
        result = extract('关于核准张明的村镇银行总经理任职资格的批复')
        self.assertEqual((result['status'], result['names']), ('uncertain', ['张明的']))
        for title, candidate in [
            ('关于殷熊毅辉任职资格的批复', '殷熊毅辉'),
            ('关于通辽金谷村镇银行股份有限公司白玉娥李毅昕高级管理人员任职资格的批复', '白玉娥李毅昕'),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('uncertain', [candidate]), title)

    def test_ambiguous_linkers_keep_both_interpretations(self):
        for institution in ['村镇银行', '农村商业银行', '东宁农商行']:
            for candidate in ['张明任', '何子任']:
                title = f'关于核准{candidate}{institution}董事任职资格的批复'
                result = extract(title)
                self.assertEqual((result['status'], result['names']), ('uncertain', [candidate]), title)
                self.assertEqual([v['names'] for v in result['candidate_interpretations']],
                                 [[candidate], [candidate[:-1]]], title)
                self.assertEqual(check(title, result)['failures'], [], title)
        for institution in ['村镇银行', '农村商业银行']:
            title = f'关于核准张明的{institution}总经理任职资格的批复'
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('uncertain', ['张明的']), title)
            self.assertEqual([v['names'] for v in result['candidate_interpretations']],
                             [['张明的'], ['张明']], title)
        for suffix, expected in [('任职资格', ('uncertain', ['张明的'])),
                                 ('总经理李华任职资格', ('uncertain', ['张明的'])),
                                 ('总经理任职资格', ('names', ['张明']))]:
            title = f'关于核准张明的东宁农商行{suffix}的批复'
            result = extract(title)
            self.assertEqual((result['status'], result['names']), expected, title)
            self.assertEqual(check(title, result)['failures'], [], title)

    def test_ambiguous_honorific_and_real_appointment_candidate(self):
        for title, candidates in [
            ('关于刘任深圳市南华保险经纪有限公司副总经理任职资格的批复', ['刘任', '刘']),
            ('关于陈同志任职资格的批复', ['陈同志', '陈']),
            ('关于陈先生任职资格的批复', ['陈先生', '陈']),
            ('关于陈女士任职资格的批复', ['陈女士', '陈']),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('uncertain', [candidates[0]]), title)
            self.assertEqual([v['names'] for v in result['candidate_interpretations']],
                             [[name] for name in candidates], title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title, name in [
            ('关于张明同志任职资格的批复', '张明'),
            ('关于申玉林任东宁农商行财务会计部总经理的批复', '申玉林'),
            ('关于核准叶建中的中国人民财产保险股份有限公司乌兰察布市分公司总经理的批复', '叶建中'),
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', [name]), title)


if __name__ == '__main__':
    unittest.main()
