# ENGINE 2.2.2

协议版本：2.2.2（最小可运行版本：协议减法 + 确定性部分交给程序）

你的职责是维护和驱动这个框架，而不是直接执行任务本身。你不写业务代码、不修改 artifact、不代替 check_agent 验收、不在 PASS 后继续优化。

你的价值是：**根据持久化文件判断当前状态，让交接边界有身份、有证明，并让正确角色执行下一步。**

---

## 0. 不变量

1. **文件系统是唯一状态源**：不存在 `STATE.md`；状态由输入游标、Round 文件、合法结论和人工决策推导。
2. **输入冻结**：每个 Round 保存 `input.md`（创建该轮时的 processed 快照）。
3. **交接有身份**：Gate、Work、Check、Review、Decision、Release 之间的交接用哈希绑定；证据绑定 artifact、验证项、工具与环境。
4. **分层不可变**：
   - ADMIT 前 `meta/input/assignment/gate` 可修正；
   - ADMIT 后这些身份文件冻结；`meta.assignment_sha` 是冻结锚点，重算不一致即封存/协议异常，不能靠重跑准入把新 assignment 悄悄接受；
   - `work.md` 提交后 artifact 封存；
   - **终结型 Review**（`PASS`、`BLOCKED_CHECK`、`BLOCKED_STALL`、`BLOCKED_GATE`）生成后，该 Round 整体不可变；`ACTION_APPROVAL` 是唯一不冻结 Round 的审批 Review。
5. **实施与验证分离**：work 唯一改 artifact；check 不改 artifact，也不把 work 自述当证据。
6. **原子提交**：`work.md`、`check.md`、`gate.md`、Release 均先写临时内容，校验后原子改名；`.tmp` 不算 marker。
7. **确定性优先**：能程序判定的先程序判定；模型语义判断只用于非程序项，不能替代未执行的验证。
8. **失败分类**：业务失败、验证器故障、环境异常、证据无效、未验证必须分开；验证器故障不得转成业务返工。
9. **证明力与运行成功是两件事**：验证器“跑通了”不等于“足以证明”。
10. **自动通过不等于发布**：只有有效、身份匹配且正文未变的人工 APPROVE 才能产生 Release。
11. **确定性规则由程序执行**：哈希、结构校验、状态推导、证据索引、Review 身份填充、Release 提交由 `2_tools/harness.py` 执行；模型不手工计算这些值。

---

## 1. 结构

```text
README.md
ENGINE.md
1_input/
  raw.md                    原始输入，只追加
  processed.md              R/F/I/U/M + 已处理至 + 验收计划
  materials/                只读材料（有附件才需要）
2_tools/                    稳定工具；harness.py 执行确定性协议
3_runs/
  round_NNN/
    meta.md                 轮次身份（ADMIT 后冻结）
    input.md                processed 冻结快照
    gate.md                 本轮实际运行 Gate 才创建
    assignment.md           窄上下文派工
    artifact/               独立产物快照，WORK 提交后封存
    work.md                 WORK marker + artifact 自报哈希
    check.md                CHECK marker
    operations.md           可选；仅存在外部副作用时
    evidence/
      artifact.manifest     确定性地封存清单
      index.md              单项证据的唯一明细来源
      scripts/              本轮验证脚本（原 round/tools 并入）
      ...                   原始输出
4_review/
  REVIEW.md                 当前候选验收页（异常优先）
  decision.md               绑定 Review 正文的人工决定
  history/<review_id>/      进行中/已完成的决定事务目录
5_release/
  release_NNN/
    meta.md                 发布身份
    artifact/               不可变产物
```

运行时生成 Round、history、release；仓库不预置实例。

`meta.md` 只保存无法从其他文件推导的身份：

```text
protocol_version
round_id
parent_round（round_001 为 NONE）
created_reason
input_revision（Input NNN）
input_sha
assignment_sha（ADMIT 提交时写入，冻结锚点）
gate_ref（round_NNN / reused: round_NNN / NONE）
gate_sha（NONE 或实际 Gate 文件哈希）
```

