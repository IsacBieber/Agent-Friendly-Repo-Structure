# 5_release

只有人工在 `4_review/decision.md` 写下 `APPROVE` 之后，Main Agent 才把最终 artifact 复制到：

```text
5_release/artifact/
```

## 规则

- 未经 `APPROVE` 不得进入本目录。`PASS` 只是自动检查通过，不等于人工批准。
- `BLOCKED` 的结果不得进入本目录。
- Release 后视为**不可变最终版本**：后续改动走新 Round，走新一轮 Review，不在这里就地修改。
- 每次 release 必须记录来源 Round，便于回溯到 `3_runs/round_NNN/` 的 assignment、check 与 evidence。

## Release 记录

尚无 release。

<!-- 追加格式：
- <UTC 时间>  round_NNN → 5_release/artifact/  decision=APPROVE
-->
