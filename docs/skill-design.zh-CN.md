# Agent Harness 的开源调研与设计

发布单元是 [Agent Skills 标准包](../skills/agent-harness/SKILL.md)。同一份 Skill 可安装到支持标准的不同宿主，任务的原始输入、执行、验证和验收页仍保存在各自的工作区。

| 开源方案 | 采用的设计 |
|---|---|
| [Agent Skills](https://agentskills.io/specification) · [goose Recipes](https://github.com/aaif-goose/goose/blob/main/documentation/docs/guides/recipes/recipe-reference.md) | 一个可复用入口带入工作流。入口保持短小，详细操作按需读取。 |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec/blob/main/docs/opsx.md) · [GitHub Spec Kit](https://github.com/github/spec-kit) | 每轮冻结范围、可观察场景和验收条件。紧凑任务将这些信息放在一份 `input.md`。 |
| [planning-with-files](https://github.com/OthmanAdi/planning-with-files) · [Beads](https://github.com/gastownhall/beads) | 用磁盘记录跨会话恢复，任务各有目录。读取最新一轮和所需的原始输入。 |
| [Superpowers](https://github.com/obra/superpowers) · [gstack](https://github.com/garrytan/gstack) | 以候选和证据交接实现与复核。独立评审按变化范围和开放问题触发。 |
| [Temporal](https://docs.temporal.io/workflow-execution) · [Bazel](https://bazel.build/remote/caching) | 正式核心用提交身份、回执和实际依赖控制发布恢复与证据复用。 |
| [pytest JUnit XML](https://docs.pytest.org/en/stable/how-to/output.html#creating-junitxml-format-files) · [Ruff](https://docs.astral.sh/ruff/linter/) | 用原始工具报告计算机器结论，把行为验证、结构检查、报告错误和未验证分别记录。Ruff 结果只用于结构验收。 |
| [Promptfoo 的验收用例](https://github.com/promptfoo/promptfoo/blob/main/site/docs/configuration/expected-outputs/index.md) · [Anthropic 的 Agent 评估](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) | 复核提示明确角色、判据、证据和输出字段。能程序判断的先跑工具，语义和覆盖交给独立复核。 |
| [Anthropic 的 Context Engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) · [长程任务交接](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) | 先读本轮快照、进度和摘要，再按证据指针取具体日志和原输入。给复核者独立上下文，只提供判断所需材料。 |
| [in-toto Attestation](https://github.com/in-toto/attestation) | 回执记录所声明的输入、工具脚本及候选内容哈希，原始输出可重新核对。此处使用本地回执，身份与写权限由实际工作区管理。 |

## 入口与正式核心

- 默认入口足以在安装 Skill 的宿主内启动、接续和查看任务。它复用原架构的 `1_input`、`3_runs`、`4_review` 边界，按请求创建必要文件。
- 已有正式工作区使用其固定的 [协议](../ENGINE.md) 和确定性工具。它为需要封存、身份绑定、人工批准和可恢复发布的任务提供更细的事务约束。
- 如果以后需要跨客户端工具接口，可以将 `list_tasks`、`get_status`、`get_review` 暴露给 [MCP](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)。写操作应复用正式核心的事务与身份。现有发布物是 Skill。

默认 Skill 的验证以本轮环境运行。跨窗口核对回执可减少重跑和重读整份日志，范围限定于同一候选和声明的冻结输入。独立复核用来核对需求和证明力。更多语言可接项目现成 JUnit 输出。正式发布继续使用项目自身的事务与批准流程。