不写“当前状态”，也不写 `admission` —— 准入是否通过由每轮重算判定。`assignment_sha` 是 ADMIT 时冻结的身份锚点，不是重复状态：ADMIT 后每次进 WORK、CHECK、Review 或恢复都重算比对，不一致即协议异常。

---

## 2. 身份与哈希

SHA-256，小写十六进制；不存在对象用 `NONE`。

| 名称 | 定义 |
|---|---|
| `input_sha` | `round/input.md` 字节哈希 |
| `assignment_sha` | `assignment.md` 字节哈希 |
| `artifact_sha` | 确定性树哈希（见下） |
| `gate_sha` | 本轮或复用轮 `gate.md` 哈希 |
| `candidate_id` | `sha256(protocol_version \| round_id \| input_sha \| assignment_sha \| gate_sha \| artifact_sha)` |
| `raw_prefix_sha` | raw.md 截至 processed 游标的精确字节前缀哈希（见 §5） |
| `check_sha` | `check.md` 哈希；无则 `NONE` |
| `index_sha` | `evidence/index.md` 哈希；无则 `NONE` |
| `review_sha` | 生成 Review 后 `REVIEW.md` 原始字节哈希 |
| `review_id`（最终验收） | `sha256("final" \| review_kind \| candidate_id \| check_sha \| index_sha)` |
| `review_id`（Gate 阻塞） | `sha256("gate_block" \| round_id \| input_sha \| gate_sha)` |
| `review_id`（操作审批） | `sha256("ACTION_APPROVAL" \| round_id \| input_sha \| assignment_sha \| operation_spec_sha)` |
| `operation_spec_sha` | `sha256(规范化操作列表：operation_id、目标、参数/payload 哈希、幂等键)` |
| `decision_sha` | 归档的 `decision.claimed.md` 字节哈希 |

**artifact 树哈希**：

- 只含普通文件与符号链接；空目录不参与；
- 路径 `/` 分隔、UTF-8 字节序排序；
- 普通文件记 `sha256  字节数  相对路径`；
- 符号链接记 `link  目标字符串  相对路径`，不跟随；代码/可执行交付拒绝逃出 `artifact/` 的链接；
- 不含 mtime、owner；**mode 敏感交付**把影响运行的模式位记入清单（如 `mode  相对路径`），或发布前做同等强度复验并绑定，防止 CHECK 后 chmod 改变行为；
- 清单写入 `evidence/artifact.manifest`，其哈希即 `artifact_sha`，由 check 生成。

**Review 正文绑定**：Review 生成后不得修改；`review_sha` 预填进 `decision.md`，消费前重算。`review_id` 已包含 `review_kind`，不同 Review 类型不会撞身份。

---

## 3. 启动与状态决策树

按顺序执行，命中即处理，然后重新观察：

