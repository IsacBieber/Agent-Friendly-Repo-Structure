# Agent Task Harness 2.2.2 结构与运行协议报告

> 用途：供网页端 GPT 或其他外部评审者快速理解本仓库当前结构与协议。
>
> 对象：仓库当前版本（协议版本 2.2.2，最小可运行版本）。
>
> 性质：框架说明，不是具体业务任务的执行记录，也没有性能基准数据。

---

## 1. 一句话定义

**Agent Task Harness 是一套面向长程 Agent 自治任务的文件系统协议：输入、轮次、产物、证据、人工验收和发布全部落盘，状态由文件推导，交接由哈希绑定，确定性验证优先。**

不引入数据库、工作流引擎、常驻服务或额外角色。

## 2. 解决什么问题

1. 状态混乱与中断后无法恢复；
2. Main 误解需求或派工不可验收；
3. 实施者自证成功；
4. Check 慢、重复执行昂贵验证；
5. 验证器故障被误当成业务失败；
6. 验证器“跑通了”被误当成“足以证明”；
7. 外部操作批准后无法继续，或崩溃后盲重试；
8. 旧批准、旧证据、旧派工在新输入或新轮次后仍被误用。

## 3. 角色与三种证明

| 角色 | 唯一负责 | 不负责 |
|---|---|---|
| Main | 输入转写、轮次、assignment、确定性校验、调用子角色、Review、审批事务 | 改业务 artifact；替 Check 宣告 PASS |
| Gate | raw→processed 语义忠实、约束冲突、可验收性；必要时定向复核 assignment | 格式字段检查、执行测试、重写任务 |
| Work | 依 assignment 改 artifact、局部自测、提交 work.md | 改目标、正式验收、自行批准外部操作 |
| Check | 用可信依据验证、分类故障、给覆盖状态与证据 | 改 artifact、直接修业务失败、改 `2_tools/` |
| Human | 接受/退回、补需求、批准明确外部操作 | 维护内部派生状态 |

- Gate 的 ADMIT：需求转写和验收方案经过独立语义审查，不证明答案正确；
- Check 的 PASS：对当前候选、当前 ACTIVE R，用有足够证明力的依据完成计划验证；
- Human 的 APPROVE：只对特定 Review 与所见正文作出交付决定，不追认未授权副作用。

## 4. 身份链

| 名称 | 来源 |
|---|---|
| `input_sha` / `assignment_sha` / `artifact_sha` / `gate_sha` | 对应文件与确定性树哈希 |
| `candidate_id` | sha256(protocol, round, input_sha, assignment_sha, gate_sha, artifact_sha) |
| `check_sha` / `index_sha` | check.md 与 evidence/index.md；缺失为 NONE |
| `review_id`（最终验收） | sha256("final", review_kind, candidate_id, check_sha, index_sha) |
| `review_id`（Gate 阻塞） | sha256("gate_block", round_id, input_sha, gate_sha) |
| `review_id`（操作审批） | sha256("ACTION_APPROVAL", round_id, input_sha, assignment_sha, operation_spec_sha) |
| `operation_spec_sha` | 规范化操作列表（operation_id、目标、参数/payload 哈希、幂等键） |
| `review_sha` | 生成 Review 后 `REVIEW.md` 原始字节哈希，预填到 decision |
| `decision_sha` | 归档的 `decision.claimed.md` 字节哈希 |

```text
input → gate → assignment + artifact → candidate_id
      → check + index → review_id（含 kind）→ review_sha → decision → release
```

`meta.assignment_sha` 是 ADMIT 时的冻结锚点：ADMIT 后每次进入 WORK、CHECK、Review 或恢复都重算比对，不一致即协议异常，不能靠“重跑准入”接受被替换的 assignment。

操作审批使用独立身份并包含 `round_id`，不同 Round 不复用授权。Review 正文不可变，消费前重算 `review_sha`。

## 5. 目录

