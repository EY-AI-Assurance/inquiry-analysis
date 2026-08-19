# SEC × IFRS 18 融合参考库

本文档融合IFRS 18官方条款（来源：IFRS Foundation HTML标准全文）与真实SEC Comment Letter案例（来源：EDGAR公开函件，159封筛查/4家公司/7案例点），为审查链提供条款级依据。

---

## 第一部分：IFRS 18 核心条款索引

### 1. 三分类体系（§47-68）

| 类别 | 段号 | 定义 | 关键判断 |
|------|------|------|---------|
| **Operating** | §52 | 残差类别——不属于investing/financing/tax/discontinued的所有收入和费用 | 主要业务活动产生的收入和费用归入此类 |
| **Investing** | §53-58 | 投资联营/合营/非合并子公司、现金及等价物、独立回报资产 | §55 override：若投资系主要业务活动，非权益法投资收入归入operating |
| **Financing** | §59-66 | 仅筹资交易产生的负债相关费用 | §65 override：若向客户融资系主要业务活动，相关费用归入operating |
| **Income taxes** | §67 | IAS 12所得税及相关汇兑差额 | — |
| **Discontinued operations** | §68 | IFRS 5终止经营 | — |

**保险融资收入/费用特殊处理（§64）：** IFRS 17下的保险融资收入/费用归入operating而非financing。这意味着保险负债重估损益属于operating category——排除出Adjusted EBITDA等于从operating中移除。

### 2. 三个法定小计（§69-74）

| 小计 | 段号 | 构成 |
|------|------|------|
| **Operating profit or loss** | §70 | operating类别全部收入和费用 |
| **Profit before financing and income taxes** | §71 | Operating profit + investing类别全部收入和费用 |
| **Profit or loss** | §72 | 全部类别收入减费用 |

**§73例外：** 若企业采用§65(a)(ii)将部分融资相关收入/费用归入operating，则不得列示"profit before financing and income taxes"，但可列示operating profit之后的额外小计（§24）。

### 3. MPM定义与披露（§117-125）

**MPM定义（§117）：** 同时满足以下条件的收入和费用小计——(a)在财务报表外公开沟通中使用；(b)传达管理层对整体财务业绩某一方面的观点；(c)不属于§118列示的IFRS规定小计（operating profit、profit before financing and income taxes、profit等）。

**MPM披露要求（§119-125）：**
- 集中在**单一附注**披露
- 与**最直接可比IFRS小计**对账（通常为operating profit）
- **逐项**解释每一调节项如何反映管理层观点
- 分配**税务影响**和**非控股权益影响**
- 说明MPM对投资者的**有用性**（定性解释）
- 披露MPM定义的**变更**
- **比较信息**需重述（§31-33）

### 4. 经营费用分析（§78-85）

**列示方法（§78-79）：** 按性质法（nature）、功能法（function）或二者混合列示。每一条目仅按一种基础聚合，但不同条目可用不同基础。

**性质法（§80）：** 按消耗的经济资源性质分类——原材料、员工福利、折旧/摊销等。

**功能法（§81-85）：** 按活动分类——如cost of sales。若采用功能法：
- §82：须列示cost of sales条目
- §83：须在**单一附注**中披露按性质法的费用总额：折旧、摊销、员工福利、减值损失/转回、存货跌价/转回
- §83(b)：每个总额需说明与operating类别各条目的关系

### 5. 异常损益（§49）

IFRS 18要求标识"异常损益"（unusual income and expenses）——具有有限预测价值、有助于理解报告期业绩的项目。但IFRS 18**不定义"异常"**——留管理层判断。

**与SEC交叉：** SEC的C&DI 102.03禁止将重复性项目标为"non-recurring"。IFRS 18 §49的"异常"判断与SEC的"non-recurring"判断标准可能不一致——企业需同时满足两套规则。

### 6. 拆分原则（§41-45）

- §41(a)：按共享特征聚合
- §41(b)：按非共享特征拆分
- §41(c)-(e)：不得掩盖重大信息
- §42：重大项目必须拆分——若主表未列示则须在附注中披露
- §43：标签须faithfully represent项目特征

### 7. 比较信息与过渡（§31-40, Appendix C）

- §33：列报/分类变更时须重分类比较信息（除非不可行）
- §37-38：追溯适用时须列示第三张财务状况表（期初）
- 生效日期：2027年1月1日，允许提前采用，追溯适用

---

## 第二部分：SEC Comment Letter 真实案例（按审查环节索引）

### 案例索引