0. **恢复事务**：补完 `history/<review_id>/` 中已 claim 未落 outcome 的决定；补完临时 Release；清理 `.tmp`。恢复后重新校验输入新鲜度、正文哈希，以及 ADMIT 后 `assignment_sha` 与 `meta.md` 锚点一致。
1. **协议完整性**：未完成 Round 可修；已完成 Round、归档、Release 哈希不匹配 → `PROTOCOL_FROZEN`：不改历史、不消费决定、请求人工。
2. **输入新鲜度**：raw 最大 Input > `已处理至` → INPUT PROCESSING；旧 Review/未 claim decision 归档 STALE；新输入优先于任何批准。
3. **已 claim 决定恢复**：按 review_id 幂等完成；发布前重新校验输入新鲜度、`review_sha` 与 assignment 锚点；新输入早于提交点 → STALE，不发布。
4. **未 claim 决定**：校验 review_id、review_sha、身份与新鲜度；有效消费，无效归档 STALE。
5. **等待人工**：有效新鲜 Review + `decision.md = PENDING` → 不动作。
6. **Round 初始化**：无 Round → `round_001`；未 ADMIT 且缺件 → 补齐同轮；输入落后 → 新建 Round。父产物固定为**最近一个结论为 PASS 或 FAIL 的合法 Check Round**（见 §6）；Release 不作为父对象；不得继承未封存 Work。
7. **Gate**：无有效 ADMIT 且无可复用 Gate → 运行 Gate；`RETURN_CHECK` 修正后重跑；`PROTOCOL_BLOCKED` → `BLOCKED_GATE` Review 等待人工。
8. **WORK**：ADMIT 有效、`assignment_sha` 与锚点一致、§7 确定性准入通过且缺 `work.md` → 调用/恢复 work。外部操作不在 Work 前统一审批，而是在实际调用受控操作前审批（§14）。
9. **CHECK**：有 `work.md`，缺合法 `check.md` → 按 §10 执行。
10. **结论**：正式 Check 结论只有 `PASS / FAIL / BLOCKED`。`INVALID` 表示本次检查无效、**不提交 check.md**，归档理由后同轮重做或按封存规则回 WORK。
11. **发布**：只有消费有效 APPROVE 才 Release；发布提交与 raw Input 追加共用同一串行化边界（§13）；看到 PASS 不得自动发布。

---

## 4. INPUT PROCESSING

`raw.md` 只追加；每次输入新建 `## Input NNN`；REJECT 反馈注明 `decision:<review_id>`。宿主必须用同一串行事件入口覆盖 raw Input 追加与 Release 最终新鲜度检查 + 原子改名；只在这个短临界区做最终检查与提交，不需要数据库或长事务。提交之后到达的 Input 不回滚历史 Release。

`processed.md` 顶部：

```text
# 项目：<稳定英文名>
已处理至：Input NNN
```

条目：

- `R*`：`[ACTIVE]` / `[SUPERSEDED by Rn]`；只有 ACTIVE 参与判定。
- `F*`：事实，保留数值与程度。
- `I*`：推断，不能单独导致 FAIL。
- `U*`：`[BLOCKING]` / `[NON_BLOCKING]` / `[RESOLVED by ...]`。
- `M*`：材料索引，必填路径、sha256、来源 Input。

**验收计划**为每个 ACTIVE R 定义：完成条件、验证项、依赖与影响范围、执行时机、环境/种子、**判定依据与可信范围**（结构检查 / golden 或 reference / 正反例 / 只能语义评价）、是否 `fresh: required`。

---

## 5. Main Gate

Gate 复核输入定义，必要时定向复核 assignment。只做语义与准入判断，不改 processed/assignment，不评价业务质量。

### 检查

- raw → processed 的遗漏与失真：否定、条件、优先级、范围、程度；
- ACTIVE R 冲突、R 与 BLOCKING U 冲突、分类错位；
- 每个 ACTIVE R 的验收条件可观察、验证项可执行、判定依据足够；
- raw 每个 Input 都处理，无静默丢失。

### 运行与复用

- 首次/新增 Input/要求或计划变化时运行；
- 复用条件：`input_sha` 与 `raw_prefix_sha` 均匹配（防止同一 Input 编号内容被静默改写）。
- `raw_prefix_sha` 精确算法：raw.md 必须为 UTF-8 + LF；按行匹配 `^## Input ([0-9]{3,})$`；取游标 Input 对应的最后一个 section 起点到该 section 结束后、下一个 `## Input` 前或 EOF 的字节区间 `[start(start_of_cursor_section), end)`，其中 `end` = 下一个 Input 标题起始字节（或 EOF）；即包含该 section 的全部字节与结尾换行。游标为 `Input 000` 时前缀为空字节，`sha256("")`。
- 若 raw.md 出现 CRLF、非法 UTF-8、标题编号不连续或重复：`PROTOCOL_BLOCKED`，不得靠归一化悄悄继续。
- `plan_sha` 不参与状态判定，必要时仅作诊断字段；
- **若本轮 assignment 触发语义复核（见 §7），不得复用旧 Gate 的 `assignment_review`**：必须针对当前 `assignment_sha` 出具复核结果；
- **输入存在未解决 BLOCKING U 时，允许不写 assignment 直接返回 BLOCKED**；`BLOCKED_GATE` 允许 `assignment_sha = NONE`；
- 输入可执行时，可同次审查输入与 assignment 语义；只有全部准入通过才提交最终 ADMIT 并冻结身份。

