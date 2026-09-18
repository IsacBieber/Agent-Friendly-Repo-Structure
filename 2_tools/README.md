# 2_tools

稳定、跨 Round 可复用的工具。

核心原则：**可以确定性验证的东西，优先使用程序验证，而不是让 LLM 凭语言判断。**

## 放这里

- 编译 / 构建入口
- 测试入口、regression 入口
- benchmark
- lint、format、静态分析
- 项目专用 validator
- diff 工具、API compatibility checker
- 数据对比与一致性检查脚本

要求：可重复运行、退出码或输出可判定、不依赖单轮上下文、不修改 artifact。

## 不放这里

一次性调查脚本。它们属于产生它的那一轮：

```text
3_runs/round_NNN/tools/      本轮临时验证脚本（bug reproduce、random test、differential test、benchmark wrapper、consistency checker）
3_runs/round_NNN/evidence/   这些脚本的原始运行结果，构成该 Round 的证据链
```

某轮工具如果后续还要复用，由 Main Agent 决定提升到本目录，并在提交说明中写明来源 Round。
写入者只有 Main Agent 与 check_agent；work_agent 对本目录只读、只调用。

## 使用约定

- work_agent 可调用本目录工具做自测，但自述不是证据。
- check_agent 是主要使用者：验证结果与证据路径写进 `check.md`。
- 工具输出必须落到某轮的 `evidence/`，让结论可以回溯到原始数据。
