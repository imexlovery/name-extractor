"""First-pass title rules; ambiguous institution boundaries stay uncertain."""

from __future__ import annotations

import re
import unicodedata
import json
from pathlib import Path

VERSION = "r51"

_HAN_RANGES = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
    (0x20000, 0x2A6DF), (0x2A700, 0x2B73F), (0x2B740, 0x2B81F),
    (0x2B820, 0x2CEAF), (0x2CEB0, 0x2EBEF), (0x2EBF0, 0x2EE5F),
    (0x2F800, 0x2FA1F), (0x30000, 0x3134F), (0x31350, 0x323AF),
    (0x323B0, 0x3347F),
)


def _han(char: str) -> bool:
    value = ord(char)
    return value == 0x3007 or any(a <= value <= b for a, b in _HAN_RANGES)


def name_length(text: str) -> int:
    """Count Han characters and ASCII letters, including inside aliases."""
    return sum(_han(c) or "A" <= c <= "Z" or "a" <= c <= "z" for c in text)


_PREFIX = re.compile(r"^(?:终止审查|同意核准|不予核准|不予许可|注销|核准|批准|同意|核定|确认|申请|拟任|担任|出任)")
_OMITTED = re.compile(r"等(?:[0-9０-９一二三四五六七八九十百千万两〇零]+)?(?:人|位(?:同志|理事|董事)|名(?:同志)?|同志)|等(?=理事|董事|高级管理人员|高管)|等$")
_INSTITUTION_END = re.compile(
    r"股份有限公司|有限责任公司|有限公司|股份公司|相互保险社|"
    r"农村资金互助社|农村信用社联合社|农村信用合作联社|农村信用联社|信用合作社|信用社|联合社|联社|农商行|农合行|"
    r"银行|保险公社|保险社|银行业|保险业|农信社|信托|人寿|财险|寿险|养老|株式会社|农发行|进出口行|金租|消金|理财|村行|互保|中支|代表处|分行|支行|分社|支公司|分公司|分中心|审计中心|电话销售中心|营业部|财务|服务点|公司"
)
_ROLE = re.compile(
    r"内部审计部负责人|法律合规部负责人|内审合规部总经理|会长|"
    r"计划财务部(?:负责人|总经理|经理)|财务会计部(?:负责人|总经理|经理)|财务总监|风险合规部(?:负责人|总经理|经理)|合规风险法务部门负责人|营业部(?:总经理|经理)|"
    r"(?:银行业金融机构|商业银行|农村商业银行|金融机构|金融)?高级管理人员|高管人员|高管|"
    r"(?:内审|财务|合规)(?:部门|部)负责人|合规风险法务部经理|运营财务部总经理|内控与风险合规部负责人|"
    r"首席合规官|首席运营官|"
    r"首席风险管理执行官|首席风险控制官|信息科技总监|信息总监|运营总监|营销总监|总审计师|审计责任人|信贷风险官|合规负责人|合规总监|合规官|风险官|风险总监|(?:合规[与及和]?)?风险管理部|"
    r"总会计师|总法律顾问|总裁助理|副总裁|总裁|"
    r"财务负责人|主要负责人|营业部主任助理|营业部主任|"
    r"金融机构(?:董事会秘书|副董事长|董事长|董事)|高级管理人员|高管人员|董事会秘书|副董事长|董事长|"
    r"(?:第[一二三四五六七八九十0-9]+届)?董事会|股权董事|股东董事|职工董事|非执行董事|执行董事|独立董事|董事|副理事长|理事长|内部理事|独立理事|理事|"
    r"副监事长|监事长|监事|行长助理|副行长|(?<!银)行长|"
    r"总经理助理|副总经理|总经理|总精算师|副经理|经理|"
    r"主任助理|副主任|主任|副首席代表|首席代表|"
    r"首席信息官|首席风险官|首席财务官|内审负责人|负责人"
)
_ROLE_QUALIFIER = re.compile(r"^[（(](?:主持工作|代为履职|代行职责|风险总监)[）)]")
_DEPARTMENT = re.compile(r"再保险运营中心|运营中心|审计中心|稽核审计部|审计分部|审计部|风险内控部|内控合规部|法律合规部|合规部|财会部|计财部|合规风险法务部|风险合规部|风险管理部|管理部|金融市场中心|营业部|营业室|办事处")
_TO_POST = re.compile(r"担任|出任|拟任|任(?=" + _ROLE.pattern + r")")
_BUSINESS_ACTION = re.compile(r"开业|设立|筹建|升格|改建为支公司|终止营业|撤销|变更首席代表|变更董事|董事长变更备案|保险兼业代理业务资格申请|更名|变更(?:营业场所|机构名称|住所|组织形式|营业地址|总代表)|变更.*营业场所|(?:修改|修订|变更).*章程|章程变更|资本工具计划发行额度")
_NON_PERSON = re.compile(r"营业部|营业室|中心|办事处|部门|管理部|管理行|审计分部|审计部|风险内控部|合规部|财会部|计财部|风险合规部|合规风险法务部|业务部|事业部|总部|总行|开业|高管|负责人|主要|财务|保险|信用社|股份有限公|派驻|^兼$|^及$|^和$|^助理$")

