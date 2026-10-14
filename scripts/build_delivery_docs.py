"""Build the Word plan and evidence report from frozen acceptance artifacts.

Run with the bundled document Python runtime, after final_compare and export.
This does not modify extraction rules or write AI answers to Excel.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'validation/0.7.0/final-acceptance'
OUT = ROOT / 'outputs/0.7.0/最终交付'


def read(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load(name):
    return json.loads((WORK / name).read_text())


def replace(paragraph, text):
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in paragraph.runs[1:]:
            run.text = ''
    else:
        paragraph.add_run(text)


def main():
    metrics, manifest = load('final-comparison.json'), load('reference-manifest.json')
    progress, second, third = load('progress.json'), load('second-progress.json'), load('third-progress.json')
    assert progress['ai_review_coverage'] == 1 and progress['invalid_answers'] == 0
    assert second['pending_inputs'] == third['pending_inputs'] == 0
    assert second['invalid_answers'] == third['invalid_answers'] == 0
    version = metrics['script_version']
    excel_check = load('delivery-excel-verification.json')
    differences = read(WORK / 'final-differences.jsonl')
    unresolved = [r for r in differences if r['category'] == 'unresolved_reference']
    rule_file = WORK / 'verified-rule-changes.json'
    rule_changes = json.loads(rule_file.read_text()) if rule_file.exists() else []
    date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y年%m月%d日')
    if metrics['acceptance_passed']:
        state = '本轮验收条件已满足，真实准确率仍按证据边界评估'
    elif metrics['confirmed_difference_rows'] or not metrics['target_reference_agreement_passed']:
        state = '语义验收尚有差异或未达到一致率目标'
    else:
        state = '自动验收材料已完成，等待100条人工确认'
    overview = (f"{state}。全量AI审核覆盖{progress['reviewed_rows']:,}/{progress['source_rows']:,}行，"
        f"固定参考逐行一致率为{metrics['reference_agreement']:.4%}，明确参考差异"
        f"{metrics['confirmed_difference_rows']}行，参考仍无法裁决{metrics['unresolved_reference_rows']}行。"
        f"本轮人工实际检查{metrics['human_reviewed_rows']}/100条，不把AI一致率当作真实准确率。")
    workflow = (f"以0.7.0/r64为冻结基线。52,146原行按标题、完整内容、被许可对象、颁布机构、文号"
        f"五字段精确去重为51,962独立输入，184原行复用完全相同输入的审核结果。每个原始行仍有独立行ID和验收记录。"
        f"首轮只提供原材料；第二轮独立重读{second['required_inputs']}条，不提供首轮或脚本结果；"
        f"第三轮对{third['required_inputs']}条竞争解释进行原文证据裁决，解释排除或不能排除的依据。"
        f"随后对9条姓名机构边界补做独立原文复核，修正6个参考答案；v1及v2更正依据全部保留。"
        f"固定参考版本为{manifest['version']}，正文只辅助AI验收，生产脚本仅依据标题。")
    evidence = ('姓名以原始有序数组比较，逐个核对标题证据位置及正文逐字引用。多人拼接字符串相同不能替代人数和拆分正确。'
        '首答、失败草稿、修订及争议原文保留在独立内部材料中。初始化误读历史的20条草稿已隔离并重新独立审核；'
        '收尾发现的缺批和留在重试目录的更正均按原始ID补齐或校验归并，覆盖以有效逐行文件为准，不以会话自报完成为准。')
    human = ('人工名单固定为60条按年份、地区和标题结构分层随机样本，加40条多人、裁决分歧、无姓名及历史风险样本。'
        '按用户后续选择使用非盲确认表，阅读原标题、必要正文、参考数组及脚本结果后勾选，错误或无法判断填写理由。'
        f"当前正确{metrics['human_status_rows'].get('correct', 0)}条、错误{metrics['human_status_rows'].get('incorrect', 0)}条、"
        f"无法判断{metrics['human_status_rows'].get('uncertain', 0)}条，实际检查{metrics['human_reviewed_rows']}条；AI和UI测试不计人工。"
        '抽检结果只反映这100条，不能夸大为全量真实准确率。')
    integrity = ('正式Excel由生产脚本输出，原表仅新增“提取姓名”“姓名字数”两列。原记录顺序、13原字段、'
        '原值、类型、样式及其他工作表保持一致；确定无姓名空值配数值0，脚本未决两列留空。'
        '固定答案及详细复核记录独立保存，不添加审核工作表，不人工改最终单元格。'
        f"导出器独立回读验证结果保存于delivery-excel-verification.json，验证{excel_check['records_verified']}条记录。")
    limitations = ('各轮审核使用同一gpt-6-luna模型的独立上下文和提示词，可能共享偏差。真实准确率未直接测得。'
        '用户已明确选择保留通用规则、披露剩余差异，不新增逐标题边界例外；76行脚本未决单列于“脚本未决76行.csv”。'
        f"{len(unresolved)}条未决参考逐行列于“剩余不确定性.csv”，不计已确认正确；其余明确差异详见final-differences.jsonl。"
        '剩余不确定性及未完成的人审必须披露，不能用“已100%准确”代替验收结论。')
    runtime_file = WORK / 'runs/current-runtime.json'
    runtime = json.loads(runtime_file.read_text()) if runtime_file.exists() else {}
    usage = runtime.get('cumulative_token_usage', {})
    model = ('审核模型为gpt-6-luna，推理强度xhigh，Fast依据用户界面开启及新会话继承确认；运行元数据未暴露Fast字段。'
        '提示词版本为title-body-blind-v2、title-body-independent-v1、title-body-adjudication-v1。'
        f"可读取审核会话的累计输入token {usage.get('input_tokens', 'unknown')}，缓存输入{usage.get('cached_input_tokens', 'unknown')}，"
        f"输出{usage.get('output_tokens', 'unknown')}；包含失败和重复上下文，推理token已包含在输出内。"
        '使用Codex订阅渠道，未调用新增付费API；货币费用不可读取，记unknown，不换算或记0。')
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / '任职资格批复姓名提取与自动验证方案.docx'
    doc = Document(source)
    history_start = next(i for i, p in enumerate(doc.paragraphs) if p.text == '历史迭代记录')
    historical = [p.text for p in doc.paragraphs[history_start:]]
    tables = [t._tbl.xml for t in doc.tables]
    replace(doc.paragraphs[1], f'{date} 规则{version} 固定参考{manifest["version"]} 验收收尾')
    replace(doc.paragraphs[2], '本方案说明任职资格批复原标题的姓名提取逻辑、边界和实际迭代。'
        f'当前生产规则为{version}，以r64冻结基线及固定参考验收记录为依据。生产只读标题；独立AI验收可结合完整正文判断边界和人数，'
        '但姓名必须在标题逐字定位。历史实验和旧参考保留，不替代本次全量审核。' + overview)
    replace(doc.paragraphs[5], '项目要求.md及用户最新验收方案作为依据。原表保留13字段和全部记录，仅新增姓名与字数两列。'
        '附件范本中的提取职位、多人拆行、单独结果工作表及删除正文均不执行。生产不读正文；正文与元数据仅提供给独立AI审核。')
    replace(doc.paragraphs[6], human)
    replace(doc.paragraphs[13], f'当前机构资源为institution_anchors_{version}.json，含12,277个机构片段及82个基础锚点，合计12,359。'
        '机构锚点只提供标题边界，不保存姓名答案。r65补入健安金汇完整机构，删除误带姓名尾字的成都江堰机构锚点；来源见补证及规则变更记录。')
    replace(doc.paragraphs[25], workflow + '第一、二轮不读取脚本结果或历史答案，第三轮提供两轮竞争解释但仍不提供脚本输出。' + evidence)
    replace(doc.paragraphs[29], '历史122条人工记录仅作交叉验证材料，不计本轮人工抽检。' + human)
    replace(doc.paragraphs[31], 'r64冻结时，第11008行“白玉娥李毅昕”因标题缺少内部切分标记留空。固定参考基于正文确认为两人，'
        '当前通用脚本仍无法可靠切分，列入确定参考差异，不能宣称已修复。用户确认保留通用规则并披露差异，不新增标题边界例外。')
    replace(doc.paragraphs[33], 'r64冻结时姓名51,309行、无姓名758行、未决79行。r65只修复3个确定姓名边界，状态数量不变。' + overview)
    replace(doc.paragraphs[35], workflow)
    replace(doc.paragraphs[36], overview + integrity)
    replace(doc.paragraphs[37], 'r64冻结阶段的历史实验结果：' + doc.paragraphs[37].text)
    replace(doc.paragraphs[39], '使用uv与项目本地.venv。uv run python -B scripts/full.py run保存当前源码和实际资源，'
        '全量运行后用acceptance.py final_compare比较固定参考；full.py export仅从脚本结果导出Excel。'
        '当前r65待验收Excel、Word和报告位于outputs/0.7.0/最终交付；当前独立审核证据在validation/0.7.0/final-acceptance。'
        'r64及此前候选和实验材料保留在原目录，旧人工记录不计本轮人审。')
    anchor = next(p for p in doc.paragraphs if p.text == '历史迭代记录')
    for heading, text in [('全量独立审核与固定参考', evidence), ('验收确认后的规则处理',
        '仅按具体错误及原文证据修正规则，重新跑全量；不为提高一致率添加无证据分支。' +
        ('本次未新增生产规则。' if not rule_changes else ' '.join(c['description'] for c in rule_changes))),
        ('人工确认和剩余不确定性', human + limitations), ('模型运行与复现', model)]:
        anchor.insert_paragraph_before(heading, style='Heading 1')
        anchor.insert_paragraph_before(text, style='Normal')
    word = OUT / f'任职资格批复姓名提取方案-0.7.0-{version}.docx'
    doc.save(word)
    checked = Document(word)
    idx = next(i for i, p in enumerate(checked.paragraphs) if p.text == '历史迭代记录')
    assert [p.text for p in checked.paragraphs[idx:]] == historical
    assert [t._tbl.xml for t in checked.tables] == tables
    report = Document()
    sec = report.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.top_margin = sec.bottom_margin = Inches(.8)
    sec.left_margin = sec.right_margin = Inches(.8)
    for style_name, size in [('Normal', 11), ('Title', 20), ('Heading 1', 14), ('Heading 2', 12)]:
        style = report.styles[style_name]
        style.font.name, style.font.size, style.font.color.rgb = 'Arial Unicode MS', Pt(size), RGBColor(0, 0, 0)
        style.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Hiragino Sans GB')
    report.add_paragraph('任职资格批复姓名提取验收报告', style='Title')
    report.add_paragraph(f'{date} 规则{version} 固定参考{manifest["version"]}')
    report.add_paragraph(overview)
    for heading, text in [('数据范围与独立审核', workflow + evidence), ('数据完整性与格式', integrity),
        ('语义比较与修复', f"已确认匹配{metrics['confirmed_matching_rows']:,}行；全量参考一致率{metrics['reference_agreement']:.4%}，"
         f"仅在确定参考范围的条件一致率{metrics['confirmed_reference_agreement']:.4%}。未决参考仍包含在全量分母，"
         '但不进入正确数。' + ('未新增生产规则。' if not rule_changes else ' '.join(c['description'] for c in rule_changes))),
        ('人工抽检', human), ('剩余不确定性', limitations), ('模型与运行记录', model),
        ('可复现入口', 'uv run python -B scripts/acceptance.py collect、compare、collect_second、collect_third、freeze_reference、final_compare。'
         '首次冻结v1后运行supplement_reference保留v1并生成v2，不能覆盖旧版本；生产全量运行及导出使用scripts/full.py，独立原表保留验证使用scripts/excel_output.py。'
         '人工入口为scripts/human_confirmation.py serve。全部答案、差异、引用、模型、提示词及日志位于validation/0.7.0/final-acceptance。')]:
        report.add_paragraph(heading, style='Heading 1')
        report.add_paragraph(text)
    report_file = OUT / '验收报告.docx'
    report.save(report_file)
    with (OUT / '剩余不确定性.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['原始行ID', 'Excel原行', '标题', '脚本状态', '脚本候选数组', '参考状态', '参考候选数组', '裁决依据', '标题证据', '正文证据'])
        for r in unresolved:
            a = r['reference']
            writer.writerow([r['row_id'], r['excel_row'], r['title'], r['script']['status'], json.dumps(r['script']['names'], ensure_ascii=False),
                a['status'], json.dumps(a['names'], ensure_ascii=False), a.get('adjudication_reason', a['reason']),
                json.dumps(a['title_evidence'], ensure_ascii=False), json.dumps(a['body_evidence'], ensure_ascii=False)])
    payload = dict(status=state, metrics=metrics, reference=manifest, first=progress, second=second, third=third,
                   excel_verification=excel_check, documents=[str(word), str(report_file)],
                   historical_paragraphs_preserved=len(historical), historical_tables_preserved=len(tables),
                   visual_render_verified=False)
    (WORK / 'delivery-report.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
