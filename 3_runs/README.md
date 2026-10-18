# 3_runs

所有执行历史。Round 是 append-only 的一等公民。

```text
3_runs/
└── round_NNN/
    ├── meta.md              轮次身份（含 assignment_sha 冻结锚点；不写状态/admission）
    ├── input.md             processed 的冻结快照
    ├── gate.md              本轮实际运行 Gate 才创建
    ├── assignment.md
    ├── artifact/            独立产物快照，WORK 提交后封存
    ├── work.md              WORK marker + artifact 自报哈希
    ├── check.md             CHECK marker（input/artifact/index_sha、结论、缺口、覆盖汇总）
    ├── operations.md        可选；仅存在外部副作用时
    └── evidence/
        ├── artifact.manifest 确定性封存清单
        ├── index.md          单项证据唯一明细来源
        ├── scripts/          本轮验证脚本（原 round/tools 并入）
        └── ...               原始输出
```

## 规则

- **状态只由文件推导**：不写“本轮状态”；`work.md` / `check.md` 存在且合法才是阶段完成。
- **原子提交**：报告先写 `.tmp`，校验后原子改名；`.tmp` 不算完成。
- **分层不可变**：ADMIT 前身份文件可修正；ADMIT 后冻结；`work.md` 提交后 artifact 封存；最终验收 Review 生成后整轮不可变。`ACTION_APPROVAL` 只暂停外部操作，不冻结 Round。
- **封存**：check 首尾各算一次树哈希。开始不一致 → check 写 `evidence/seal_invalid_NNN.md`，Main 归档 `work.md`，同轮重做 WORK；结束 `E != 开始 S`（且 `S = work 自报 W`）意味着 `E != W`，本轮证据作废、禁止 PASS；可归因则同轮重交封存，越权/无法归因 → BLOCKED。不存在“封存仍有效只重做 CHECK”的分支。
- **父产物**：新 Round 只继承最近一个 check 已完成且 artifact 哈希一致的 Round；Release 不作为父对象，未封存 Work 不得升格为候选。
- **终结型 Review**：`PASS`、`BLOCKED_CHECK`、`BLOCKED_STALL`、`BLOCKED_GATE` 生成后该 Round 不可变；`ACTION_APPROVAL` 不冻结 Round。
- **证据复用按验证项**：`evidence_key` 匹配才可复用；记录 `origin_candidate` 与 `applied_to_candidate`；依赖不完整或 `fresh: required` 不复用。
- **临时脚本归 evidence**：本轮验证脚本放 `evidence/scripts/`，与输出、哈希同处；跨轮稳定工具才进 `2_tools/`。
- **operations.md**：仅外部副作用 Round 生成，由 Main/宿主维护；授权在实际调用前取得，`STARTED` 必须先持久提交再发出不可逆请求，结果不明记 UNKNOWN 并停止重试。
- **历史默认不读取**：正常只看最新 Round；旧 Round 用于追溯、regression 定位、回滚、审计。
- **check_agent 写权限**：当前 `evidence/**`、最终 `check.md`；不得修改 artifact、`2_tools/`、`operations.md`。

## 命名

`round_001`、`round_002`……连续递增，不预留、不跳号、不复用。
