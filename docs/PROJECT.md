# 项目总览

仅从标题提取任职资格批复明示姓名，保留52,146条记录、13原字段及格式，只追加提取姓名和姓名字数。[项目要求](../项目要求.md)为最高参考，要求超过99.8%、自查错误归零及最终人工检查，当前尚未最终验收。

## 当前状态 2026年10月14日

以r64本地提交 `4c42608` / 标签 `v0.7.0-r64` 冻结后，独立AI审核覆盖全部52,146行（51,962独立输入，184原行精确输入复用），原始行ID与13字段保留。第二轮独立重读3,602输入，第三轮裁决327输入；9条机构边界补证修正6处参考错误，固定参考v2保留v1和更正依据。

r65仅修复3行有具体原文证据的姓名边界；57项测试、46,760标题/52,146行合同检查以及Excel原字段回读验证通过。固定参考匹配52,031行，全量一致率99.7795%，76行脚本未决但参考明确，39行参考无法裁决，未达到高于99.8%的验收目标，明确错误未归零。真实准确率未知，人工实际检查0/100。100条非盲确认表已固定（60随机、40风险）。

[当前验收指标](../validation/0.7.0/final-acceptance/final-comparison.json)、[固定参考版本](../validation/0.7.0/final-acceptance/reference-manifest.json)、[交付目录](../outputs/0.7.0/最终交付)、[下一步](PLAN.md)。用户已确认保留通用规则并披露差异，不新增逐标题边界例外；当前生产仍仅执行通用标题规则，不回填AI答案。

## r64冻结时的历史状态

0.6.0/r61已通过本地提交9259fed及标签v0.6.0-r61封存为待验收工程版，见[封存说明](0.6.0封存说明.md)。封存时71标题78行未决，相对r56新增确定51标题53行，原确定输出不变；源码、资源、Word及Excel保留。

当前0.7.0/r64补齐完整监管新闻和地区金融学会理事会负责人变更公示的无姓名路径，要求消费完整原标题，具名或残缺内容不放行。相对本地提交083f03c的r63恰好2标题2行由未决转无姓名，原确定输出不变。全量46,760标题：姓名45,997/51,309行，无姓名691/758行，未决72/79行。46项测试、全量合同、52,146行生产映射及r64候选Excel导出检查均通过；[r64候选审阅入口](../validation/0.7.0/delivery-closure/候选审阅入口.md)记录了原表保留证据。

第三轮字符语境实验A1未选出可用参数。A2冻结后仅在90标题留出集评分一次，出现4个可靠错误并按协议停止；目标标题及第11008行未评分，实验没有进入生产，当前仍为r64，没有建立r65。这个结构代理实验不能给出全表真实准确率，也不能证明字符语境方法在所有场景均不可行。r64仍是工程候选，项目验收未通过；第11008行已知漏提、72标题79行未决、105标题108行人数风险和最终人工检查缺口仍在，真实准确率未知。详见[第三轮收尾](../validation/0.7.0/delivery-closure/round-03.md)与[交付审计](../validation/0.7.0/delivery-closure/交付审计报告.md)。

生产为script_only，不读取正文或AI、人工姓名答案。第11008行白玉娥李毅昕仍连写多人漏提。39个长度拦截标题/42行未发现被遗漏的内部人数、称谓或名单边界；既有单人和多人判断不能仅凭完整槽位区分。原122条人工记录保留，部分看过正文；119条确定人工答案中55条脚本完整匹配，64标题/67行待完成，另3条人工答案未决。41个待完成标题候选相同但仍弃权，23个候选不同，不将全部待完成称为已确认错误。此前固定894标题GPT复核为889确定匹配、5共同未决、确定分歧0，不要求用户逐条人工填完894条。收尾74原标题首答及逐轮研究另存，不作为人工真值。旧AI参考确定差异0，35单渠道、37分歧及22,525缺参考仍保留，真实准确率未知。

## 成果与入口

- [0.7.0验证报告](../validation/0.7.0/验证报告.md)、[r64候选Excel](../outputs/0.7.0/任职资格批复汇总测试-0.7.0-r64纯脚本待复核版.xlsx)、[阶段统计](../validation/0.7.0/stage-report.json)、[r64实际变化](../validation/0.7.0/changes-r64.jsonl)及[894独立GPT复核](../validation/0.7.0/independent-review/summary.json)
- [当前未决](../validation/0.7.0/remaining-unresolved.jsonl)、[第三轮收尾](../validation/0.7.0/delivery-closure/round-03.md)、[候选审阅入口](../validation/0.7.0/delivery-closure/候选审阅入口.md)及[连写多人研究](../validation/0.7.0/连写多人研究.md)
- [r61封存Excel](../outputs/0.6.0/任职资格批复汇总测试-0.6.0-r61纯脚本待复核版.xlsx)及[原阶段报告](../validation/0.6.0/验证报告.md)
- [原人工记录](../validation/0.6.0/human-review.jsonl)、[694无姓名检查](../validation/0.6.0/原694无姓名标题-人工盲审.csv)及[冻结200随机检查](../validation/0.6.0/随机200标题-人工盲审.csv)
- [下一步](PLAN.md)及[系统结构](ARCHITECTURE.md)

根目录Word有效规则同步当前版本，历史附录保留。没有push或外发。

## 复现

沿用Python、uv、本地.venv及uv.lock，无新增依赖。默认validation/0.7.0，导出outputs/0.7.0。

```sh
cd /Users/tristana/法询金融科技codex测试
uv run python -B scripts/full.py run
uv run python -B scripts/full.py finish
uv run python -B validation/0.7.0/evaluate_stage.py
uv run python -B -m unittest discover -s tests
uv run python -B validation/0.7.0/independent-review/evaluate_blind.py
uv run python -B validation/0.7.0/independent-review/scan_confirmed.py
uv run python -B validation/0.7.0/concatenated_experiment.py
```

run保存实际源码和资源，首轮及阶段差异比较冻结r61，后续逐轮比较前轮；finish/export复用旧参考，只用脚本写生产单元格。人工检查入口沿用0.6.0文件，不重抽名单、不覆盖原阶段产物。