# These are institutional/geographical anchors, never person or surname lists.
# An unfamiliar institution root is deliberately not split by a guessed name length.
_INSTITUTION_STARTS = (
    "中国", "国家开发银行", "工商银行", "建设银行", "农业银行", "交通银行",
    "邮政储蓄银行", "平安银行", "中信", "友利银行", "韩亚银行", "新韩银行",
    "蒙特利尔银行", "三井住友银行", "韩国输出入银行", "中德住房储蓄银行",
    "银行业", "保险业", "金融机构", "泰康人寿", "太平财产保险", "太平人寿", "阳光财产保险",
    "百年人寿", "中宏人寿", "瑞泰人寿", "中邮保险", "英大泰和人寿",
    # r02 roots are explicit institutional spans in the ten r01 difference titles.
    # They apply to any title containing that institution, without person/row overrides.
    "清河农商银行", "安福中银富登村镇银行", "故城县农村信用联社",
    "华泰集团财务", "漯河市源汇区农村信用合作联社", "德州银行",
    "企业银行", "玉屏长征村镇银行", "赞皇县农村信用联社",
    "济南槐荫沪农商村镇银行",
    # Institution spans from the independently audited silent-error titles.
    "遂宁银行", "信托保障基金公司", "升华茂林保险销售服务有限公司", "西安银行",
    "华夏人寿", "泰康养老", "华泰财险", "紫金财险",
    "农发行", "进出口行",
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
    "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
    "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
    "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆", "香港", "澳门", "台湾",
)
_ACRONYM_INSTITUTION = re.compile(r"[A-Z]{2,}(?=科技集团|集团财务|金融公司)")
INSTITUTION_ANCHOR_RESOURCE = 'institution_anchors_r41.json'
_INSTITUTION_STARTS += tuple(json.loads(Path(__file__).with_name(INSTITUTION_ANCHOR_RESOURCE).read_text(encoding='utf-8')))
_REGION_ANCHORS = set('中国 北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 山东 河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 青海 宁夏 新疆 香港 澳门 台湾'.split())


def _outside(text: str) -> tuple[str, bool]:
    """Mask parentheses with spaces while keeping original character offsets."""
    stack: list[str] = []
    output = []
    for char in text:
        if char in "（(":
            stack.append(char)
            output.append(" ")
        elif char in "）)":
            if not stack:
                return text, False
            stack.pop()
            output.append(" ")
        else:
            output.append(" " if stack else char)
    return "".join(output), not stack


# Institution resources are fixed for a run; mask once, retaining source offsets.
_PARENT_END = re.compile(r"股份有限公司|有限责任公司|有限公司|股份公司|相互保险社|农村信用社联合社|农村信用合作联社|信用合作联社|银行")
_PARENT_INSTITUTIONS = {
    anchor[:match.end()]
    for anchor in _INSTITUTION_STARTS
    for match in _PARENT_END.finditer(anchor)
    if match.start() > 0
}
_MASKED_INSTITUTIONS = tuple((_outside(anchor)[0], len(anchor)) for anchor in set(_INSTITUTION_STARTS) | _PARENT_INSTITUTIONS if anchor not in _REGION_ANCHORS)
_COMPLETE_INSTITUTIONS = {anchor for anchor, length in _MASKED_INSTITUTIONS}