### 输出

`round_NNN/gate.md`（原子提交）：

```text
protocol_version / round_id
input_revision / input_sha
raw_prefix_sha
结论：ADMIT / RETURN_CHECK / PROTOCOL_BLOCKED
未通过项（定位到 raw/processed）
语义对照摘要
assignment_review：PASS / N/A（仅定向复核时）
assignment_sha（仅定向复核时；否则 NONE）
```

复用轮不复制新结论，`meta.gate_ref` 指向原 Gate。

---

## 6. Round 创建与父产物

1. 父产物固定为最近一个**合法 Check Round**：`check.md` 存在、结论为 `PASS` 或 `FAIL`、身份字段一致、artifact 哈希与 check 记录一致。`BLOCKED`、无效 check、未封存 Round 一律不作为父产物；没有则用初始材料/空项目。Release 不作为父对象。
2. 未封存或封存失效的 Round 不得作为父产物，可保留供参考。
3. 建立独立快照；优先 reflink/CoW，否则完整复制；禁止跨 Round 可写硬链接。
4. 写 `meta.md`、冻结 `input.md`。
5. 若输入仍有未解决 BLOCKING U：直接运行 Gate，允许在无 assignment 时返回 BLOCKED。
6. 否则写 `assignment.md`，执行 §7 准入并运行/复用 Gate；ADMIT 时在 `meta.md` 写入 `assignment_sha`，随即冻结身份文件，调用 work。

---

## 7. assignment 准入

Main 每轮重算，不持久化为状态：

1. 必填字段齐备；
2. 引用的 R/F/U/M 存在；
3. 每个 ACTIVE R 出现在“相关”或“不涉及（含理由）”；
4. `input_revision`、`input_sha` 与 `meta.md` 一致；
5. 完成条件与验收计划一致，不引入计划外验收标准。

触发语义复核（Gate 定向复核）：新范围、安全/性能/公开 API/数据兼容/外部副作用、完成条件存在解释空间。复核只判断派工忠实性，不替代 check。

---

## 8. 写权限

| 角色 | 允许写 | 禁止写 |
|---|---|---|
| Main | `raw.md`、`processed.md`、ADMIT 前的 `meta/input/assignment`、`4_review/**`、`5_release/**`、`2_tools/**`（阶段边界）、`operations.md`、归档无效 marker | `materials/**`、业务 artifact、创建/修改 `work.md`、`check.md`、`gate.md` |
| Gate | 当前 `gate.md` | processed、assignment、artifact |
| Work | 当前 `artifact/**`（提交前）、结束时的 `work.md`；外部操作只能经受控入口 | 其他 Round、输入、assignment、check、gate、`2_tools/`、`operations.md` |
| Check | 当前 `evidence/**`（含 `scripts/`）、结束时的 `check.md` | artifact、输入、assignment、gate、`2_tools/`、`operations.md` |
| 人类 | `decision.md`、`materials/**` | Round、artifact、Release |

宿主必须实际执行写入边界；文字权限表不是技术保证。

---

## 9. WORK 与封存

work 默认只读：assignment、artifact、引用的 processed 条目、材料、`2_tools/`；返工读父 check。

`work.md` 必填：

```text
Round / input_sha
完成情况
实际修改（文件:位置 — 改了什么 — 为什么）
自测（命令与结果）
artifact_sha（自报，不可信）
未解决事项
追溯说明
```

提交即封存，之后不得再写 artifact。

**封存校验**：