| 公司 | 年份 | 指标 | 核心问题 | IFRS 18交叉 | 强度 |
|------|------|------|---------|------------|------|
| Grab | 2021 | Adjusted EBITDA | 突出程度、对账方向、预测命名 | §69 法定小计优先 | 中 |
| Uber | 2019 | Adjusted EBITDA | "non-routine"标签矛盾 | §49 异常损益定义 | 中 |
| Uber | 2020 | Segment Adj. EBITDA | 分部已不成立 | IFRS 8 + §117 | 低-中 |
| Uber | 2023 | Adjusted EBITDA | "certain"筛选不透明 | §41 不掩盖原则 | 中-高 |
| Lyft | 2022-23 | Adj. EBITDA/Contribution | 历史保险改变确认计量 | §52 + §64 保险归operating | 高/红线 |
| Coupang | 2025 | Segment Adj. EBITDA | CODM使用及重大费用 | §78-85 费用分析 | 中 |
| Uber | 2026 | Non-GAAP Op. Income | 主动向operating income靠拢 | §70 operating profit锚点 | 战略信号 |

### Grab 2021 — 叙事顺序与对账方向

**IFRS 18交叉：** §69要求列示operating profit法定小计；§43标签faithful representation

**SEC质询：** 业务亮点先讲Adjusted EBITDA，使用"Strongest"正面定性，未同步呈现IFRS指标。对账表由非IFRS倒推IFRS。预测中"EBITDA"口径与MD&A中Adjusted EBITDA定义不同。

**整改：** 修订MD&A先陈述IFRS结果，对账方向改为IFRS→非IFRS。预测口径改名"Adjusted EBITDA (PIPE)"。

**启示：** IFRS 18 operating profit须作为每张盈利桥梁起点。同名异义须改名——MPM进入附注后提高了跨材料一致性要求。

### Uber 2019 — "non-routine"标签与重复事实矛盾

**IFRS 18交叉：** §49"异常损益"标识——IFRS 18不定义"异常"，与SEC 102.03标准可能不一致

**SEC质询：** "non-routine legal, tax, and regulatory reserves"在2017-2018连续出现，SEC引用C&DI 102.03要求删除标签。

**整改：** 删除"non-routine"措辞，但保留调整。

**启示：** IFRS 18 §49的"异常"判断须与SEC"non-recurring"标准对齐——若SEC认定不构成non-recurring，IFRS 18的"unusual"标签也可能被质疑。

### Uber 2023 — "certain"筛选规则须可审计

**IFRS 18交叉：** §41-45拆分不得掩盖重大信息；§117(b) MPM须反映管理层观点

**SEC质询：** "certain legal, tax, and regulatory reserve changes"（2021年5.26亿/2022年7.32亿），SEC要求量化三类构成并解释"certain"筛选。

**整改：** 建立两步筛选——先按事项事实判断，再对单一事项适用一致量化门槛。扩充MD&A定义。

**启示：** 每个调整类别需有纳入/排除示例和量化门槛，纳入审计委员会年度复核。

### Lyft 2022-23 — 历史保险负债调整红线

**IFRS 18交叉：** §52 operating残差类别 + §64保险融资收入/费用归入operating

**SEC质询：** "Changes to liabilities for insurance attributable to historical periods"（2.503亿美元）实质创建"只看本事故期间"的替代计量基础。SEC认定与C&DI 100.04不一致。

**整改：** 从所有非GAAP指标中删除，重列比较期。

**启示：** 保险精算重估在IFRS 18下明确归入operating category。排除出Adjusted EBITDA等于改变operating category的计量基础——双重违规（SEC C&DI 100.04 + IFRS 18 §52分类基础）。

### Coupang 2025 — 分部重大费用透明度

**IFRS 18交叉：** §78-85经营费用分析；§42重大信息拆分

**SEC质询：** CODM如何使用Segment Adjusted EBITDA？cost of sales、OGA和调整项统称"other segment items"——cost of sales显然重大。

**整改：** 按分部披露cost of sales，澄清CODM信息接收范围。保留指标。

**启示：** IFRS 18 §83要求功能法下列示须在单一附注中按性质法拆分。分部层面同理——重大费用不得埋入"other"。

### Uber 2026 — 向Operating Income锚点靠拢

**IFRS 18交叉：** §70 operating profit作为法定锚点

**演化：** Uber以Non-GAAP Operating Income取代Adjusted EBITDA，将折旧和股份支付重新纳入核心指标。从GAAP income from operations出发，仅剔除收购摊销、特定准备金、减值、重组等。

**启示：** IFRS 18提供法定operating profit锚点后，市场指标从"证明公司能产生EBITDA"升级为"解释operating profit中哪些项目不代表持续经营"。

---

## 第三部分：跨案例归纳——可信度链条