# Preserve every source offset instead of letting resource order select a match.
_INSTITUTION_TRIE = {}
for _anchor, _length in _MASKED_INSTITUTIONS:
    _node = _INSTITUTION_TRIE
    for _character in _anchor:
        _node = _node.setdefault(_character, {})
    _node[None] = _length


def _registered_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    for start in range(len(text)):
        node = _INSTITUTION_TRIE
        for end in range(start, len(text)):
            node = node.get(text[end])
            if node is None:
                break
            if None in node:
                spans.append((start, start + node[None]))
    return spans


def _institution_context(text: str) -> bool:
    """An institutional heading can establish context, not absence of people."""
    outer, balanced = _outside(text.strip())
    return balanced and any(start == 0 for start, end in _registered_spans(outer)) and any(
        match.end() == len(outer) for match in _INSTITUTION_END.finditer(outer)) and not _ROLE.search(outer)


def _before_role(text: str) -> str:
    outer, _ = _outside(text)
    cuts = [m.start() for pattern in (_ROLE, _TO_POST) if (m := pattern.search(outer))]
    return text[:min(cuts)] if cuts else text


def _after_leading_roles(text: str) -> str:
    value = text.strip()
    while match := _ROLE.match(value):
        value = value[match.end():].lstrip()
        if qualifier := _ROLE_QUALIFIER.match(value):
            value = value[qualifier.end():].lstrip()
        next_role = value.lstrip("、,，；;及和兼 ")
        if _ROLE.match(next_role):
            value = next_role
    return value


def _result(names: list[str], status: str, rule: str, note: str = "") -> dict:
    return {"names": names, "status": status, "rule": rule, "note": note}


def _finish(candidate: str, rule: str, note: str = "") -> dict:
    while candidate and unicodedata.category(candidate[0]) == 'Cf':
        candidate = candidate[1:]
    while candidate and unicodedata.category(candidate[-1]) == 'Cf':
        candidate = candidate[:-1]
    candidate = re.sub(r'^DR\.', '', candidate, flags=re.I)
    outer, balanced = _outside(candidate)
    if not balanced:
        return _result([candidate] if candidate else [], "uncertain", rule, "括号不配对")
    if re.search(r'[A-Za-z]', outer) and re.search(r'[,，]', outer):
        return _result([candidate], 'uncertain', rule, '外文括号外逗号的同人或多人关系缺少标题依据')
    if rule == 'institution_before_person' and re.fullmatch(r'行[\u4e00-\u9fff]+', outer):
        return _result([candidate], 'uncertain', rule, '机构后孤立行字可能为姓名首字或机构职务残片')
    if rule == 'generic_institution_before_boundary':
        return _result([candidate], 'uncertain', rule, '泛称金融机构前长汉字片段缺少姓名及地区边界')
    separators = [m.start() for m in re.finditer(r"[、；;]", outer)]
    # Commas can belong to a Western name. Only purely Han comma lists split here.
    if not re.search(r"[A-Za-z]", outer):
        separators += [m.start() for m in re.finditer(r"[,，]", outer)]
    starts, names = 0, []
    for end in sorted(separators) + [len(candidate)]:
        part = re.sub(r"(?:[0-9０-９一二三四五六七八九十百千万两〇零]+位)?(?:同志|先生|女士)(?:的)?$", "", candidate[starts:end].strip())
        part = re.sub(r'[一二三四五六七八九十两0-9]+人$', '', part)
        qualifier = re.search(r'[（(]([^（）()]*)[）)]$', part)
        if qualifier and _ROLE.fullmatch(qualifier[1]):
            part = part[:qualifier.start()].rstrip()
        starts = end + 1
        if not part:
            return _result(names, "uncertain", rule, "并列片段为空")
        masked, _ = _outside(part)
        if not masked.strip():
            return _result(names + [part], "uncertain", rule, "只有括号内说明，缺少括号外姓名")
        if rule == 'person_before_institution' and part.endswith('的'):
            return _result(names + [part[:-1]], 'uncertain', rule, '机构前的字可能为连接词，候选需语义复核')
        if part.endswith('等'):
            return _result(names + [part[:-1]], 'uncertain', rule, '候选尾部等字可能为省略标记，需语义复核')
        if re.fullmatch(r'[0-9０-９一二三四五六七八九十百千万两〇零]+[名位个]',part):
            if rule == 'institution_before_person' and not names:
                return _result([], 'no_name', rule, '机构职务只明示人数，未明示姓名')
            return _result(names + [part], 'uncertain', rule, '候选仅是人数表达，标题是否明示姓名需复核')
        if rule == 'person_before_institution' and part.endswith('任'):
            return _result(names + [part[:-1]], 'uncertain', rule, '机构前任字可能为任职动词，需语义复核')
        connectors = list(re.finditer(r"[和及与]", masked))
        connectors = [m for m in connectors if m.start() > 0 and masked[m.end():].strip()]
        if name_length(masked) > 4 and connectors:
            split_candidates = []
            start = 0
            for delimiter in connectors:
                split_candidates.append(part[start:delimiter.start()].strip())
                start = delimiter.end()
            split_candidates.append(part[start:].strip())
            candidates = split_candidates if all(name_length(n) >= 2 for n in split_candidates) else [part]
            return _result(names + candidates, "uncertain", rule, "连接词关系待独立复核，候选分段不表示已确认多人")
        if _INSTITUTION_END.search(masked) or _ROLE.search(masked) or "金融机构" in masked:
            return _result(names, "uncertain", rule, "姓名与机构或职务边界未确定")
        if _NON_PERSON.search(masked):
            return _result(names + [part], "uncertain", rule, "候选含部门、事项或连接词残片")
        allowed_punctuation = "·•・‧∙⋅.-‐‑‒–—－,，'’（）()"
        if any(not (c.isalpha() or _han(c) or c.isspace() or c in allowed_punctuation) for c in part):
            return _result(names + [part], "uncertain", rule, "候选含未定义的字符")
        names.append(part)
    if any(unicodedata.category(c).startswith("L") and not (_han(c) or c.isascii() or 'LATIN' in unicodedata.name(c, '')) for n in names for c in n):
        return _result(names, "uncertain", rule, "其他书写体系需要复核")
    if any(name_length(n) == 0 for n in names):
        return _result(names, "uncertain", rule, "未找到明确姓名字符")
    if any(name_length(n) == 1 for n in names):
        return _result(names, "uncertain", rule, "单字候选需要复核，可能为边界截断")
    if any(not re.search('[A-Za-z·•・‧∙⋅]', n) and name_length(n) > 4 for n in names):
        return _result(names, 'uncertain', rule, '较长连续汉字可能是完整长姓名或连写多人，保留原片段由语义复核，不按长度猜拆')
    return _result(names, "names", rule, note)


