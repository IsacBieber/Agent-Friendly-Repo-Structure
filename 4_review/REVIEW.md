# 验收

项目：<待命名>

review_kind：<PASS / BLOCKED_CHECK / BLOCKED_GATE / BLOCKED_STALL / ACTION_APPROVAL / PROTOCOL_FROZEN>

<!-- 最终验收 Review：填写以下字段 -->
review_id：<NONE>
candidate_id：<NONE>
candidate_round：<NONE>
input_sha：<NONE>
artifact_sha：<NONE>
check_sha：<NONE>
index_sha：<NONE>
gate_sha：<NONE>

<!-- ACTION_APPROVAL Review：改为填写以下字段 -->
assignment_sha：<NONE>
operation_spec_sha：<NONE>
operation_ids：<NONE>

自动检查：<PASS / BLOCKED / PROTOCOL_BLOCKED>
自治轮数：<N>

> 由 Main 在停止自治或需要操作审批时生成；生成前先归档旧内容。
> `BLOCKED_GATE` 用 `input_sha + gate_sha` 计算 `review_id`，`assignment_sha` 可为 NONE 且不要求 check。
> `ACTION_APPROVAL` 用 `candidate_round + input_sha + assignment_sha + operation_spec_sha` 计算身份，不冻结 Round。
> 生成后正文不可变；`review_sha` 由 Main 计算并预填到 `decision.md`。
> 终结型 Review（PASS/BLOCKED_CHECK/BLOCKED_STALL/BLOCKED_GATE）生成后该 Round 不可变。
> 异常优先只是排序，不删减任何 R 的覆盖与证据。

## 需要人工决定

无。

## 未验证与缺口

- UNVERIFIED：
- 未执行的必需验证：
- N/A 理由：

## 风险与未解决事项

- U1：

## 要求验收

<!-- PASS 必须给 evidence_id；BLOCKED/UNVERIFIED 写状态与原因；BLOCKED_GATE/ACTION_APPROVAL 写「尚未验收」及阻塞原因。 -->

| ID | 状态 | 要求 | 结果 | 关键证据（evidence_id） |
|---|---|---|---|---|
| R1 | ACTIVE | ... | ... | ... |

## 待批准操作（仅 ACTION_APPROVAL）

| operation_id | 目标 | 参数/payload 哈希 | 幂等键 | 风险 |
|---|---|---|---|---|
|  |  |  |  |  |

## 关键变化

- 

## 验证阶段、判定依据与复用

- 身份与封存：
- 验证项执行/复用：
- 覆盖合成：
- 判定依据与 `origin_candidate` / `applied_to_candidate`：

## 追溯

最终检查：`3_runs/round_NNN/check.md`
证据索引：`3_runs/round_NNN/evidence/index.md`
操作记录：`3_runs/round_NNN/operations.md`（如存在）
归档历史：`4_review/history/`