| 审查环节 | SEC风险 | IFRS 18对应 | 案例证据 | 控制动作 |
|---------|--------|------------|---------|---------|
| 法定锚点 | 非GAAP压过GAAP/IFRS | §69-74 法定小计 | Grab 2021 | 先讲operating profit及驱动因素 |
| 名称 | 同名异义 | §43 标签 + §117 MPM定义 | Grab 2021；Uber 2019 | 口径字典+受控名称 |
| 正常经营 | 剔除重复性现金成本 | §52 operating残差 + §49异常判断 | Uber 2023；Lyft 2022-23 | 按类别判断重复性 |
| 确认计量 | 改变确认计量 | §52 + IFRS 17交互 | Lyft 2022-23 | C&DI 100.04一票否决 |
| 选择性 | "certain"自由裁量 | §41-45 不掩盖 | Uber 2023 | 事实条件+金额门槛 |
| 对称性 | 只剔除损失 | §41-45 共享特征 | Coupang 2025 | 同一政策覆盖正负 |
| 分部事实 | 不对应CODM | IFRS 8 + §117 | Uber 2020；Coupang 2025 | CODM证据+重大费用 |
| 费用透明度 | 成本埋入"其他" | §78-85 经营费用分析 | Coupang 2025 | 按性质法拆分 |
| 异常标识 | "unusual"标准不清 | §49 不定义"异常" | Uber 2019 | 与SEC 102.03对齐 |

### 为什么IFRS 18后SEC审查更严格

- operating profit成为可比性更强的法定锚点——投资者更容易识别管理层是在解释还是在绕开不利结果
- MPM进入财务报表附注——"指标口径"从IR材料提升为财务报告控制问题（§119-125单一附注+逐项解释+税/NCI）
- 三分类明确——投资收益归investing、融资费用归financing、保险归operating——分类错误更容易被发现
- §49异常损益标识——但"异常"不定义，SEC可能就此与企业的判断标准质询
- SEC规则独立适用——满足IFRS 18 MPM披露不等于SEC满意

---

## 第四部分：滴滴落地框架

### 三层盈利叙事

| 层级 | 指标 | IFRS 18对应 | 定位 |
|------|------|------------|------|
| 第一层 | Operating Profit | §70 法定小计 | 核心业务是否盈利；解释收入/成本/费用驱动因素 |
| 第二层 | MPM: Adjusted Operating Profit | §117-125 单一附注 | 少量、稳定调整；逐项解释并分配税/NCI |
| 第三层 | Adjusted EBITDA | §117 MPM | 折旧摊销+资本强度；不替代operating profit |

### 调整项八问测试

详见SKILL.md环节3。每个拟调整项目必须通过八问，其中④确认计量为红线一票否决项。

### 风险地图

| 风险 | 典型项目 | IFRS 18归类 | 处理建议 |
|------|---------|------------|---------|
| 较低 | 利息、税、折旧摊销、离散交易成本 | investing/financing/operating | 标准EBITDA与Adjusted分开 |
| 中高 | 股份支付、重组、减值、收购摊销、重大法律/税务/监管 | operating | 书面政策+门槛+审计委员会复核 |
| 高/红线 | 司机/用户激励、保险及准备金发展、常规安全/合规/客服/支付；改变确认计量的"正常化" | operating (§52+§64) | 纳入核心经营；Lyft案例否决基准 |

### 治理产出

1. **盈利指标口径手册**：定义、法定起点（§70）、调节项、税/NCI影响、分部/集团关系、历史沿革、禁止用语
2. **调整项决策矩阵**：八问测试、案例证据、金额门槛、同类正常成本、对称性、审批结论
3. **跨材料一致性清单**：财务报表MPM附注、MD&A、业绩稿、路演、预算、薪酬KPI、董事会材料
4. **季度变动与重列控制**：新调整项需解释原因、量化影响、评估比较期重列（§31-33）
5. **监管预演问答**：模拟SEC追问"为什么是certain""为何不是正常经营""是否改变确认计量""收益是否同样调整""IFRS 18 §49异常标准是什么"

---

## 官方来源

- IFRS 18标准全文：[IFRS Foundation HTML](https://www.ifrs.org/content/dam/ifrs/publications/html-standards/english/2026/issued/ifrs18.html)
- SEC Non-GAAP C&DIs：[SEC Compliance & Disclosure Interpretations](https://www.sec.gov/divisions/corpfin/guidance/non-gaap-financial-measurements.htm)
- Grab：Staff 2021-09-01 | 回复 2021-09-13 | Staff 2021-10-13 | 回复 2021-10-18 | F-4/A
- Uber：Staff 2019-04-09 | 回复 2019-04-11 | Staff 2020-09-03 | 回复 2020-09-25 | Staff 2023-07-20 | 回复 2023-08-07 | 结项 2023-08-22 | 2026 8-K
- Lyft：Staff 2022-08-12 | 回复 2022-09-16 | Staff 2022-12-20 | 整改回复 2023-01-05
- Coupang：Staff 2025-06-26 | 回复 2025-07-14 | 结项 2025-07-28 | 2024 10-K
