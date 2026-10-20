# 2_tools

稳定、可信、跨 Round 复用的工具与身份校验器。2.2.2 起，协议的确定性部分由 `harness.py` 执行，模型不再手工计算哈希、判断状态合法性或拼装事务。

## harness.py

Python 3.8+，标准库，无第三方依赖。

```bash
python 2_tools/harness.py --root <workspace> <command>
```

| 命令 | 作用 | 退出码 |
|---|---|---|
| `status` | 读取文件，推导阶段、异常与下一步动作 | 0；异常写入 JSON `anomalies` |
| `admit --round round_NNN` | 校验 assignment 字段、R 引用、input/assignment 冻结锚点 | 0 通过；42 失败；40/41 缺文件 |
| `seal --round round_NNN [--write] [--mode-sensitive]` | 计算 artifact 树哈希，写 manifest，核对 work 自报值 | 0；50 artifact 缺失 |
| `evidence --round ... record ...` | 记录要求、命令、输出、依赖、工具、环境、seed，自动算 `evidence_key` | 0；61–64 输入问题 |
| `evidence --round ... verify` | 复算输出/依赖/要求哈希与 `evidence_key` | 0；65 缺索引 |
| `evidence --round ... reuse --id E1 --key KEY` | 判断证据是否可复用 | 0 |
| `review --round ... --kind KIND` | 生成 Review、身份字段、`review_sha` 与 PENDING decision | 0；70 存在未归档决定；73–77 条件不满足 |
| `consume [--stale]` | claim 并消费决定：APPROVE 生成 Release，REJECT 写新 Input，STALE 归档 | 0；80–90 校验失败 |
| `release` | 恢复已 claim 的 APPROVE 事务 | 0 |
| `selftest` | 临时目录构造最小实验 + 故障注入 | 0 全过；1 有失败 |

```bash
python 2_tools/harness.py --root . status
python 2_tools/harness.py --root . admit --round round_001
python 2_tools/harness.py --root . seal --round round_001 --write
python 2_tools/harness.py --root . review --round round_001 --kind PASS
python 2_tools/harness.py --root . consume
```

失败时输出 JSON：`{"ok": false, "error": "...", "code": N, "details": {...}}`。模型只负责理解、实现与语义判断；程序负责确定规则。

## 放这里

- 构建、测试、regression、benchmark；
- lint、format、静态分析；
- validator、diff、API compatibility checker；
- artifact manifest、报告结构、ID/哈希/身份校验器；
- `evidence_key` 计算与证据复用校验；
- 边界防错：写入权限、路径规范化、参数格式、局部 lint；
- 稳定的 golden/reference 生成器与数据对比脚本。

要求：可重复运行、结构化输出、退出码可判定、不依赖单轮对话、不修改 artifact。

稳定工具按版本保留或引用不可变版本，使旧证据能追溯到当时的工具代码。

## 验证器信任

| 判定类型 | 最低依据 |
|---|---|
| 结构检查（存在、JSON、字段、明确阈值） | 规则直接来自冻结验收计划，输出可复查 |
| 行为/算法/时序正确性 | golden/reference、可证不变量、正反例或独立判据 |
| 仅由同一模型自造期望值并自测 | 不能单独 PASS；标 UNVERIFIED 或请求独立判断 |
| 不可程序化的体验/文案 | 语义验收，需评价准则与观察内容 |

## 验证器输出契约

至少包含：

- `outcome`：`passed` / `business_failure` / `verifier_fault` / `env_fault` / `evidence_invalid`；
- `requirement_id`、`failure_key`、`observed`、`expected`；
- 依赖集合（实际读取的文件/模块）、命令、环境、seed。

**仅凭非零退出码不得判定业务失败**；无法区分断言失败与 runner 崩溃时按验证器故障处理。

## 不放这里

一次性验证脚本属于当前 Round：

```text
3_runs/round_NNN/evidence/scripts/   本轮验证脚本
3_runs/round_NNN/evidence/           原始输出与身份记录
```

check_agent 不得直接修改本目录。脚本若被证明长期稳定，由 Main 在阶段边界提升到这里并记录来源 Round。work 对本目录只读。

## 证据身份

```text
evidence_key = sha256(
  requirement_id | requirement_sha |
  verifier_id | verifier_sha |
  command | sorted(dependency:sha256) |
  tool_sha | env_fingerprint | seed
)
```

要求、判定规则、依赖、工具、环境或种子变化必须使缓存失效。验证器必须声明依赖集合；无法证明完整时禁止复用；动态/跨模块行为默认重验。复用记录 `origin_candidate`（证据产生的候选）与 `applied_to_candidate`（可迁移条件）；`fresh: required` 永不复用。

`evidence/index.md` 保留每项原始输出的路径、内容哈希与 oracle/golden 版本；复用与最终验收时校验实际字节与身份匹配。

工具输出必须落入当前 Round 的 `evidence/`，使 check 结论可追溯到原始数据。