def _extract(title: str) -> dict:
    """Return ordered original name expressions, or an explicit unresolved status."""
    if not isinstance(title, str) or not title.strip():
        return _result([], "uncertain", "empty_title", "标题为空")
    core = title.split("关于", 1)[-1].strip()
    core = re.sub(r"^[\u4e00-\u9fff]{2,24}?(?:银保监局|银监局|监管分局|监管局)", "", core).strip()
    # A document type does not establish absence of a named applicant.
    if notice := re.fullmatch(r'(?:加强)?(.+?)(?:同志|先生|女士)(?:准予行政许可决定书|行政许可事项终止审查通知书|任职资格管理的通知)', core):
        return _finish(notice[1], 'named_administrative_notice')
    quoted = list(re.finditer(r'《[^》]*》', core))
    if quoted:
        tail = core[quoted[-1].end():]
        if mixed := re.fullmatch(r'(?:及|并|和|、)(?:核准)?(.+(?:任职资格|拟任资格).*)', tail):
            return extract(mixed[1])
    if heading := re.fullmatch(r'(.+?)(?:：|:|——)(.+(?:任职资格|拟任资格).*)', core):
        institution = heading[1]
        while match := _PREFIX.match(institution):
            institution = institution[match.end():].lstrip()
        if _institution_context(institution):
            return extract(heading[2])
    if roster := re.fullmatch(r'(.+?)[（(]([^（）()：:]*)名单[：:](.+)[）)](?:任职资格|拟任资格).*', core):
        if _institution_context(roster[1]) and (not roster[2] or _ROLE.fullmatch(roster[2])):
            return extract(roster[3] + '任职资格')
    if (re.search(r'《[^》]*任职资格[^》]*》', core) and core.endswith(('的通知', '的公示'))) or re.fullmatch(r'中国银行保险监督管理委员会令[（(][^（）()]+[）)]', core):
        return _result([], 'no_name', 'regulatory_document', '规范性文件标题未明示被批复人')
    if re.fullmatch(r'(?:加强|开展|执行).*?(?:管理|活动|问题)的通知', core):
        return _result([], 'no_name', 'regulatory_document', '规范性事项通知未明示被批复人')
    if repeat := re.fullmatch(r'(.+?任职资格的批复)(?:于|关于)?\1', core):
        return extract(repeat[1])
    if repeat := re.search(r'((?:' + _ROLE.pattern + r')任职资格的批复)\1$', core):
        return extract(core[:repeat.start()] + repeat[1])
    qualification = re.search(r"任职资格|任职|职资格|拟任资格|(?<=" + r"董事" + r")资格", core)
    if qualification is None:
        institution_only = core.removesuffix('的批复')
        while match := _PREFIX.match(institution_only):
            institution_only = institution_only[match.end():].lstrip()
        institution_only, balanced = _outside(institution_only)
        if balanced and institution_only in _COMPLETE_INSTITUTIONS:
            return _result([], 'no_name', 'complete_institution_without_person', '标题仅为有来源的完整机构，未明示姓名')
        if re.fullmatch(r'.*?(?:准予行政许可决定书|行政许可事项终止审查通知书)', core):
            return _result([], 'no_name', 'administrative_notice', '文书标题未明示被批复人')
        if _INSTITUTION_END.search(core) and _BUSINESS_ACTION.search(core):
            return _result([], "no_name", "institution_business_action", "机构事项，标题未明示姓名")
        if (_INSTITUTION_END.search(core) or _ROLE.search(core)) and _ROLE.search(core) and core.endswith('的批复'):
            # A named institution and explicit post supply the missing qualification context.
            return extract(re.sub(r'资格$', '', core.removesuffix('的批复')) + '任职资格的批复')
        if simple := re.fullmatch(r'核准(.+)的批复', core):
            return _result([simple[1]], 'uncertain', 'approval_object_without_qualification', '裸核准对象缺少任职或岗位语义，不能区分个人和机构简称')
        if _INSTITUTION_END.search(core) and _BUSINESS_ACTION.search(core):
            return _result([], "no_name", "institution_business_action", "机构事项，标题未明示姓名")
        return _result([], "uncertain", "missing_qualification", "缺少任职资格结构")
    if len(re.findall('任职资格', core)) == 1:
        prefix = core[:qualification.start()]
        masked_prefix, balanced_prefix = _outside(prefix)
        separators = list(re.finditer('[、；;]', masked_prefix))
        if balanced_prefix and separators:
            starts = [0] + [match.end() for match in separators]
            ends = [match.start() for match in separators] + [len(prefix)]
            clauses = [prefix[start:end].strip() for start, end in zip(starts, ends)]
            results = [extract(clause + '任职资格') for clause in clauses if clause]
            if len(results) == len(clauses):
                accepted = []
                for index, (clause, result) in enumerate(zip(clauses, results)):
                    if result['status'] == 'names':
                        accepted.extend(result['names'])
                    elif accepted and _ROLE.match(clause) and not _after_leading_roles(clause).strip():
                        continue
                    elif index == 0 and _institution_context(clause):
                        continue
                    else:
                        break
                else:
                    if accepted:
                        return _result(accepted, 'names', 'complete_person_clauses')
    if len(re.findall('任职资格',core)) > 1:
        clauses = re.split(r'任职资格(?:的批复)?[、和及与]', core)
        if len(clauses) > 1:
            results = [extract(clause if '任职资格' in clause else clause+'任职资格') for clause in clauses]
            if all(result['status']=='names' for result in results):
                return _result([name for result in results for name in result['names']], 'names', 'explicit_qualification_clauses')
        return _result([], 'uncertain', 'multiple_qualification_segments', '标题有多个任职资格片段，需检查全部被批复人，不能仅取首段')
    core = core[:qualification.start()].strip()
    if re.fullmatch(r'核[\u4e00-\u9fff]{2,}', core) and not core.startswith('核准'):
        return _result([core], 'uncertain', 'incomplete_approval_verb', '核可能为缺字许可动词或原姓名首字，缺少唯一边界')
    if core.endswith('拟') and title[title.find(core) + len(core):].startswith('任职资格'):
        return _result([core], 'uncertain', 'ambiguous_proposed_appointment', '拟可能修饰任职资格或属于原姓名尾字，缺少唯一边界')
    core = core.removesuffix('的').rstrip()
    if core.startswith('对') and ('关于对' in title or '监管分局对' in title or '监管局对' in title):
        core = core[1:].lstrip()
    while match := _PREFIX.match(core):
        core = core[match.end():].lstrip()
    outer, balanced = _outside(core)
    if not balanced:
        return _result([core] if core else [], "uncertain", "unbalanced_parentheses", "括号不配对")
    if not _INSTITUTION_END.search(outer) and (ambiguous := re.search(r'(?<!主)任(?=高级管理人员|高管)', outer)):
        return _result([core[:ambiguous.end()]], 'uncertain', 'ambiguous_post_verb', '任可能为姓名尾字或任职动词，标题无明确分隔')
    roles=list(_ROLE.finditer(outer))
    if any(re.search('[、,，;；和及与]',outer[first.end():second.start()]) and _INSTITUTION_END.search(outer[first.end():second.start()]) for first,second in zip(roles,roles[1:])):
        clauses = re.split(r'[、；;]', core)
        if len(clauses)>1:
            results=[extract(clause+'任职资格') for clause in clauses]
            if all(result['status']=='names' for result in results):
                return _result([name for result in results for name in result['names']], 'names', 'explicit_post_clauses')
        return _result([], 'uncertain', 'multiple_person_or_post_clauses', '多个机构职务片段可能对应不同人，不能仅取首个姓名')
    omitted = _OMITTED.search(outer)
    note = "仅保留等N人或等人之前的明示姓名" if omitted else ""
    if omitted:
        core, outer = core[:omitted.start()].rstrip(), outer[:omitted.start()]
    if not core:
        return _result([], "uncertain", "missing_person_segment", "未找到被批复人片段")

    # An opening and a named appointment are distinct coordinated actions.
    # Require the complete registered institution to precede the opening action.
    if opening := re.search(r'开业(?:并|及|和|、)(?:同意)?核准', outer):
        institution = outer[:opening.start()].strip()
        if institution in _COMPLETE_INSTITUTIONS or _institution_context(institution):
            result = extract(core[opening.end():] + '任职资格')
            if result['status'] == 'names':
                result['rule'] = 'opening_and_named_appointment'
            return result

    person_part = _before_role(core).strip()
    masked, _ = _outside(person_part)
    institution_only = re.sub(r'开业[、,，和及并]*$', '', masked).strip()
    if institution_only in _COMPLETE_INSTITUTIONS and not _after_leading_roles(core[len(person_part):]).strip():
        return _result([], 'no_name', 'complete_institution_without_person', '有来源的完整机构及职务结构未明示姓名')
    institutions = list(_INSTITUTION_END.finditer(masked))
    specific = _registered_spans(masked)
    leading = [end for start,end in specific if start==0]
    if leading:
        start = max(leading)
        if core[start:].endswith('联社主任') and core[start:-len('联社主任')].strip():
            return _finish(core[start:-len('联社主任')].strip(), 'person_between_institution_and_post', note)
        trailing = [left for left,end in specific if left>start and end==len(masked)]
        if trailing:
            return _finish(person_part[start:min(trailing)].strip(), 'person_between_institutions', note)
    if specific and min(start for start,end in specific) > 0 and not any(masked.startswith(region) for region in _REGION_ANCHORS):
        candidate = person_part[:min(start for start,end in specific)].strip()
        if person_part[min(start for start,end in specific):].startswith('金融机构') and re.fullmatch(r'[\u4e00-\u9fff]{4,}', candidate):
            return _finish(candidate, 'generic_institution_before_boundary', note)
        return _finish(candidate, 'person_before_institution', note)
    unresolved_tail = None
    if institutions:
        # Institution-first titles can contain branches and a job before the name.
        tail = core[institutions[-1].end():]
        tail = re.sub(r'^(?:(?:升格|更名|开业|迁址|变更营业场所)[、,，和及]*)+', '', tail)
        while match := _PREFIX.match(tail):
            tail=tail[match.end():].lstrip()
        tail = _after_leading_roles(tail)
        department = _DEPARTMENT.search(tail)
        if department:
            prefix = tail[:department.start()]
            if not prefix or any(prefix.startswith(region) for region in _REGION_ANCHORS) or _NON_PERSON.search(prefix) or re.search(r'路$|第[一二三四五六七八九十0-9]+$|^[东西南北]区$', prefix):
                after_department = _after_leading_roles(tail[department.end():])
                if after_department:
                    tail = after_department
        tail = _before_role(tail).strip()
        if tail:
            result = _finish(tail, "institution_before_person", note)
            if result["status"] == "names":
                return result
            unresolved_tail = result

    person_part = _before_role(core).strip()
    masked, _ = _outside(person_part)
    if _INSTITUTION_END.search(masked) or "金融机构" in masked:
        specific = _registered_spans(masked)
        cuts = [start for start, end in specific]
        for anchor in _REGION_ANCHORS:
            position = masked.find(anchor)
            if position >= 0 and not any(position < end and position + len(anchor) > start for start, end in specific):
                cuts.append(position)
        cuts += [m.start() for m in _ACRONYM_INSTITUTION.finditer(masked)]
        if cuts and min(cuts) > 0:
            candidate = person_part[:min(cuts)].strip()
            if person_part[min(cuts):].startswith('金融机构') and re.fullmatch(r'[\u4e00-\u9fff]{4,}', candidate):
                return _finish(candidate, 'generic_institution_before_boundary', note)
            # A leftover administrative suffix indicates an unresolved earlier root.
            if not specific and re.search(r"省|自治区|自治州|市|县|区|乡|镇|旗|盟|街道", candidate):
                return _result([], "uncertain", "institution_root_unknown", "机构起点可能早于已识别锚点")
            return _finish(candidate, "person_before_institution", note)
        if cuts and min(cuts) == 0:
            if unresolved_tail is not None:
                return unresolved_tail
            if len(institutions) > 1:
                return _result([], 'uncertain', 'institution_intermediate_segment', '机构及分支间可能含姓名，不能因末尾无姓名即确认无姓名')
            return _result([], "no_name", "institution_without_person", "机构及职务结构未明示姓名")
        return _result([], "uncertain", "institution_root_unknown", "机构起点未确定，未按姓名长度猜分界")
    if not person_part:
        return _result([], "no_name", "role_without_person", "只有职务或群体，没有明示姓名")
    return _finish(person_part, "person_before_qualification", note)


