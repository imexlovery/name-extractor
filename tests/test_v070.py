import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from extract import extract
from validate import check


class IncompleteTitlesAndInstitutionLinker(unittest.TestCase):
    def test_adjudicated_full_institution_boundaries(self):
        cases = {
            '关于冯毅健安金汇保险销售服务有限公司总经理任职资格的批复': ['冯毅'],
            '关于核准袁军成都江堰金都村镇银行有限责任公司董事任职资格的批复': ['袁军成'],
            '中国银保监会中山监管分局于高明任职资格的批复': ['高明'],
            '关于于高明任职资格的批复': ['于高明'],
        }
        for title, names in cases.items():
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('names', names), title)
            self.assertEqual(check(title, result)['failures'], [], title)

    def test_complete_public_matters_without_named_people(self):
        for title in [
            '银保监会持续开展银行保险机构股权和关联交易专项整治不断提升公司治理质效',
            '关于江苏省金融学会第十一届理事会届中变更负责人的公示',
            '关于中国银行保险监督管理委员会推进银行保险机构股权专项整治进一步提高公司治理水平',
            '关于浙江省金融学会第十二届理事会变更负责人的公示',
        ]:
            result = extract(title)
            self.assertEqual((result['status'], result['names']), ('no_name', []), title)
            self.assertEqual(check(title, result)['failures'], [], title)

    def test_public_matters_do_not_hide_named_or_truncated_subjects(self):
        for title in [
            '张明在银保监会开展银行保险机构股权专项整治会议上发言',
            '银保监会持续开展银行保险机构股权和关联交易专项整治张明提出不断提升公司治理质效',
            '关于江苏省金融学会第十一届理事会届中变更负责人张明的公示',
            '关于江苏省金融学会第十一届理事会届中变更负责人的公示并核准李华任职资格的批复',
        ]:
            result = extract(title)
            self.assertNotEqual(result['status'], 'no_name', title)
            self.assertEqual(check(title, result)['failures'], [], title)
        for title in [
            '银保监会持续开展银行保险机构',
            '关于江苏省金融学会第十一届理事会届中变更负责人',
        ]:
            result = extract(title)
            self.assertEqual(result['status'], 'uncertain', title)
            self.assertEqual(check(title, result)['failures'], [], title)
        result = extract('关于加强张明同志任职资格管理的通知')
        self.assertEqual((result['status'], result['names']), ('names', ['张明']))

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