```text
README.md
ENGINE.md
1_input/
  raw.md
  processed.md
  materials/                （按需）
2_tools/                    稳定、可信、按版本可追溯的跨轮工具
3_runs/
  round_NNN/
    meta.md                 身份（含 assignment_sha 锚点；不写状态）
    input.md
    gate.md                 本轮实际运行 Gate 才创建
    assignment.md
    artifact/
    work.md
    check.md
    operations.md           可选，仅外部副作用
    evidence/
      artifact.manifest
      index.md              单项证据唯一明细来源
      scripts/              本轮验证脚本
      ...
4_review/
  REVIEW.md
  decision.md
  history/<review_id>/      outcome 完成前是进行中事务目录
5_release/
  release_NNN/
    meta.md
    artifact/
```

## 6. 输入层

`raw.md` 只追加；每次输入新建 `## Input NNN`；REJECT 反馈注明 `decision:<review_id>`。

**串行化边界**：宿主用同一互斥入口覆盖 raw Input 追加与 Release 最终新鲜度检查 + 原子改名；只在这个短临界区做最终检查与提交。提交后到达的 Input 不回滚历史 Release。

`processed.md` 顶部：`# 项目` + `已处理至：Input NNN`。条目：`R*`（ACTIVE/SUPERSEDED）、`F*`、`I*`、`U*`（BLOCKING/NON_BLOCKING/RESOLVED）、`M*`（路径、sha256、来源 Input）。

验收计划为每个 ACTIVE R 定义：完成条件、验证项、依赖与影响范围、判定依据与可信范围、执行时机、环境/种子、`fresh: required`。

## 7. Main Gate

- 输入存在未解决 BLOCKING U 时，允许无 assignment 直接返回 BLOCKED；此时生成 `BLOCKED_GATE` 终结型 Review；
- 输入可执行时，可同次审查输入与 assignment 语义；全部准入通过才 ADMIT 并冻结身份；
- Gate 复用条件：`input_sha` 与 `raw_prefix_sha` 匹配；**若本轮 assignment 触发语义复核，旧 Gate 的 assignment_review 不能转移**，必须针对当前 `assignment_sha` 出具结果；
- 不持久化 `admission`；准入结果每轮重算。

输出 `gate.md`：ADMIT / RETURN_CHECK / PROTOCOL_BLOCKED、定位到 raw/processed 的未通过项、语义对照摘要；定向复核时记录 `assignment_review` 与 `assignment_sha`。

## 8. 权限

| 角色 | 允许写 | 禁止写 |
|---|---|---|
| Main | `raw.md`、`processed.md`、ADMIT 前身份文件、`meta.assignment_sha` 锚点、`4_review/**`、`5_release/**`、`2_tools/**`（阶段边界）、`operations.md`、归档无效 marker | `materials/**`、业务 artifact、`work.md`/`check.md`/`gate.md` 的创建 |
| Gate | 当前 `gate.md` | processed、assignment、artifact |
| Work | `artifact/**`（提交前）、结束时 `work.md`；外部操作经受控入口 | 其他 Round、输入、assignment、check、gate、`2_tools/`、`operations.md` |
| Check | `evidence/**`（含 scripts）、结束时 `check.md` | artifact、输入、assignment、gate、`2_tools/`、`operations.md` |
| Human | `decision.md`、`materials/**` | Round、artifact、Release |

宿主必须实际执行写入边界；文字权限不是技术保证。

## 9. 状态决策树

0. 恢复事务：补完已 claim 未落 outcome 的决定、临时 Release、`.tmp`；重验新鲜度、`review_sha`、assignment 锚点；
1. 协议完整性：未完成 Round 可修；已完成历史/Release 哈希不匹配 → PROTOCOL_FROZEN；
2. 输入新鲜度：raw 最大 Input > `已处理至` → 输入处理；旧 Review/未 claim decision 归档 STALE；新输入优先；
3. 已 claim 决定：按 review_id 幂等完成；在串行边界内重验新鲜度与全部身份后提交；
4. 未 claim 决定：校验 review_id、review_sha、身份与新鲜度；有效消费，无效 STALE；
5. 有效新鲜 Review + PENDING → 等待人工；
6. Round 初始化或补齐；父产物固定为最近合法 Check Round；
7. Gate：无有效 ADMIT 时运行或复用；RETURN_CHECK 修正后重跑；PROTOCOL_BLOCKED 生成 BLOCKED_GATE Review；
8. WORK：ADMIT 有效、assignment 锚点一致、确定性准入通过且缺 work.md；
9. CHECK：有 work.md，缺合法 check.md；
10. 结论：FAIL → 新 Round；PASS/BLOCKED → 终结型 Review；CHECK 期间变化 → 本轮证据作废；
11. 发布：只有消费有效 APPROVE 才 Release，提交与输入追加在同一串行边界。

