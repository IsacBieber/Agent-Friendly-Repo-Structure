# agent-task-harness

面向 Agent 长程自治任务的文件系统框架。

## 解决什么问题

长程 Agent 任务常见的失控：

- 状态混乱：不知道现在到底进行到哪一步。
- 上下文膨胀：每轮把全部历史重新塞给模型。
- 过程不可见：Agent 说“已完成”，但没人知道它改了什么。
- 验收缓慢：人工验收前要先读一大堆日志。
- 无法恢复：中断之后只能重头再来。
- 难以审计：结论找不到原始输入和执行证据。

本框架的答案：**文件系统本身就是执行状态**。没有数据库、没有额外状态系统、没有工作流引擎。

## 核心思想

```text
Input
↓
Main Agent
↓
Assignment
↓
Work
↓
Check
↓
Round
↓
Review
↓
Human Decision
```

流程结构固定，不随任务变化。Agent 的智能只用在理解输入、明确本轮任务、完成任务、验证结果、判断下一步。

```text
用户输入
   ↓
INPUT PROCESSING
   ↓
Main Agent 生成本轮 assignment
   ↓
WORK
   ↓
CHECK
   ↓
DECIDE
   ├─ FAIL     → 新 Round → WORK
   ├─ PASS     → REVIEW → 等待人类
   └─ BLOCKED  → REVIEW → 等待人类
```

## 角色

| 角色 | 职责 | 禁止 |
|---|---|---|
| Main Agent | 维护输入、创建 Round、写 assignment、调用子 Agent、读 check、写 REVIEW、按文件系统判断下一步 | 亲自改 artifact、代替验收、PASS 后继续优化 |
| work_agent | 完成本轮 assignment，只有它能改当前 artifact | 改全局任务与验收标准、决定项目方向 |
| check_agent | 独立验证，只信 artifact 与验证结果 | 修改 artifact、把 work.md 的声明当证据 |
| 人类 | 只看 `4_review/REVIEW.md`，在 `decision.md` 写 APPROVE / REJECT | — |

## 目录

```text
README.md
ENGINE.md            Main Agent 的执行协议
1_input/             任务输入层：原话 raw.md + 形式化 processed.md + materials/
2_tools/             跨 Round 复用的确定性工具
3_runs/              Round 执行历史，append-only
4_review/            人工验收：REVIEW.md + decision.md
5_release/           人工 APPROVE 后的不可变产物
```

## 快速开始

1. 向 Main Agent 描述任务（自然语言即可）。
2. Main Agent 将原话逐字追加到 `1_input/raw.md`（`## Input 001`）。
3. Main Agent 生成 `1_input/processed.md`：把信息分类为 `R*` 要求、`F*` 事实、`I*` 推断、`U*` 未明确、`M*` 材料。
4. 之后自动进入 Round：WORK → CHECK → DECIDE，FAIL 就开新轮继续。
5. 自动检查停下后，只看 `4_review/REVIEW.md`。
6. 在 `4_review/decision.md` 写 `APPROVE` 或 `REJECT` + 反馈。

## 五条要点

- 状态由文件是否存在决定：`work.md` = WORK 完成，`check.md` = CHECK 完成。
- Round 完成后不再修改；旧 Round 用于回溯、回滚与审计，默认不读取。
- 每个 Round 拥有独立完整的 artifact 快照。
- 能程序验证的绝不交给语言模型判断。
- CHECK 一旦 PASS，自治立即停止，不做“再优化一下”。

协议细节见 `ENGINE.md`（Main Agent 读）。人类只需读本页与 `4_review/REVIEW.md`。