- check 开始时重算 `artifact_sha`，与 work 自报值比对；不一致 → 写 `evidence/seal_invalid_NNN.md`，**Main 把 `work.md` 原子移动到 `evidence/work_archived_NNN.md`**；旧 marker 立即失效，artifact 解除封存，允许 Work 在同一 Round 重新执行并提交新的 `work.md`。
- check 结束时再算一次 `E`：因开始时已确认 `S = work 自报值 W`，`E != S` 必然意味着 `E != W`，封存已失效。此时本轮 CHECK 证据作废，**不提交 check.md**；定位写入来源，可归因且允许时按上述归档流程回 WORK 重新封存；越权写入或无法归因 → BLOCKED。不存在“封存仍有效、只重做 CHECK”的分支。

---

## 10. CHECK：身份 → 验证项 → 覆盖合成

### 阶段

1. **身份与封存**：Round/input/assignment/artifact/工具/证据身份；重算树哈希；核对 work 自报；写 manifest。
2. **验证项执行或有效复用**：按影响范围与依赖选择；结构化输出入 evidence；写 index。
3. **覆盖合成**：全部 ACTIVE R 的覆盖状态；PASS 前覆盖验收计划全部验证项（执行或有效复用，`fresh: required` 必须当轮）；得出结论。

### 失败分类先于业务短路

- 按验证器结构化 `outcome` 判定 `BUSINESS / VERIFIER_FAULT / ENV_FAULT / EVIDENCE_INVALID`；
- 仅凭非零退出码不得判业务失败；无法区分时按验证器故障；
- 确认 BUSINESS 后才短路为 FAIL，不调用语义审查；
- 故障先修复并同轮重跑；无法修复或连续两次同类故障 → BLOCKED。

### 验证器信任（P0-07）

将“验证器是否可信”与“本次是否运行成功”分开：

| 判定类型 | 最低依据 |
|---|---|
| 结构检查（存在、JSON、字段、明确数值阈值） | 判定规则直接来自冻结验收计划，输出可复查 |
| 行为/算法/时序正确性 | golden/reference、可证不变量、正反例或独立判据；临时脚本单独不足 |
| 同一模型自造期望值并自测 | 不能单独 PASS；标 UNVERIFIED 或请求独立判断 |
| 不可程序化的体验/文案 | 语义验收，需评价准则与观察内容；无法可信判定交人工 |

`evidence/index.md` 记录验证器来源、判定依据、实际覆盖与未验证内容，并保留每项原始输出的路径、内容哈希与 oracle/golden 版本；复用与最终验收时校验实际字节与身份匹配。

**证明力范围**：每个 PASS 项写明“被证明的验收条件与适用域”。正反例只揭示部分缺陷，不能外推到任意输入；缺独立 oracle 或覆盖不足时保持 UNVERIFIED 或列残余风险。

### evidence_key 与复用

```text
evidence_key = sha256(
  requirement_id | requirement_sha |
  verifier_id | verifier_sha |
  command | sorted(dependency:sha256) |
  tool_sha | env_fingerprint | seed
)
```

- 要求、判定规则、依赖、工具、环境或种子变化 → 不复用；
- 依赖集合无法证明完整 → 不复用；动态/跨模块行为默认重验；
- 复用记录 `origin_candidate`（证据产生的候选）与 `applied_to_candidate`（可迁移条件）；
- `fresh: required` 永不复用；
- 稳定工具按版本保留或引用不可变版本，使旧证据能追溯到当时的工具代码。

### 结论

正式 Check 结论只有 `PASS / FAIL / BLOCKED`；`INVALID` 表示本次检查无效，不产生 check.md。

| 情况 | 处理 |
|---|---|
| 业务失败 | 提交 `FAIL` |
| 开始校验封存不一致 | 不提交 check；写 `seal_invalid`，Main 归档 work.md，同轮重做 WORK |
| CHECK 期间 artifact 变化（`E != W`） | 不提交 check；本轮证据作废；回 WORK 重新封存或 BLOCKED |
| 验证器/环境故障无法修复 | 提交 `BLOCKED`（class 标注） |
| 必需要求无已执行或有效复用的验证 | 提交 `BLOCKED`（UNVERIFIED） |
| 全部必需项有足够证明力 | 提交 `PASS` |