## 10. Round 与父产物

父产物固定为**最近一个结论为 PASS 或 FAIL、身份一致且 artifact 哈希与 check 记录一致的合法 Check Round**；`BLOCKED`、无效 check、未封存 Round 排除；没有则用初始材料/空项目。Release 不作为父对象。每轮独立快照，禁止跨 Round 可写硬链接。

## 11. assignment 准入

每轮重算，不持久化为状态：必填字段、R/F/U/M 引用、每个 ACTIVE R 出现在“相关”或“不涉及（含理由）”、input 身份一致、完成条件与验收计划一致。

触发 Gate 定向语义复核：新范围、安全/性能/公开 API/数据兼容/外部副作用、完成条件存在解释空间。

## 12. Work 与封存

- `work.md` 原子提交即封存；提交后不得再改 artifact；
- check 开始时 `S = artifact 实际哈希`，必须等于 work 自报值 `W`，否则写 `evidence/seal_invalid_NNN.md`，Main 归档 work.md，同轮重做 WORK；
- check 结束时再算 `E`。因 `S = W`，`E != S` 等价于 `E != W`，封存已失效：本轮 CHECK 证据作废、禁止 PASS；定位写入来源，可归因且允许时同轮重做 WORK 并重新封存；越权/无法归因 → BLOCKED。不存在“封存仍有效、只重做 CHECK”的分支。

## 13. Check：身份 → 验证项 → 覆盖合成

1. 身份与封存：重算树哈希、核对 work 自报、写 manifest；
2. 验证项执行或有效复用：按影响范围与依赖选择，结构化输出入 evidence，写 index；
3. 覆盖合成：全部 ACTIVE R 状态；PASS 前覆盖计划全部验证项（执行或有效复用，`fresh: required` 必须当轮）。

失败先分类：`BUSINESS / VERIFIER_FAULT / ENV_FAULT / EVIDENCE_INVALID`；仅凭非零退出码不得判业务失败；确认 BUSINESS 后才短路为 FAIL；故障修复后同轮重跑，无法修复或连续两次同类故障 → BLOCKED。

### 验证器信任与证明力

| 判定类型 | 最低依据 |
|---|---|
| 结构检查（存在、JSON、字段、明确阈值） | 规则来自冻结验收计划，输出可复查 |
| 行为/算法/时序正确性 | golden/reference、可证不变量、正反例或独立判据 |
| 同一模型自造期望值并自测 | 不能单独 PASS；UNVERIFIED 或请求独立判断 |
| 不可程序化体验/文案 | 语义验收，需评价准则与观察内容 |

每个 PASS 项写明“被证明的验收条件与适用域”。正反例不能外推到任意输入；缺独立 oracle 或覆盖不足时保持 UNVERIFIED 或列残余风险。

### 证据身份与复用

```text
evidence_key = sha256(requirement_id | requirement_sha |
                      verifier_id | verifier_sha | command |
                      sorted(dependency:sha256) | tool_sha | env | seed)
```

`evidence/index.md` 保留每项原始输出的路径、内容哈希与 oracle/golden 版本；复用和最终验收校验实际字节与身份。依赖无法证明完整 → 不复用；动态/跨模块默认重验；记录 `origin_candidate` / `applied_to_candidate`；`fresh: required` 永不复用。稳定工具按版本保留以便追溯。

check.md 只写 `input_sha`、`artifact_sha`、`index_sha`、结论、缺口、覆盖汇总、失败 key；证据明细在 index。

