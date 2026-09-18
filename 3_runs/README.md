# 3_runs

所有执行历史。Round 是执行历史的一等公民。

```text
3_runs/
└── round_NNN/
    ├── meta.md         本轮元信息（创建时立即写）
    ├── assignment.md   Main Agent 给 work_agent 的派工
    ├── artifact/       本轮独立完整的产物快照
    ├── work.md         work_agent 报告 —— 存在即 WORK 完成
    ├── check.md        check_agent 报告 —— 存在即 CHECK 完成
    ├── evidence/       验证的原始输出
    └── tools/          本轮临时验证脚本
```

## 规则

- **append-only**：完成后的 Round 不再修改。返工、修复、重跑都通过新 Round 表达。
- **完成 marker**：`work.md` 存在 = WORK 完成；`check.md` 存在 = CHECK 完成。两者都必须最后写入。文件系统本身就是状态，不存在独立状态文件。
- **artifact 独立**：`round_N/artifact/` 快照后成为 `round_N+1/artifact/` 的起点。优先 reflink / CoW / snapshot，不支持则完整复制。**禁止**跨 Round 使用可写硬链接。
- **历史默认不读取**：正常运行只关心编号最大的 Round。旧 Round 用于回溯、调试、regression 定位、回滚、审计；子 Agent 在信息不足或需要核对原始表达时可按需下钻（Just-in-Time），但不要无理由扫描全部历史。
- **`evidence/` 只放原始输出**：结论写在 `check.md`，数据留在 `evidence/`。

## 命名

`round_001`、`round_002` …… 三位数字递增。不预留、不跳号、不复用。