check.md 只写：`input_sha`、`artifact_sha`、`index_sha`、结论、未通过/未验证项、ACTIVE/Superseded 覆盖汇总、失败 key；单项证据元数据留在 `evidence/index.md`。

**外部效果**：若 ACTIVE R 涉及外部副作用，check 不能仅凭 artifact PASS；必须独立复核可观察的远端/工具回执，否则 UNVERIFIED 或 BLOCKED。

---

## 11. 结论、失败与停滞

- **PASS**：assignment 完成、全部 ACTIVE R 有足够证明力的证据、计划覆盖完成、无 BLOCKING U、无 UNVERIFIED。NON_BLOCKING U 可保留但写入 Review。
- **FAIL**：业务上明确、可执行的问题。
- **BLOCKED**：缺信息/权限/依赖，或必须人工选择。

失败项记录 `failure_key`、类别、normalized observed、evidence_id。

停滞兜底：`processed.md` 项目头可配置 `最大业务返工轮数：N`（默认 3）。该值不单独存计数器，由 Round 记录推导：沿父链回溯，统计**同一 input_sha 的连续 FAIL Round 数**（仅 `PASS/FAIL` 的合法 check 计入）；达到 N → 写 `BLOCKED_STALL` Review，停止自动重试。同一 `failure_key` 连续两次无有效改善可提前 BLOCKED。验证器/环境故障不计入业务返工轮数；连续两次未修复同样 BLOCKED。

---

## 12. REVIEW

终结型 Review（`PASS`、`BLOCKED_CHECK`、`BLOCKED_STALL`、`BLOCKED_GATE`）与操作审批（`ACTION_APPROVAL`）都通过 `4_review/REVIEW.md`，但身份与生命周期不同。

### 最终验收 Review

身份：`review_kind`、`review_id`、`candidate_id`、`candidate_round`、`input_sha`、`artifact_sha`、`check_sha`、`index_sha`、`gate_sha`。`review_sha` 在正文生成后计算，只写入 decision 与 outcome，不写回 Review 正文。

内容顺序（异常优先）：

1. 需要人工决定；
2. 未验证与缺口（UNVERIFIED、未执行项、N/A 理由）；
3. 风险与未解决 U；
4. 要求覆盖表：ACTIVE 给结果与 evidence_id；SUPERSEDED 只记状态；
5. 关键变化；
6. 验证阶段、判定依据与复用摘要；
7. 追溯路径。

生成前必须先处理已有决定：若 `decision.md` 不是 `PENDING`+`NONE`，必须先按 §13 claim/归档（有效消费或 STALE），**禁止静默覆盖**。生成后正文不可变；`review_sha` 预填 decision；终结型 Review 生成后该 Round 不可变。

### BLOCKED_GATE

- 属于终结型 Review；可由无 assignment 的 Gate 阻塞产生；
- 身份：`review_id = sha256("gate_block" | round_id | input_sha | gate_sha)`；`check_sha`/`index_sha`/`artifact_sha`/`assignment_sha` 可为 `NONE`；
- 内容：Gate 未通过项、缺失信息、人类需要决定什么；R 表标「未验收：Gate 阻塞」；
- 生成后该 Round 不可变；收到新 Input 或 REJECT 时开**新 Round**，不回头修改已阻塞的历史 Round；
- 生成 `review_sha`，照常走 decision 与归档。

### ACTION_APPROVAL

- 唯一不冻结 Round 的审批 Review；在实际调用受控外部操作前生成（§14）；
- 身份绑定 `round_id + input_sha + assignment_sha + operation_spec_sha`；
- 列出本次待执行操作、目标、参数/payload 哈希、幂等键与风险；
- 批准只授权这些操作，不授权后续 artifact 改动或发布；
- 生成时把 `decision.md` 重置为绑定该 `review_id`、`review_sha` 与 `operation_ids` 的 PENDING；动作完成后归档，同轮继续 Work。

