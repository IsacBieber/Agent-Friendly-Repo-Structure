# agent-task-harness 2.2.1

面向 Agent 长程自治任务的文件系统框架。2.2.1 是 2.2 的二次结构审计勘误：补冻结锚点、阻塞终结分支、执行前审批与发布串行化。

## 解决什么问题

- 状态混乱、中断后无法恢复；
- Main 误解需求或派工不可验收；
- 实施者自证成功；
- Check 慢、重复执行昂贵验证；
- 验证器故障被误当成业务失败；
- 验证器“跑通了”被误当成“足以证明”；
- 外部操作批准后无法继续、或崩溃后盲重试；
- 旧批准、旧证据在新输入后仍被误用。

## 核心流程

```text
Input Processing
      ↓
创建 Round：独立 artifact、meta.md、冻结 input.md、写 assignment
      ↓
Main Gate：输入语义 + 必要时定向复核 assignment → ADMIT
      ↓
Work：执行；外部操作在真正调用前审批并落 operations.md
      ↓
提交 work.md = artifact 封存
      ↓
Check
  1 身份与封存
  2 验证项执行或有效复用（失败先分类）
  3 覆盖合成 → PASS / FAIL / BLOCKED / INVALID / UNVERIFIED
      ↓
FAIL(业务) → 新 Round；验证器/环境故障 → 同轮修复
PASS / BLOCKED → 最终 Review（异常优先）→ Human Decision
      ↓
有效且正文未变的 APPROVE → release_NNN 原子提交
```

## 关键角色

| 角色 | 职责 | 禁止 |
|---|---|---|
| Main | 输入、轮次、assignment、确定性校验、调用子角色、Review、审批事务 | 修改业务 artifact、替 Check 宣告 PASS |
| Main Gate | 输入语义与验收方案复核；必要时定向复核 assignment | 格式字段检查、执行测试、重写任务 |
| work | 依 assignment 改 artifact、局部自测、提交 work.md | 改目标、正式验收、自行批准外部操作 |
| check | 用可信依据验证、分故障类别、给覆盖状态 | 改 artifact、直接修业务失败、改 `2_tools/` |
| 人类 | 接受/退回、补需求、批准明确外部操作 | 维护内部派生状态 |

## 目录

```text
README.md
ENGINE.md                  核心执行协议
1_input/
  raw.md                   原始输入，只追加
  processed.md             R/F/I/U/M + 已处理至 + 验收计划
  materials/               只读材料（按需）
2_tools/                   稳定、可信的跨轮工具
3_runs/
  round_NNN/
    meta.md                轮次身份（含 assignment_sha 冻结锚点，不写状态/admission）
    input.md               processed 冻结快照
    gate.md                本轮实际运行 Gate 才创建
    assignment.md
    artifact/              独立产物快照，WORK 提交后封存
    work.md / check.md      原子提交的阶段 marker
    operations.md          可选，仅外部副作用
    evidence/
      artifact.manifest
      index.md             单项证据唯一明细来源
      scripts/             本轮验证脚本
      ...                  原始输出
4_review/
  REVIEW.md                当前候选验收页（异常优先）
  decision.md              绑定 review_id 与 review_sha 的决定
  history/<review_id>/     进行中/已完成的事务目录
5_release/
  release_NNN/             每次有效批准的不可变发布
```

## 身份链

```text
input_sha → gate_sha → assignment_sha + artifact_sha → candidate_id
check_sha + index_sha → review_id（含 review_kind）→ review_sha → decision
→ release_NNN + decision_sha
```

操作审批使用独立身份：`input_sha + assignment_sha + operation_spec_sha`。证据按 `evidence_key` 复用，并记录 `origin_candidate` 与 `applied_to_candidate`。

## Check 为什么更快，但仍可信

- 先身份与封存，再跑验证项；
- 失败先分类：只有 BUSINESS 才短路为 FAIL；
- 验证器/环境故障不进入业务返工；
- 证据按验证项复用，依赖不完整或 `fresh: required` 不复用；
- 临时脚本只能做结构检查；行为正确性需要 golden/reference、正反例等独立依据；
- 覆盖合成必须给出全部 ACTIVE R 的状态。

## 失败处理

| 类别 | 处理 |
|---|---|
| 业务失败 | FAIL，新 Round |
| 验证器故障 | 修验证器，同轮重跑 |
| 环境异常 | 修环境；无解 BLOCKED |
| 证据无效 | INVALID CHECK，同轮重做 |
| 未验证 | 不允许 PASS，补验或 BLOCKED |

同一失败 key 连续两次无有效改善 → BLOCKED，停止重试。

## 快速开始

1. 追加原话到 `1_input/raw.md`。
2. 更新 `processed.md`：条目、`已处理至`、验收计划（含判定依据）。
3. 创建 Round：独立 artifact、`meta.md`、冻结 `input.md`、写 assignment。
4. 运行或复用 Gate，ADMIT 后冻结身份文件。
5. WORK；外部操作在调用受控入口前审批（批准后同轮继续）。
6. 提交 `work.md`，artifact 封存。
7. CHECK：身份 → 验证项 → 覆盖合成；CHECK 期间 artifact 变化则本轮证据作废。
8. PASS/BLOCKED/BLOCKED_GATE 生成终结型 Review；人类只需读 `4_review/REVIEW.md`。
9. 人类在 `decision.md` 对绑定的 `review_id` 与 `review_sha` 做决定。
10. 有效 APPROVE 原子生成 `5_release/release_NNN/`。

完整协议见 [ENGINE.md](ENGINE.md)。
