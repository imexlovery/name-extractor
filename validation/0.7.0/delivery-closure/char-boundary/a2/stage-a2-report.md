# 字符语境实验 A2：阶段结果

本报告记录 A2 的一次预先约定拟合与校准。A1 的 `selected=null` 和未评分 holdout90 状态继续保留；A2 是材料和起止位置特征来源修订，不覆盖 A1 失败。所有结果是结构代理或弱监督字符证据，不是真实原表准确率。

## 弱字符材料与拟合计数

- inventory 唯一标题记录：46760；合格来源记录：23174；拒收记录：23586。
- 合格裸主体去重后：22361；弱来源覆盖原行：27644。
- A1 结构样本：430 条/原分组组数 423；fit/calibration/holdout 分组原样沿用。
- 去重后拟合片段：22626；唯一 A1 fit 原标点名单表达：91；这些表达的显式边界数：107。
- 弱主体只提供起止位置和片段内部二/三字语境；只有 A1 fit 原标点名单提供边界跨隙 n-gram。
- 隔离核对：41 个目标完整标题（39 个原目标与 2 个四字风险题）对应 44 条原始行，均按标题屏蔽；523 个长度至少 2 的目标候选连续子串均排除。最终拟合片段与 A1 calibration/holdout 的 `parts` 或 `text` 完整匹配交集为 0，目标子串交集也为 0。行数及隔离复核见[主审记录](../../round-03-main-review.json)。

## 校准与留出

- 校准候选数：98；选择结果：`{"bias": 2.116556438866837, "margin_strictly_above": 0.0, "accepted_correct": {"multi": 29, "whole4": 1, "long_whole": 2}, "balanced_coverage": 0.6666666666666666}`。
- 校准原因：`selected`；覆盖摘要：`{"multi": {"covered": 29, "unknown_gap": 1}, "short_whole": {"not_testable": 51}, "whole4": {"covered": 1, "unknown_gap": 1}, "long_whole": {"covered": 2, "unknown_gap": 1}}`。
- holdout90 仅评分一次；汇总：`{"totals": {"not_testable": 52, "reliable_correct": 32, "reliable_error": 4, "abstain": 2}, "by_class": {"short_whole": {"not_testable": 52}, "multi": {"reliable_correct": 29, "reliable_error": 2, "abstain": 1}, "whole4": {"reliable_correct": 3}, "long_whole": {"reliable_error": 2, "abstain": 1}}}`。
- 阶段停止状态：`stopped_reliable_holdout_error`。

## 限制

短主体不是人工单人真值，不能用于校准或声称姓名准确率。A1 的结构样本来自原标点与语言形式代理，A2 的 holdout 结果即使通过，也只代表这组结构题。目标题候选仅参与事前防泄漏排除，没有生成预测或用于调参；进入目标 B 需要主 Agent 单独批准。