**外部效果**：ACTIVE R 涉及外部副作用时，check 不能仅凭 artifact PASS，必须独立复核可观察的远端/工具回执，否则 UNVERIFIED/BLOCKED。

## 14. 失败与停滞

正式 check 结论只有 `PASS / FAIL / BLOCKED`；`INVALID` 表示本次检查无效、不提交 check.md。

停滞兜底：`processed.md` 项目头可配置 `最大业务返工轮数：N`（默认 3），不单独存计数器，沿父链统计同一 input_sha 的连续 FAIL Round 数；达到 N 或同一 `failure_key` 连续两次无有效改善 → BLOCKED。验证器/环境故障不计入业务返工轮数，连续两次未修复同样 BLOCKED。

## 15. Review

终结型 Review：`PASS`、`BLOCKED_CHECK`、`BLOCKED_STALL`、`BLOCKED_GATE`。生成后该 Round 不可变，正文不可变，`review_sha` 预填 decision。

- PASS/检查类：绑定 candidate、check、index、gate；R 表 ACTIVE 给结果与 evidence_id；
- BLOCKED_GATE：身份为 `sha256("gate_block", round_id, input_sha, gate_sha)`；`check/index/artifact/assignment` 可为 NONE；R 表标「未验收：Gate 阻塞」；新 Input/REJECT 开新 Round；
- ACTION_APPROVAL：唯一不冻结 Round 的审批；身份含 round_id；在真实调用受控操作前生成，批准后同轮继续 Work。

## 16. 决策与发布

`decision.md` 必填：`review_kind`、`review_id`、`review_sha`、`decision`、反馈；操作审批另含 `operation_ids`。允许值：PENDING / APPROVE / REJECT / APPROVE_ACTION。

消费前：`review_sha` 与当前正文一致；`review_id` 可重算；输入新鲜；APPROVE 要求 kind=PASS、check PASS、gate ADMIT、最新合法候选；APPROVE_ACTION 要求 spec 一致且操作集合等于 Review 列出的操作，执行时再比对 operation_id/目标/payload/幂等键；REJECT 只要求身份一致、未消费、非冻结。

事务：归档 Review → claim decision → 算 decision_sha → 重置入口 → 幂等执行 → 写 outcome。

APPROVE 发布：临时目录 → 校验 → **在串行边界内重验新鲜度与身份** → 原子改名。新输入早于提交点则 STALE。

## 17. 外部操作

存在外部副作用时生成 `operations.md`，Main/宿主维护，work 只经受控入口，check 只读。

Work 先生成 payload；入口计算 `operation_spec_sha` 后检查授权；无授权则暂停 Work、生成 ACTION_APPROVAL，批准后同轮继续。

记录：`operation_id`、`spec_sha`、`approval review_id`、`intended`、`STARTED`、`outcome：SUCCESS/FAILED/UNKNOWN`。

规则：`STARTED` 必须先持久提交再发不可逆请求；结果不明 → UNKNOWN，停止重试并 BLOCKED；operation_id/目标/payload/幂等键任一变化重新审批；不同 Round 不复用授权；未批准不得执行。

## 18. Release

`release_NNN/{meta.md, artifact/}`；meta 绑定 review_id、candidate_id、candidate_round、input_sha、artifact_sha、check_sha、gate_sha、decision_sha、review_sha、released_at。临时目录 + 校验 + 串行边界内最终检查 + 原子改名；同一 review_id 只产生一个 Release；发布后不可就地修改；不强制额外索引文件。

## 19. 2.2.2 最小可运行版本

2.2.2 只做两件事：修运行歧义，把确定性规则交给程序。

### 协议修正