def extract(title: str) -> dict:
    """Resolve complete structural candidates; conflicting subjects stay open."""
    result = _extract(title)
    if result['status'] != 'names' or result['rule'] in {
        'explicit_qualification_clauses', 'explicit_post_clauses', 'complete_person_clauses',
        'opening_and_named_appointment',
    }:
        return result
    core = title.split('关于', 1)[-1].strip()
    qualification = re.search(r'任职资格|任职|职资格|拟任资格', core)
    if qualification is None:
        return result
    core = core[:qualification.start()].strip()
    while match := _PREFIX.match(core):
        core = core[match.end():].lstrip()
    outer, balanced = _outside(core)
    if not balanced:
        return result
    spans = _registered_spans(outer)
    if not spans:
        return result
    # Nested mother/branch matches belong to the same institution span.
    first = min(start for start, end in spans)
    last = max(end for start, end in spans)
    # A known mother institution can have a previously unseen regional branch.
    # Its explicit branch suffix extends the institution, not the person span.
    roles = list(_ROLE.finditer(outer))
    last = max([last] + [match.end() for match in _INSTITUTION_END.finditer(outer)
                        if match.start() >= first and not any(
                            match.start() < role.end() and match.end() > role.start() for role in roles)])
    if first == 0:
        return result
    prefix = _finish(core[:first].strip(), 'structural_prefix')
    tail = _after_leading_roles(core[last:])
    tail_outer, _ = _outside(tail)
    if role := _ROLE.search(tail_outer):
        if _after_leading_roles(tail[role.start():]).strip():
            return result
        tail = tail[:role.start()].strip()
    if not tail:
        return result
    suffix = _finish(tail, 'structural_suffix')
    if prefix['status'] == suffix['status'] == 'names' and prefix['names'] != suffix['names']:
        return _result(prefix['names'] + suffix['names'], 'uncertain', 'conflicting_person_boundaries',
                       '机构前与机构岗位后均有完整姓名主体结构，首个正则不能独自确定被批复人')
    return result