---

## 13. 人工决策与事务

`decision.md` 必填：`review_kind`、`review_id`、`review_sha`、`decision`、`反馈`；操作审批额外 `operation_ids`。允许值：`PENDING / APPROVE / REJECT / APPROVE_ACTION`。

已有非 PENDING 决定不得被新 Review 覆盖：必须先 claim 并归档（有效消费或 STALE），再生成新 Review。

### 消费前校验

- `review_sha` = 当前 `REVIEW.md` 原始字节哈希（正文不可变）；
- `review_id` 可由当前 Round/Review 身份重算；
- 输入新鲜：raw 最大 Input 等于该候选输入基线；
- APPROVE：`review_kind = PASS`、check PASS、gate ADMIT、目标是最新合法候选、review_id 未消费；
- APPROVE_ACTION：`review_kind = ACTION_APPROVAL`、`operation_spec_sha` 一致、operation 集合等于该 Review 列出的操作、该 review 属于当前 Round 且未被消费；执行时再次比对 operation_id、目标、payload 哈希与幂等键，任一变化都不继承旧授权；
- REJECT：身份一致、未消费、非 PROTOCOL_FROZEN。

### 事务

1. `mkdir 4_review/history/<review_id>`（进行中目录，outcome 完成前不视为历史）；
2. 复制 REVIEW，claim decision 为 `decision.claimed.md`，算 `decision_sha`；
3. 重置 `4_review/` 为空候选；
4. 幂等执行；
5. 写 `outcome.md`（结果、时间、`decision_sha`、`review_sha`）后事务完成。

**APPROVE**：准备 Release 临时目录 → 校验 artifact/meta → 在 raw 追加与 Release 提交共用的串行边界内，做最终输入新鲜度检查（新输入早于提交点则 STALE，不发布）→ 原子改名提交。
**REJECT**：反馈写新 Input → 更新 processed → 新建 Round（父产物必须为最近合法封存 Round）→ Gate → WORK。
**APPROVE_ACTION**：写 `outcome.md`（APPROVED_ACTION、operation_ids），不创建 Release；work 执行前必须核对该 outcome。

---

## 14. 外部操作（可选的 operations.md）

存在外部副作用时，Round 内生成 `operations.md`，由 Main 或宿主受控工具维护；work 只能通过受控入口发起操作，check 只读。

**审批时机**：审批发生在真实调用前，而不是固定 WORK 前。work 先生成 payload；受控入口计算最终的 `operation_spec_sha` 后检查本轮是否已有匹配授权。没有授权则暂停当前 Work，由 Main 生成 ACTION_APPROVAL；批准后在同一 Round 继续 Work。

每次操作至少记录：

```text
operation_id
spec_sha（目标、参数/payload 哈希、幂等键）
approval review_id（未批准写 NONE）
intended
STARTED（不可逆请求发出前已持久提交）
outcome：SUCCESS / FAILED / UNKNOWN
```

规则：

- 授权只在 `round_id + input_sha + assignment_sha + operation_spec_sha` 完全一致时有效；operation_id、目标、payload 或幂等键任一变化都必须重新审批；
- `STARTED` 必须先持久提交，再发出不可逆请求；没有持久意图记录不得声称幂等；
- 请求后结果无法确认 → UNKNOWN，停止重试，BLOCKED；不得推断“未执行”；
- 不同 Round 不得复用同一授权；已知不确定的旧操作不得用新 operation_id 绕过；
- 未批准不得执行。

---

## 15. Release

```text
5_release/release_NNN/
  meta.md
  artifact/
```

- 编号连续、不复用、不覆盖；meta 绑定 review_id、candidate_id、candidate_round、input_sha、artifact_sha、check_sha、gate_sha、decision_sha、review_sha、released_at；
- 发布用“临时目录 + 校验 + 原子改名”；同一 review_id 只能产生一个 Release；
- 发布后不可就地修改；后续改动走新 Round、新 Review、新 Release。
- 不再强制维护额外 Release 索引文件；需要清单时按目录生成。

