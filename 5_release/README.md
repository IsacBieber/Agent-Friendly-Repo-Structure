# 5_release

只有人工在 `4_review/decision.md` 写下有效且正文未变的 `APPROVE` 之后，Main 才创建：

```text
5_release/
└── release_NNN/
    ├── meta.md
    └── artifact/
```

## 规则

- 未经有效 `APPROVE` 不得进入本目录。
- `PASS` 只是自动检查通过，不等于人工批准。
- `BLOCKED`、无效 check（INVALID 不提交正式 check）、`UNVERIFIED`、身份或正文不匹配的候选不得发布。
- 每次发布独立编号，连续递增，不复用、不覆盖。
- 发布使用“临时目录 → 校验 artifact 与 meta → 原子改名”；提交前再次校验输入新鲜度，新输入早于提交点则视为 STALE，不发布。
- Release 后不可就地修改；后续改动走新 Round、新 Review、新 Release。
- `meta.md` 必须绑定：`release_id`、`review_id`、`candidate_id`、`candidate_round`、`input_sha`、`artifact_sha`、`check_sha`、`gate_sha`、`decision_sha`、`review_sha`、`released_at`。
- 同一个 `review_id` 只能产生一个 Release；重复消费必须跳过。
- 不强制维护额外索引文件；需要清单时按目录生成。