| 问题 | 修改 |
|---|---|
| Check 状态混乱 | 正式结论只允许 `PASS / FAIL / BLOCKED`；`INVALID` 表示检查无效，不提交 check.md |
| Work 封存后无法返工 | 归档旧 `work.md` 到 `evidence/work_archived_NNN.md` 后 marker 失效，解除封存，同轮允许重新执行 |
| `raw_prefix_sha` 不明确 | 精确字节算法：UTF-8 + LF，按 `## Input NNN` section 取 `[0, end_of_cursor_section)`；CRLF/非法 UTF-8/编号异常为 PROTOCOL_BLOCKED |
| 停滞检测不确定 | 可配置 `最大业务返工轮数`，沿父链统计连续 FAIL Round，不单独存计数器 |
| 父产物不严格 | 允许 PASS/FAIL 的合法 Check Round；BLOCKED 与无效 check 排除 |
| 人工决定被覆盖 | 新 Review 生成前必须处理/归档已有 decision，禁止静默重置 |

`PROTOCOL_FROZEN` 保留为安全停机状态，人工从可信副本修复，不增加审批出口。

### 最小 CLI

`2_tools/harness.py`（Python 标准库）执行确定性协议：

| 命令 | 作用 |
|---|---|
| `status` | 推导阶段、异常与下一步动作 |
| `admit` | 校验派工字段、R 引用、冻结锚点 |
| `seal` | 计算 artifact 树哈希、写 manifest、核对封存 |
| `evidence record/verify/reuse` | 写证据索引、校验字节/依赖、计算与匹配 `evidence_key` |
| `review` | 生成 Review 并填充身份、`review_id`、`review_sha`、PENDING decision |
| `consume` | claim/归档决定；APPROVE 生成 Release；REJECT 写新 Input |
| `release` | 恢复已 claim 的发布事务 |
| `selftest` | 临时目录最小实验 + 故障注入 |

模型负责理解、实现与语义判断；程序负责哈希、结构校验、状态推导、事务与发布。`selftest` 覆盖：正常闭环、封存不一致、决定未归档时拒绝新 Review、缺 check 拒绝 PASS、raw 前缀变化。

## 20. 2.2.1 相对 2.2 的勘误（历史）

| 项 | 2.2.1 |
|---|---|
| 冻结锚点 | 恢复 `meta.assignment_sha`，ADMIT 后重算比对；不恢复 `admission` 状态 |
| Gate 阻塞 | 新增 `BLOCKED_GATE` 终结身份与冻结出口，允许无 assignment |
| CHECK 恢复 | 删除不可达的“变化但仍封存有效”分支；`E != W` 即证据作废，回 WORK 或 BLOCKED |
| 操作审批 | 移到真实调用前、绑定轮次与最终 payload；STARTED 先持久提交 |
| 发布竞态 | raw 追加与 Release 最终检查+改名共用串行边界 |
| 代码交付 | mode 敏感交付把运行模式位纳入身份或发布前等强度复验 |
| Gate 复核 | 触发语义复核时必须针对当前 assignment_sha 出具结果 |
| 证据 | index 保留原始输出路径、内容哈希、oracle/golden 版本并在复用时校验 |
| 证明力 | 每项 PASS 写明被证明条件与适用域，不外推 |
| 父产物 | 固定为最近合法 Check Round；Release 不作为父对象 |

## 21. 限制与待验证

1. 写入边界、串行化、原子改名依赖宿主实现；
2. artifact 快照成本依赖 reflink/CoW；
3. 输入/决定/发布需要宿主串行化；
4. 依赖集合完整性需要验证器声明；
5. 外部副作用无法完全由本地文件表达；
6. 临时验证器证明力仍可能不足，必须按第 13 节标注；
7. 有/无缓存、有/无 Gate 复用的收益需要真实任务对照数据，未测前不声称更快；
8. CLI 目前覆盖确定性协议部分；多 Agent 编排仍由宿主负责。

## 22. 给网页端 GPT 的评审提示

> 这是“文件系统即状态”的长程 Agent 任务框架（协议版本 2.2.2），不是业务项目。请评审其冻结身份锚点、阻塞终结分支、封存恢复、验证器证明力、操作审批与幂等、发布串行化、Review 正文绑定，以及 2.2.2 的确定性 CLI；区分协议已规定的内容与建议扩展的内容。不要默认引入数据库、常驻 Agent 或复杂 DAG。
