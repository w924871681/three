# 第三篇论文：三图整合后的全文最高审校（2026-10-10）

## 交付结论

以此前纠正性 batch20 版本论文为完整正文基线，嵌入用户交付的 **Fig.1、Fig.2、Fig.3 原始 PDF**（均不改动图片字节），编译形成 **IEEEtran 双栏 9 页，8 个主章节、Algorithm 1、3 图、4 表、24 条参考文献**的完整稿件。三张图采用精简 caption：

- **Fig.1:** “Selective lifecycle escalation with score-gated RI admission and action commitment.”
- **Fig.2:** “Paired service-loss contrasts and center-level Proposed--B8 differences.”
- **Fig.3:** “Search admission, candidate-search updates, and committed RI actions.”

**这是一版正文与证据已同步、可完整编译的终稿候选；不等于已经满足无人审核的投稿冻结。**

## 全文科学审核

### Section 1–2：研究问题、贡献与相关工作

保持原有三项贡献和已有引文。未将固定身份维护、架构选择或在线漂移检测宣称为本文首次提出；贡献限定于：有界维护可恢复性的理论问题、维护响应驱动的在线准入证据、可行候选选择性升级及单路径提交。24 条引文保持正文首次出现顺序，编译引用均得到解析。

### Section 3–4：理论、代理信号与在线决策

保留原公式与算法实现边界，明确区分 (i) 全策略类上的 $\mathcal R_t^M$；(ii) 基于 $k\in\{0,10,20,50\}$ 的有限 one-shot 离线 hindsight reference $R_t^{\mathrm{fin}}$；(iii) 用 identity-specific 正尺度归一化的拟合标签；(iv) 冻结模型输出的在线准入分数 $q_t$。$q_t<0$ **仅开放模型级候选搜索，不强制执行 RI**。维护探测为 provisional candidate，候选 50 次更新是**每个候选**的适配量，不是全局搜索成本上限。在线只访问 update/assessment，service 在提交后揭示；RI 后历史清空。Fig.1 在 Method 中引用。

### Section 5：完整性纠正协议

保持 F1 full-batch20 统一输入、20中心 ×3 seeds ×4场景 ×5方法 ×24阶段，1,200 trajectories/28,800 stages，240 个五方法公平配对组和60个初始参考。说明原先239 fullbatch +961 singleton 的来源混合已被纠正。新运行属于**已观察结果后的完整性纠正性复核**，不能称全新 unseen heldout。受控 runtime 与历史 runtime 的逐位等价性没有独立证明。

Bootstrap 明确为20中心配对重采样、4000次、seed=2904、共享抽样索引；4个95%区间为**边际区间，不是多重比较同时区间**。B2 具备不同的固定身份更新和筛选规则，保持原描述。

### Section 6：三图与结果表分工

- Fig.2 给出四个 paired contrast 的置信区间和20中心 Proposed–B8 差值；Table II 负责精确记录五方法总体均值、观测差和置信区间。
- Fig.2 中 **18/20 中心**的聚合 Proposed–B8 差值恰为零，正文作描述性说明，不能推断逐阶段行为等价。
- Fig.3 区分搜索准入、candidate-search optimizer updates、最终提交 RI；Table III 仅保留维护、RI、retention 和 action penalty 等额外行为量。原先完全重复工作量的独立表已删除，计数移入 Fig.3 对应正文。
- Table IV 保留 C0/C1/C3/C4 分场景结果，不增加 Fig.4。

已同步的主要统计：Proposed mean loss **0.002940644**；B0 0.006604799、B1 0.003341980、B2 0.004883941、B8 0.002912627。Proposed–B8 观察差为 **+2.8016915×10⁻⁵**，边际95%区间 **[−1.85948×10⁻⁷, +8.42367×10⁻⁵]**，**跨零；不能声称优于B8、显著劣于B8、非劣性或统计等价**。对B0/B1/B2的三个边际区间均低于零。P7.7 open rate=1918/5760=33.30%；搜索更新数871,400 vs B8 2,664,000（减少约67.29%）；RI 104 vs105；这些计数不代表完整端到端成本。

离线 missed escalation 为2100/5760，按有限参考 margin<0 且未提交 RI 定义，不等于2100个确定存在更好 RI 结果的门控误判。

### Section 7–8：结论边界

未扩大 claim 至 full-class recoverability 可直接验证、精确升级时机、未见数据泛化、真实部署总成本或多重比较整体显著性。结论维持相对固定身份基线的优势、与B8差值跨零及显著减少模型级搜索工作量的**受限结论**。

## 编译和图表验收

- IEEEtran 两轮 `pdflatex` 成功：**9 pages**。
- **3张图全部有实际PDF嵌入**：Fig.1 位于第5页；Fig.2、Fig.3 位于第7页。图片与正文没有宏替换伪影。
- **4个表**：Table I 方法、Table II 主结果、Table III 动作行为、Table IV 场景。
- 标签唯一，所有 `\\ref`/`\\eqref` 以及24条 `\\cite` 已解析；`\\bibitem` 顺序与首次引用相同。
- 无 LaTeX Error、无 undefined citation/ref、无 overfull box；存在一般性的 underfull spacing 提示。
- 第7页为 Fig.2 / 主结果表 / Fig.3 集中浮动页，是 IEEEtran 的自然浮动结果，内容清晰且未溢出，但目标期刊定版时可重新优化浮动布局。
- Fig.1 是用户提供的**嵌入栅格 PDF**，并非矢量可编辑；Fig.2/3 为文本/图形矢量 PDF。

## 最后两项须作者确认的问题

1. **Fig.1 的 RI 分支入线歧义（科学可视化问题）**：最新提供的图在下方 lifecycle update 中写明了 RI→reset history 且两分支均指向 next stage；但来自 Commit Selected Action 的独立连接到 RI 框**不够明确**（已做局部放大检查）。这不影响正文算法的明确规则，但在声称“图示连线完全正确”之前应对图做一次定点矢量修线。本次尊重用户要求，三个图均按提交原样嵌入，未擅改。
2. **作者与投稿格式**：`main.tex` 中作者为占位。不能从另一篇论文推断第三篇作者、通讯作者及单位，需作者明确确认后填入。IEEEtran journal 模式属于可编译审校基线，投稿具体格式须根据目标期刊调整。

## 交付来源与可核验范围

正文统计依据此前用户提供并由 Codex 封存的 `PAPER3_FINAL_VERIFIED_HANDOFF.md`。本轮独立核验 PDF/LaTeX 文件结构、三份上传图字节、正文统计文字、引用次序与可见排版；**没有重放用户本地原始1200轨迹或重新运行Bootstrap**，因此不冒充对完整原始实验数据的再次第三方认证。