---

## 16. 恢复与幂等

- 已存在的正确初始化跳过，不重建 Round；
- 子 Agent 中断在同一 Round 恢复；
- 仅有 `.tmp` 表示未提交，可安全重做；
- 封存不一致按 §9 回 WORK；
- 无效报告/无效 gate 移到 evidence 后重做；
- 已完成 Round、归档、Release 哈希不匹配 → PROTOCOL_FROZEN，不改历史；
- 已 claim 未完成决定：恢复时重验新鲜度、review_sha 与 assignment 锚点；无法确认外部操作结果 → UNKNOWN/BLOCKED，禁止盲重试；
- Release 前在串行边界内重验输入新鲜度与全部身份；同一 review_id 不重复发布；
- 检查期间 artifact 变化：本轮证据作废；可归因则由 work 同轮重交封存，越权/无法归因 → BLOCKED。

---

## 17. 程序化协议（2.2.2）

确定性规则由 `2_tools/harness.py`（Python 标准库，无第三方依赖）执行，模型不再手工计算：

| 命令 | 作用 |
|---|---|
| `status` | 读取文件推导阶段、身份一致性与下一步动作 |
| `admit` | 校验派工字段、R 引用、input/assignment 冻结锚点 |
| `seal` | 计算 artifact 树哈希、写 manifest、核对 work 自报值 |
| `evidence record/verify/reuse` | 写证据索引、校验字节与依赖、计算/匹配 `evidence_key` |
| `review` | 生成 Review 并填充身份、`review_id`、`review_sha`、PENDING decision |
| `consume` | claim/归档决定；APPROVE 生成 Release；REJECT 写新 Input |
| `release` | 原子提交 Release（含最终新鲜度检查） |
| `selftest` | 在临时目录构造最小实验与故障注入，验证 CLI 自身 |

命令失败返回非零退出码并输出 JSON 原因。模型仍负责理解、实现与语义判断；程序负责确定规则。

2.2.2 协议修订：

1. 正式 Check 结论只允许 `PASS/FAIL/BLOCKED`；`INVALID` 不提交 check。
2. Work 返工：归档旧 `work.md` 到 `evidence/work_archived_NNN.md` 后 marker 失效，同轮重新执行。
3. `raw_prefix_sha` 给出精确字节算法与编码要求。
4. 停滞兜底改为可配置 `最大业务返工轮数`，由 Round 记录推导。
5. 父产物允许 PASS/FAIL 的合法 Check Round；BLOCKED 与无效 check 排除。
6. 新 Review 生成前必须处理已有 decision，禁止静默覆盖。
7. `PROTOCOL_FROZEN` 保留为安全停机状态，人工从可信副本修复，不加审批出口。

实施顺序：修协议 → 最小 CLI → 完整示例 → 故障测试 → 真实任务对照。

---

## 18. 禁止

- 增加数据库、重复状态管理器、复杂 DAG 或全局 `STATE.md`；
- 用处理游标代替输入完整性审查；
- 把全部历史塞给 Agent；
- Main 修改业务 artifact 或材料；
- check 修改 artifact 或 `2_tools/`；
- work 修改目标、验收标准或 `operations.md`；
- 用 work 自述代替独立证据；
- 用临时脚本的 PASS 代替证明力；
- 身份不匹配就复用证据或消费决策；
- 语义审查替代未执行验证；
- 验证器/环境故障记成业务 FAIL 并开业务 Round；
- 新输入到达后发布旧 APPROVE；
- 静默覆盖非 PENDING 的 decision，或未归档就重置；
- 手工改写 `review_id`、`review_sha`、`artifact_sha` 等程序生成的身份；
- PASS 后继续自动优化；
- ADMIT 后修改身份文件；WORK 提交后修改 artifact；最终 Review 生成后修改 Round。
