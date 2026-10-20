#!/usr/bin/env python3
"""Harness 2.2.2 minimal deterministic runner.

Implements the deterministic part of ENGINE.md:
status / admit / seal / evidence / review / consume / release / selftest.

Standard library only. See 2_tools/README.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

PROTOCOL = "2.2.2"
FINAL_KINDS = {"PASS", "BLOCKED_CHECK", "BLOCKED_STALL", "BLOCKED_GATE"}
REVIEW_KINDS = FINAL_KINDS | {"ACTION_APPROVAL", "PROTOCOL_FROZEN"}
CHECK_VERDICTS = {"PASS", "FAIL", "BLOCKED"}


class HarnessError(Exception):
    def __init__(self, code: int, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_text(text: str) -> str:
    return sha_bytes(text.encode("utf-8"))


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    write_text(tmp, text)
    os.replace(tmp, path)


def parse_fields(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fa5]+)\s*[:：]\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1), m.group(2))
    return fields


def must(cond, code, msg, details=None):
    if not cond:
        raise HarnessError(code, msg, details)


def round_dirs(root: Path):
    base = root / "3_runs"
    if not base.is_dir():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir() and re.fullmatch(r"round_\d{3,}", p.name)])


def latest_round(root: Path):
    rounds = round_dirs(root)
    return rounds[-1] if rounds else None


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def raw_inputs(raw_path: Path):
    """Return [(number_text, start_byte, end_byte)] for ## Input NNN sections."""
    data = raw_path.read_bytes()
    must(b"\r" not in data, 21, "raw.md 含 CRLF；协议要求 UTF-8 + LF")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessError(21, "raw.md 不是合法 UTF-8", {"error": str(exc)})
    heads = list(re.finditer(rb"^## Input ([0-9]{3,})\n", data, re.M))
    sections = []
    for i, m in enumerate(heads):
        num = m.group(1).decode("ascii")
        start = m.start()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(data)
        sections.append((num, start, end))
    return data, sections


def raw_prefix(root: Path, cursor: str) -> dict:
    raw_path = root / "1_input" / "raw.md"
    data, sections = raw_inputs(raw_path)
    nums = [s[0] for s in sections]
    must(nums == sorted(nums) and len(nums) == len(set(nums)), 22, "raw.md Input 编号重复或乱序", {"inputs": nums})
    must(cursor in ("000", "Input 000") or cursor in nums or cursor.replace("Input ", "") in nums,
         23, "游标 Input 不存在于 raw.md", {"cursor": cursor, "inputs": nums})
    cur = "000" if cursor in ("000", "Input 000") else cursor.replace("Input ", "")
    if cur == "000":
        return {"cursor": "Input 000", "start": 0, "end": 0, "sha256": sha_bytes(b"")}
    idx = nums.index(cur)
    end = sections[idx][2]
    prefix = data[:end]
    return {"cursor": f"Input {cur}", "start": 0, "end": end, "sha256": sha_bytes(prefix)}


def artifact_manifest(artifact: Path, mode_sensitive: bool = False) -> tuple[str, str]:
    entries = []
    if artifact.is_dir():
        for p in artifact.rglob("*"):
            r = p.relative_to(artifact).as_posix()
            if p.is_symlink():
                entries.append((r.encode("utf-8"), f"link  {os.readlink(p)}  {r}"))
            elif p.is_file():
                entries.append((r.encode("utf-8"), f"{sha_file(p)}  {p.stat().st_size}  {r}"))
                if mode_sensitive:
                    entries.append(((r + "#mode").encode("utf-8"), f"mode  {oct(p.stat().st_mode & 0o777)[2:]}  {r}"))
    entries.sort(key=lambda x: x[0])
    text = "".join(line + "\n" for _, line in entries)
    return sha_bytes(text.encode("utf-8")), text


def make_identity(root: Path, rdir: Path) -> dict:
    meta = parse_fields(read_text(rdir / "meta.md"))
    must(meta.get("round_id") == rdir.name, 30, "meta.round_id 与目录不一致")
    input_sha = sha_file(rdir / "input.md") if (rdir / "input.md").is_file() else "NONE"
    assignment_sha = sha_file(rdir / "assignment.md") if (rdir / "assignment.md").is_file() else "NONE"
    gate_sha = meta.get("gate_sha", "NONE")
    if gate_sha and gate_sha != "NONE" and (rdir / "gate.md").is_file():
        actual = sha_file(rdir / "gate.md")
        if meta.get("gate_ref") not in (None, "NONE") and not meta.get("gate_ref", "").startswith("reused"):
            gate_sha = actual
    artifact_sha, _ = artifact_manifest(rdir / "artifact") if (rdir / "artifact").is_dir() else ("NONE", "")
    check_sha = sha_file(rdir / "check.md") if (rdir / "check.md").is_file() else "NONE"
    index_sha = sha_file(rdir / "evidence" / "index.md") if (rdir / "evidence" / "index.md").is_file() else "NONE"
    candidate = sha_text("|".join([PROTOCOL, rdir.name, input_sha, assignment_sha, gate_sha, artifact_sha]))
    return {
        "protocol_version": PROTOCOL,
        "round_id": rdir.name,
        "round_dir": rdir,
        "meta": meta,
        "input_sha": input_sha,
        "assignment_sha": assignment_sha,
        "gate_sha": gate_sha,
        "artifact_sha": artifact_sha,
        "check_sha": check_sha,
        "index_sha": index_sha,
        "candidate_id": candidate,
    }


def final_review_id(kind: str, candidate: str, check_sha: str, index_sha: str) -> str:
    return sha_text("|".join(["final", kind, candidate, check_sha, index_sha]))


def gate_block_review_id(round_id: str, input_sha: str, gate_sha: str) -> str:
    return sha_text("|".join(["gate_block", round_id, input_sha, gate_sha]))


def action_spec_sha(operations) -> str:
    lines = []
    for op in operations:
        lines.append("|".join([op["id"], op["target"], op["payload_sha"], op["idempotency_key"]]))
    return sha_text("\n".join(sorted(lines)))


def action_review_id(round_id: str, input_sha: str, assignment_sha: str, spec_sha: str) -> str:
    return sha_text("|".join(["ACTION_APPROVAL", round_id, input_sha, assignment_sha, spec_sha]))


def assignment_ids(assignment_text: str) -> dict:
    fields = parse_fields(assignment_text)
    active = set(re.findall(r"\bR\d+\b", assignment_text))
    return fields, active


def processed_requirements(text: str) -> dict:
    req = {}
    for line in text.splitlines():
        m = re.search(r"\[(R\d+)\]\[(ACTIVE|SUPERSEDED[^\]]*)\]\s*(.*)", line)
        if m:
            req[m.group(1)] = {
                "status": "ACTIVE" if m.group(2) == "ACTIVE" else "SUPERSEDED",
                "text": m.group(3).strip(),
                "line": line.strip(),
            }
    return req


def evidence_key(requirement_id: str, requirement_sha: str, verifier: str, verifier_sha: str,
                 command: str, deps: dict, tool_sha: str, env: str, seed: str) -> str:
    dep_text = ",".join(f"{k}:{deps[k]}" for k in sorted(deps))
    return sha_text("|".join([requirement_id, requirement_sha, verifier, verifier_sha,
                              command, dep_text, tool_sha, env, seed]))


# ---------------------------------------------------------------------------
# commands


def cmd_status(args) -> dict:
    root = Path(args.root).resolve()
    rounds = round_dirs(root)
    raw_path = root / "1_input" / "raw.md"
    proc_path = root / "1_input" / "processed.md"
    out = {"root": str(root), "protocol_version": PROTOCOL, "rounds": [r.name for r in rounds], "anomalies": []}
    cursor = "000"
    max_rework = 3
    if proc_path.is_file():
        ptext = read_text(proc_path)
        fields = parse_fields(ptext)
        cur = fields.get("已处理至", "Input 000")
        m = re.search(r"(\d{3,})", cur)
        cursor = m.group(1) if m else "000"
        m2 = re.search(r"最大业务返工轮数\s*[:：]\s*(\d+)", ptext)
        if m2:
            max_rework = int(m2.group(1))
    raw_max = "000"
    if raw_path.is_file():
        _, sections = raw_inputs(raw_path)
        nums = [s[0] for s in sections]
        raw_max = nums[-1] if nums else "000"
        out["raw_max_input"] = f"Input {raw_max}"
        out["raw_prefix_sha"] = raw_prefix(root, cursor)["sha256"]
    out["processed_cursor"] = f"Input {cursor}"
    out["max_business_rework"] = max_rework

    if raw_max != "000" and int(raw_max) > int(cursor):
        out.update(stage="INPUT_PROCESSING", next_action="process_new_input")
        return out

    review_path = root / "4_review" / "REVIEW.md"
    decision_path = root / "4_review" / "decision.md"
    if decision_path.is_file():
        dec = parse_fields(read_text(decision_path))
        rid = dec.get("review_id", "NONE")
        dv = dec.get("决策", dec.get("decision", "PENDING"))
        if rid not in ("NONE", "") or dv != "PENDING":
            out.update(stage="DECISION", next_action="consume_decision", decision=dv, review_id=rid)
            return out

    if not rounds:
        out.update(stage="NO_ROUND", next_action="create_round")
        return out

    latest = rounds[-1]
    ident = make_identity(root, latest)
    out["latest_round"] = latest.name
    meta = ident["meta"]
    out["input_revision"] = meta.get("input_revision")
    gate_path = latest / "gate.md"
    gate_verdict = None
    if gate_path.is_file():
        gate_verdict = parse_fields(read_text(gate_path)).get("结论")
        out["gate_verdict"] = gate_verdict
        if parse_fields(read_text(gate_path)).get("input_sha") not in (None, ident["input_sha"]):
            out["anomalies"].append("gate.input_sha 与 input.md 不一致")
    else:
        ref = meta.get("gate_ref", "NONE")
        if ref in ("NONE", ""):
            out.update(stage="GATE", next_action="run_gate")
            return out
        out["gate_reused_from"] = ref

    if gate_verdict == "PROTOCOL_BLOCKED":
        out.update(stage="BLOCKED_GATE", next_action="review_blocked_gate")
        return out

    if meta.get("assignment_sha") and meta.get("assignment_sha") != "NONE":
        if ident["assignment_sha"] != meta["assignment_sha"]:
            out["anomalies"].append("assignment_sha 与 meta 冻结锚点不一致")
            out.update(stage="PROTOCOL_ANOMALY", next_action="freeze_fix")
            return out

    work = latest / "work.md"
    check = latest / "check.md"
    if not work.is_file():
        if review_path.is_file():
            rv = parse_fields(read_text(review_path)).get("review_kind")
            if rv in FINAL_KINDS:
                out.update(stage="WAIT_HUMAN", next_action="wait_human", review_kind=rv)
                return out
        # stagnation backstop derived from FAIL chain
        fail_count = 0
        cur_round = latest
        while cur_round is not None:
            c = cur_round / "check.md"
            if c.is_file():
                cv = parse_fields(read_text(c)).get("结论")
                if cv == "FAIL":
                    fail_count += 1
                else:
                    break
            else:
                break
            parent = parse_fields(read_text(cur_round / "meta.md")).get("parent_round", "NONE")
            cur_round = (root / "3_runs" / parent) if parent not in ("NONE", "") else None
        out["consecutive_fail_rounds"] = fail_count
        if fail_count >= max_rework:
            out.update(stage="BLOCKED_STALL", next_action="review_blocked_stall")
            return out
        out.update(stage="WORK", next_action="run_work")
        return out

    if not check.is_file():
        out.update(stage="CHECK", next_action="run_check")
        return out

    check_fields = parse_fields(read_text(check))
    verdict = check_fields.get("结论")
    out["check_verdict"] = verdict
    if verdict not in CHECK_VERDICTS:
        out["anomalies"].append("check 结论非法；不构成正式 CHECK")
        out.update(stage="CHECK_INVALID", next_action="redo_check")
        return out
    if check_fields.get("artifact_sha") not in (None, ident["artifact_sha"]):
        out["anomalies"].append("check.artifact_sha 与当前 artifact 不一致")

    review_kind = None
    if review_path.is_file():
        review_kind = parse_fields(read_text(review_path)).get("review_kind")
    if review_kind in FINAL_KINDS:
        out.update(stage="WAIT_HUMAN", next_action="wait_human", review_kind=review_kind)
        return out
    if verdict == "FAIL":
        out.update(stage="REWORK", next_action="create_round")
    elif verdict == "PASS":
        out.update(stage="REVIEW", next_action="generate_review")
    else:
        out.update(stage="BLOCKED", next_action="generate_blocked_review")
    return out


def cmd_admit(args) -> dict:
    root = Path(args.root).resolve()
    rdir = root / "3_runs" / args.round
    must(rdir.is_dir(), 40, "Round 不存在", {"round": args.round})
    meta = parse_fields(read_text(rdir / "meta.md"))
    assignment_path = rdir / "assignment.md"
    must(assignment_path.is_file(), 41, "缺少 assignment.md")
    text = read_text(assignment_path)
    fields = parse_fields(text)
    errors = []
    for key in ("input_revision", "input_sha"):
        if key not in fields:
            errors.append(f"缺字段：{key}")
    for heading in ("本轮目标", "必须完成", "相关 ACTIVE Requirements"):
        if not re.search(rf"(?m)^#{{1,6}}\s*{re.escape(heading)}", text):
            errors.append(f"缺小节：{heading}")
    input_sha = sha_file(rdir / "input.md") if (rdir / "input.md").is_file() else "NONE"
    if fields.get("input_sha") not in (None, input_sha):
        errors.append("assignment.input_sha 与 input.md 不一致")
    if meta.get("input_sha") not in (None, input_sha):
        errors.append("meta.input_sha 与 input.md 不一致")
    proc_path = root / "1_input" / "processed.md"
    proc = processed_requirements(read_text(proc_path)) if proc_path.is_file() else {}
    active = {rid for rid, v in proc.items() if v["status"] == "ACTIVE"}
    listed = set(re.findall(r"\bR\d+\b", text))
    missing = sorted(active - listed)
    if missing:
        errors.append("未覆盖 ACTIVE R：" + ", ".join(missing))
    if meta.get("assignment_sha") not in (None, "NONE") and meta.get("assignment_sha") != sha_file(assignment_path):
        errors.append("assignment_sha 与 meta 冻结锚点不一致")
    result = {"ok": not errors, "round": args.round, "errors": errors}
    if errors:
        raise HarnessError(42, "assignment 准入失败", result)
    return result


def cmd_seal(args) -> dict:
    root = Path(args.root).resolve()
    rdir = root / "3_runs" / args.round
    artifact = rdir / "artifact"
    must(artifact.is_dir(), 50, "artifact 目录不存在")
    sha, manifest = artifact_manifest(artifact, args.mode_sensitive)
    if args.write:
        write_atomic(rdir / "evidence" / "artifact.manifest", manifest)
    work_path = rdir / "work.md"
    work_sha = parse_fields(read_text(work_path)).get("artifact_sha") if work_path.is_file() else "NONE"
    return {
        "round": args.round,
        "artifact_sha": sha,
        "work_declared": work_sha,
        "sealed": work_sha == sha,
        "manifest_written": bool(args.write),
        "manifest_sha": sha_text(manifest),
    }


def parse_operations(ops):
    out = []
    for spec in ops or []:
        parts = spec.split("|")
        must(len(parts) == 4, 60, "operation 格式应为 id|target|payload_sha|idempotency_key", {"spec": spec})
        out.append({"id": parts[0], "target": parts[1], "payload_sha": parts[2], "idempotency_key": parts[3]})
    return out


def cmd_evidence(args) -> dict:
    root = Path(args.root).resolve()
    rdir = root / "3_runs" / args.round
    evidence_dir = rdir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    index_path = evidence_dir / "index.md"

    if args.action == "record":
        must(args.output and Path(args.output).is_file(), 61, "原始输出文件不存在")
        out_path = Path(args.output).resolve()
        out_sha = sha_file(out_path)
        input_text = read_text(rdir / "input.md")
        req_line = ""
        for line in input_text.splitlines():
            if f"[{args.requirement}]" in line:
                req_line = line.strip()
                break
        must(req_line, 62, "在 input.md 中找不到要求", {"requirement": args.requirement})
        req_sha = sha_text(req_line)
        deps = {}
        for dep in args.dep or []:
            p = (root / dep).resolve()
            must(p.is_file(), 63, "依赖文件不存在", {"dependency": dep})
            deps[rel(root, p)] = sha_file(p)
        tool_sha = sha_file((root / args.tool).resolve()) if args.tool else "NONE"
        verifier_sha = args.verifier_sha or "NONE"
        key = evidence_key(args.requirement, req_sha, args.verifier, verifier_sha,
                           args.command, deps, tool_sha, args.env, args.seed)
        block = [
            f"### {args.id}",
            f"- evidence_key：{key}",
            f"- requirement_id：{args.requirement}",
            f"- requirement_sha：{req_sha}",
            f"- outcome：{args.outcome}",
            f"- verifier：{args.verifier}",
            f"- verifier_sha：{verifier_sha}",
            f"- command：`{args.command}`",
            f"- output：{rel(root, out_path)}",
            f"- output_sha256：{out_sha}",
            f"- tool_sha256：{tool_sha}",
            f"- env：{args.env}",
            f"- seed：{args.seed}",
            "- dependencies：",
        ]
        block += [f"  - {k}：{v}" for k, v in sorted(deps.items())] or ["  - NONE"]
        text = "\n".join(block) + "\n\n"
        if index_path.is_file():
            content = read_text(index_path)
            if f"### {args.id}\n" in content:
                raise HarnessError(64, "evidence_id 已存在", {"id": args.id})
            write_text(index_path, content + text)
        else:
            write_text(index_path, "# 证据索引\n\n" + text)
        return {"recorded": args.id, "evidence_key": key, "index_sha": sha_file(index_path)}

    if args.action == "verify":
        must(index_path.is_file(), 65, "evidence/index.md 不存在")
        content = read_text(index_path)
        blocks = re.split(r"^### ", content, flags=re.M)[1:]
        errors, checked = [], 0
        for b in blocks:
            eid = b.splitlines()[0].strip()
            f = {}
            deps = {}
            in_deps = False
            for line in b.splitlines():
                if line.strip() == "- dependencies：":
                    in_deps = True
                    continue
                if in_deps and line.startswith("  - "):
                    k, _, v = line[4:].partition("：")
                    if k != "NONE":
                        deps[k.strip()] = v.strip()
                    continue
                m = re.match(r"^-\s*([A-Za-z_][A-Za-z0-9_]*)：\s*(.*)$", line)
                if m:
                    f[m.group(1)] = m.group(2).strip()
                    in_deps = False
            checked += 1
            out_path = f.get("output")
            if out_path and out_path != "NONE":
                p = (root / out_path).resolve()
                if not p.is_file():
                    errors.append(f"{eid}: 输出文件缺失")
                elif sha_file(p) != f.get("output_sha256"):
                    errors.append(f"{eid}: 输出哈希不符")
            for dep, expected in deps.items():
                p = root / dep
                if not p.is_file():
                    errors.append(f"{eid}: 依赖缺失 {dep}")
                elif sha_file(p) != expected:
                    errors.append(f"{eid}: 依赖变化 {dep}")
            if f.get("requirement_id") and f.get("requirement_sha"):
                input_text = read_text(rdir / "input.md")
                req_line = ""
                for line in input_text.splitlines():
                    if f"[{f['requirement_id']}]" in line:
                        req_line = line.strip()
                        break
                if req_line and sha_text(req_line) != f["requirement_sha"]:
                    errors.append(f"{eid}: 要求文本已变化")
            key = evidence_key(f.get("requirement_id", ""), f.get("requirement_sha", ""),
                               f.get("verifier", ""), f.get("verifier_sha", ""),
                               f.get("command", "").strip("`"), deps,
                               f.get("tool_sha256", "NONE"), f.get("env", ""), f.get("seed", ""))
            if f.get("evidence_key") != key:
                errors.append(f"{eid}: evidence_key 不匹配")
        return {"checked": checked, "ok": not errors, "errors": errors,
                "index_sha": sha_file(index_path)}

    if args.action == "reuse":
        must(index_path.is_file(), 65, "evidence/index.md 不存在")
        content = read_text(index_path)
        blocks = re.split(r"^### ", content, flags=re.M)[1:]
        for b in blocks:
            if b.splitlines()[0].strip() != args.id:
                continue
            f = {}
            for line in b.splitlines():
                m = re.match(r"^-\s*([A-Za-z_][A-Za-z0-9_]*)：\s*(.*)$", line)
                if m:
                    f[m.group(1)] = m.group(2).strip()
            if f.get("evidence_key") == args.key:
                return {"reused": True, "id": args.id, "reason": "evidence_key 匹配"}
            return {"reused": False, "id": args.id, "reason": "evidence_key 不匹配"}
        raise HarnessError(66, "evidence_id 不存在", {"id": args.id})

    raise HarnessError(67, "未知 evidence 动作", {"action": args.action})


def review_body(kind: str, root: Path, rdir: Path, ident: dict, extra: dict) -> tuple[str, str]:
    meta = ident["meta"]
    check_verdict = "NONE"
    if (rdir / "check.md").is_file():
        check_verdict = parse_fields(read_text(rdir / "check.md")).get("结论", "NONE")
    lines = [
        "# 验收",
        "",
        f"项目：{extra.get('project', '<待命名>')}",
        "",
        f"review_kind：{kind}",
        f"review_id：{extra['review_id']}",
    ]
    if kind in FINAL_KINDS:
        lines += [
            f"candidate_id：{ident['candidate_id']}",
            f"candidate_round：{rdir.name}",
            f"input_sha：{ident['input_sha']}",
            f"artifact_sha：{ident['artifact_sha']}",
            f"check_sha：{ident['check_sha']}",
            f"index_sha：{ident['index_sha']}",
            f"gate_sha：{ident['gate_sha']}",
        ]
    elif kind == "ACTION_APPROVAL":
        lines += [
            f"candidate_round：{rdir.name}",
            f"input_sha：{ident['input_sha']}",
            f"assignment_sha：{ident['assignment_sha']}",
            f"operation_spec_sha：{extra['operation_spec_sha']}",
            f"operation_ids：{extra['operation_ids']}",
        ]
    lines += [
        "",
        f"自动检查：{check_verdict}",
        f"自治轮数：{extra.get('rounds', 1)}",
        "",
        "## 需要人工决定",
        "",
        "无。" if kind == "PASS" else "见下方阻塞项。",
        "",
        "## 未验证与缺口",
        "",
        "- 见 check.md。",
        "",
        "## 风险与未解决事项",
        "",
        "- 见 check.md。",
        "",
        "## 要求验收",
        "",
        "| ID | 状态 | 要求 | 结果 | 关键证据（evidence_id） |",
        "|---|---|---|---|---|",
    ]
    input_text = read_text(rdir / "input.md")
    for line in input_text.splitlines():
        m = re.search(r"\[(R\d+)\]\[(ACTIVE|SUPERSEDED[^\]]*)\]\s*(.*)", line)
        if m:
            status = "ACTIVE" if m.group(2) == "ACTIVE" else "SUPERSEDED"
            result = check_verdict if status == "ACTIVE" else "SUPERSEDED"
            lines.append(f"| {m.group(1)} | {status} | {m.group(3).strip()} | {result} | 见 check.md |")
    if kind == "ACTION_APPROVAL":
        lines += ["", "## 待批准操作（仅 ACTION_APPROVAL）", "",
                  "| operation_id | 目标 | payload 哈希 | 幂等键 |", "|---|---|---|---|"]
        for op in extra["operations"]:
            lines.append(f"| {op['id']} | {op['target']} | {op['payload_sha']} | {op['idempotency_key']} |")
    lines += [
        "",
        "## 关键变化",
        "- 见 check.md / work.md。",
        "",
        "## 验证阶段、判定依据与复用",
        "- 身份与封存：由 harness seal 校验。",
        "- 验证项执行/复用：见 evidence/index.md。",
        "- 覆盖合成：见 check.md。",
        "",
        "## 追溯",
        f"最终检查：`3_runs/{rdir.name}/check.md`",
        f"证据索引：`3_runs/{rdir.name}/evidence/index.md`",
        f"操作记录：`3_runs/{rdir.name}/operations.md`（如存在）",
        "归档历史：`4_review/history/`",
        "",
    ]
    body = "\n".join(lines)
    return body, sha_text(body)


def ensure_decision_free(root: Path) -> None:
    decision_path = root / "4_review" / "decision.md"
    if not decision_path.is_file():
        return
    dec = parse_fields(read_text(decision_path))
    rid = dec.get("review_id", "NONE")
    dv = dec.get("决策", dec.get("decision", "PENDING"))
    if rid not in ("NONE", "") or dv != "PENDING":
        raise HarnessError(70, "已有未归档的人工决定，禁止静默覆盖", {"review_id": rid, "decision": dv})


def cmd_review(args) -> dict:
    root = Path(args.root).resolve()
    ensure_decision_free(root)
    rdir = root / "3_runs" / args.round
    must(rdir.is_dir(), 71, "Round 不存在")
    ident = make_identity(root, rdir)
    kind = args.kind
    must(kind in REVIEW_KINDS, 72, "非法 review_kind", {"kind": kind})
    extra = {"project": parse_fields(read_text(root / "1_input" / "processed.md")).get("# 项目", "project")
             if (root / "1_input" / "processed.md").is_file() else "project",
             "rounds": len(round_dirs(root))}
    if kind in FINAL_KINDS:
        must((rdir / "check.md").is_file(), 73, "终结型 Review 需要合法 check.md")
        verdict = parse_fields(read_text(rdir / "check.md")).get("结论")
        must(verdict in CHECK_VERDICTS, 74, "check 结论非法，不构成正式 CHECK")
        rid = final_review_id(kind, ident["candidate_id"], ident["check_sha"], ident["index_sha"])
        extra["review_id"] = rid
        if kind == "BLOCKED_GATE":
            pass
    elif kind == "BLOCKED_GATE":
        must((rdir / "gate.md").is_file(), 75, "Gate 阻塞 Review 需要 gate.md")
        must(parse_fields(read_text(rdir / "gate.md")).get("结论") == "PROTOCOL_BLOCKED", 76, "Gate 不是 PROTOCOL_BLOCKED")
        rid = gate_block_review_id(rdir.name, ident["input_sha"], ident["gate_sha"])
        extra["review_id"] = rid
    else:  # ACTION_APPROVAL
        ops = parse_operations(args.operation)
        must(ops, 77, "ACTION_APPROVAL 需要至少一个 --operation")
        spec = action_spec_sha(ops)
        rid = action_review_id(rdir.name, ident["input_sha"], ident["assignment_sha"], spec)
        extra.update(review_id=rid, operation_spec_sha=spec,
                     operation_ids=",".join(o["id"] for o in ops), operations=ops)
    body, review_sha = review_body(kind, root, rdir, ident, extra)
    write_atomic(root / "4_review" / "REVIEW.md", body)
    decision = [
        "# 人工决策",
        "",
        f"review_kind：{kind}",
        f"review_id：{rid}",
        f"review_sha：{review_sha}",
        f"operation_ids：{extra.get('operation_ids', 'NONE')}",
        "",
        "决策：PENDING",
        "",
        "允许值：PENDING / APPROVE / REJECT / APPROVE_ACTION",
        "",
        "## 反馈",
        "",
        "无。",
        "",
    ]
    write_atomic(root / "4_review" / "decision.md", "\n".join(decision))
    return {"review_id": rid, "review_sha": review_sha, "review_kind": kind}


def archive_review(root: Path, rid: str, outcome: str, extra_lines=None) -> Path:
    hist = root / "4_review" / "history" / rid
    hist.mkdir(parents=True, exist_ok=True)
    review_path = root / "4_review" / "REVIEW.md"
    if review_path.is_file() and not (hist / "REVIEW.md").exists():
        shutil.copy2(review_path, hist / "REVIEW.md")
    decision_path = root / "4_review" / "decision.md"
    if decision_path.is_file() and not (hist / "decision.claimed.md").exists():
        shutil.move(str(decision_path), hist / "decision.claimed.md")
    lines = [f"outcome：{outcome}", f"archived_at：{args_now()}"]
    if extra_lines:
        lines += extra_lines
    write_atomic(hist / "outcome.md", "\n".join(lines) + "\n")
    return hist


def args_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reset_review_entry(root: Path) -> None:
    write_atomic(root / "4_review" / "REVIEW.md", "# 验收\n\n（当前无候选）\n")
    write_atomic(root / "4_review" / "decision.md",
                 "# 人工决策\n\nreview_kind：NONE\nreview_id：NONE\nreview_sha：NONE\n"
                 "operation_ids：NONE\n\n决策：PENDING\n\n允许值：PENDING / APPROVE / REJECT / APPROVE_ACTION\n\n## 反馈\n\n无。\n")


def cmd_consume(args) -> dict:
    root = Path(args.root).resolve()
    decision_path = root / "4_review" / "decision.md"
    must(decision_path.is_file(), 80, "decision.md 不存在")
    dec = parse_fields(read_text(decision_path))
    rid = dec.get("review_id", "NONE")
    dv = dec.get("决策", dec.get("decision", "PENDING"))
    if rid in ("NONE", "") or dv == "PENDING":
        if not args.stale:
            return {"consumed": False, "reason": "PENDING"}
    if args.stale:
        archive_review(root, rid if rid not in ("NONE", "") else "stale_" + args_now().replace(":", "-"),
                       "STALE", ["reason：manual stale"])
        reset_review_entry(root)
        return {"consumed": True, "outcome": "STALE"}

    review_path = root / "4_review" / "REVIEW.md"
    must(review_path.is_file(), 81, "REVIEW.md 不存在")
    review_sha = sha_file(review_path)
    must(dec.get("review_sha") == review_sha, 82, "review_sha 与正文不一致")
    kind = dec.get("review_kind")
    must(kind in REVIEW_KINDS, 83, "非法 review_kind")

    rdir = None
    review_fields = parse_fields(read_text(review_path))
    for c in round_dirs(root):
        ident = make_identity(root, c)
        if kind == "BLOCKED_GATE":
            if gate_block_review_id(c.name, ident["input_sha"], ident["gate_sha"]) == rid:
                rdir = c
                break
        elif kind == "ACTION_APPROVAL":
            spec = review_fields.get("operation_spec_sha", "NONE")
            if action_review_id(c.name, ident["input_sha"], ident["assignment_sha"], spec) == rid:
                rdir = c
                break
        elif kind in FINAL_KINDS:
            if final_review_id(kind, ident["candidate_id"], ident["check_sha"], ident["index_sha"]) == rid:
                rdir = c
                break
    must(rdir is not None, 84, "无法从当前 Round 重算 review_id", {"review_id": rid})
    ident = make_identity(root, rdir)

    if dv == "APPROVE_ACTION":
        must(kind == "ACTION_APPROVAL", 89, "APPROVE_ACTION 只用于 ACTION_APPROVAL")
        must(review_fields.get("operation_ids") == dec.get("operation_ids"), 90, "operation_ids 与 Review 不一致")
        archive_review(root, rid, "APPROVED_ACTION", [f"operation_ids：{dec.get('operation_ids', 'NONE')}"])
        reset_review_entry(root)
        return {"consumed": True, "outcome": "APPROVED_ACTION"}

    if dv == "REJECT":
        feedback = dec.get("反馈", "")
        raw_path = root / "1_input" / "raw.md"
        data = read_text(raw_path)
        nums = [int(n) for n in re.findall(r"^## Input (\d{3,})$", data, re.M)]
        nxt = (max(nums) + 1) if nums else 1
        addition = f"\n## Input {nxt:03d}\n\n{feedback.strip()}\n"
        write_atomic(raw_path, data.rstrip("\n") + "\n" + addition)
        archive_review(root, rid, "REJECTED", [f"feedback_input：Input {nxt:03d}"])
        reset_review_entry(root)
        return {"consumed": True, "outcome": "REJECTED", "new_input": f"Input {nxt:03d}"}

    if dv == "APPROVE_ACTION":
        archive_review(root, rid, "APPROVED_ACTION", [f"operation_ids：{dec.get('operation_ids', 'NONE')}"])
        reset_review_entry(root)
        return {"consumed": True, "outcome": "APPROVED_ACTION"}

    must(dv == "APPROVE", 85, "未知 decision", {"decision": dv})
    must(kind == "PASS", 86, "只有 PASS Review 可以 APPROVE")
    check = parse_fields(read_text(rdir / "check.md"))
    must(check.get("结论") == "PASS", 87, "check 不是 PASS")
    meta = ident["meta"]
    cursor = "000"
    proc = parse_fields(read_text(root / "1_input" / "processed.md"))
    m = re.search(r"(\d{3,})", proc.get("已处理至", "Input 000"))
    if m:
        cursor = m.group(1)
    raw_max = max([int(n) for n in re.findall(r"^## Input (\d{3,})$", read_text(root / "1_input" / "raw.md"), re.M)] or [0])
    must(int(cursor) == raw_max, 88, "存在未处理新输入，拒绝发布", {"cursor": cursor, "raw_max": raw_max})

    rel_dir = root / "5_release"
    rel_dir.mkdir(exist_ok=True)
    nums = [int(p.name.split("_")[1]) for p in rel_dir.iterdir() if p.is_dir() and re.fullmatch(r"release_\d{3,}", p.name)]
    rel_name = f"release_{(max(nums) + 1) if nums else 1:03d}"
    tmp = rel_dir / (rel_name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    (tmp / "artifact").mkdir(parents=True)
    for item in (rdir / "artifact").iterdir():
        if item.is_dir():
            shutil.copytree(item, tmp / "artifact" / item.name)
        else:
            shutil.copy2(item, tmp / "artifact" / item.name)
    meta_lines = [
        f"release_id：{rel_name}",
        f"review_id：{rid}",
        f"candidate_id：{ident['candidate_id']}",
        f"candidate_round：{rdir.name}",
        f"input_sha：{ident['input_sha']}",
        f"artifact_sha：{ident['artifact_sha']}",
        f"check_sha：{ident['check_sha']}",
        f"gate_sha：{ident['gate_sha']}",
        f"decision_sha：{sha_file(decision_path)}",
        f"review_sha：{review_sha}",
        f"released_at：{args_now()}",
    ]
    write_atomic(tmp / "meta.md", "# Release\n\n" + "\n".join(meta_lines) + "\n")
    os.replace(tmp, rel_dir / rel_name)
    archive_review(root, rid, "APPROVED", [f"release：5_release/{rel_name}"])
    reset_review_entry(root)
    return {"consumed": True, "outcome": "APPROVED", "release": f"5_release/{rel_name}"}


def cmd_release(args) -> dict:
    root = Path(args.root).resolve()
    return cmd_consume(argparse.Namespace(root=str(root), stale=False))


# ---------------------------------------------------------------------------
# selftest


def make_fixture(root: Path) -> None:
    (root / "1_input" / "materials").mkdir(parents=True)
    (root / "3_runs").mkdir()
    (root / "4_review").mkdir()
    write_text(root / "1_input" / "raw.md", "# 原始输入\n\n## Input 001\n\n实现一个加法函数。\n")
    write_text(root / "1_input" / "processed.md",
               "# 项目：selftest\n\n已处理至：Input 001\n最大业务返工轮数：3\n\n"
               "## 明确要求\n- [R1][ACTIVE] 加法函数返回正确结果。来源：Input 001\n")
    rdir = root / "3_runs" / "round_001"
    (rdir / "artifact").mkdir(parents=True)
    (rdir / "evidence").mkdir()
    write_text(rdir / "artifact" / "add.py", "def add(a, b):\n    return a + b\n")
    write_text(rdir / "input.md", read_text(root / "1_input" / "processed.md"))
    input_sha = sha_file(rdir / "input.md")
    artifact_sha, _ = artifact_manifest(rdir / "artifact")
    write_text(rdir / "meta.md",
               "# Round 001\n\nprotocol_version：2.2.2\nround_id：round_001\nparent_round：NONE\n"
               f"created_reason：selftest\ninput_revision：Input 001\ninput_sha：{input_sha}\n"
               f"assignment_sha：NONE\ngate_ref：round_001\ngate_sha：NONE\n")
    write_text(rdir / "assignment.md",
               "# 本轮任务\n\ninput_revision：Input 001\n"
               f"input_sha：{input_sha}\n\n## 本轮目标\n实现 add。\n\n## 必须完成\n- add 返回正确\n\n"
               "## 相关 ACTIVE Requirements\n- R1\n\n## 必须保持\n- 无\n\n## 完成条件\n- 测试通过\n")
    write_text(rdir / "gate.md",
               "# Main Gate\n\nprotocol_version：2.2.2\nround_id：round_001\n"
               f"input_revision：Input 001\ninput_sha：{input_sha}\nraw_prefix_sha：{raw_prefix(root, '001')['sha256']}\n"
               "结论：ADMIT\nassignment_review：N/A\nassignment_sha：NONE\n")
    gate_sha = sha_file(rdir / "gate.md")
    meta = read_text(rdir / "meta.md").replace("assignment_sha：NONE", f"assignment_sha：{sha_file(rdir / 'assignment.md')}")
    meta = meta.replace("gate_sha：NONE", f"gate_sha：{gate_sha}")
    write_text(rdir / "meta.md", meta)
    write_text(rdir / "work.md",
               f"# Work\n\nRound：round_001\ninput_sha：{input_sha}\n\n## 完成情况\n完成\n\n"
               f"## 实际修改\n- add.py — 新增 — R1\n\n## 自测\n- python -c — OK\n\nartifact_sha：{artifact_sha}\n")
    out = root / "3_runs" / "round_001" / "evidence" / "test.log"
    write_text(out, "add tests: 1 passed\n")
    write_text(rdir / "check.md",
               f"# Check\n\nRound：round_001\ninput_sha：{input_sha}\nartifact_sha：{artifact_sha}\n"
               f"index_sha：NONE\n\n执行层级：identity/items/coverage\n结论：PASS\n\n"
               "未通过项：无\n\nRequirements 覆盖：R1 PASS\n\n验证结果：见 evidence\n")


def run_selftest() -> dict:
    results = []
    with tempfile.TemporaryDirectory(prefix="harness-selftest-") as td:
        root = Path(td) / "workspace"
        make_fixture(root)

        st = cmd_status(argparse.Namespace(root=str(root)))
        results.append(("status init", st.get("stage") == "REVIEW", st))

        adm = cmd_admit(argparse.Namespace(root=str(root), round="round_001"))
        results.append(("admit", adm["ok"], adm))

        seal = cmd_seal(argparse.Namespace(root=str(root), round="round_001", write=True, mode_sensitive=False))
        results.append(("seal", seal["sealed"], seal))

        cmd_evidence(argparse.Namespace(root=str(root), round="round_001", action="record", id="E1",
                                        requirement="R1", outcome="passed", command="python test_add.py",
                                        output=str(root / "3_runs/round_001/evidence/test.log"),
                                        dep=["3_runs/round_001/artifact/add.py"], tool="3_runs/round_001/artifact/add.py",
                                        verifier="pytest", verifier_sha="NONE", env="linux/py3.11", seed="0"))
        ver = cmd_evidence(argparse.Namespace(root=str(root), round="round_001", action="verify"))
        results.append(("evidence verify", ver["ok"], ver))

        rev = cmd_review(argparse.Namespace(root=str(root), round="round_001", kind="PASS", operation=None))
        results.append(("review pass", rev["review_kind"] == "PASS", rev))

        # decision overwrite guard
        dec_path = root / "4_review" / "decision.md"
        dec_text = read_text(dec_path).replace("决策：PENDING", "决策：APPROVE")
        write_text(dec_path, dec_text)
        try:
            cmd_review(argparse.Namespace(root=str(root), round="round_001", kind="PASS", operation=None))
            results.append(("decision overwrite guard", False, "未拒绝"))
        except HarnessError as exc:
            results.append(("decision overwrite guard", exc.code == 70, exc.message))

        cons = cmd_consume(argparse.Namespace(root=str(root), stale=False))
        results.append(("consume approve", cons.get("outcome") == "APPROVED" and
                        (root / "5_release" / "release_001" / "meta.md").is_file(), cons))

        # seal mismatch
        (root / "3_runs/round_001/artifact/add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        seal2 = cmd_seal(argparse.Namespace(root=str(root), round="round_001", write=False, mode_sensitive=False))
        results.append(("seal mismatch detected", seal2["sealed"] is False, seal2))

        # raw prefix changes when earlier content edited
        p1 = raw_prefix(root, "001")["sha256"]
        raw_path = root / "1_input" / "raw.md"
        write_text(raw_path, read_text(raw_path).replace("加法函数", "减法函数"))
        p2 = raw_prefix(root, "001")["sha256"]
        results.append(("raw prefix changes", p1 != p2, {"before": p1, "after": p2}))

        # invalid check is not a formal check
        (root / "3_runs/round_001/check.md").unlink()
        try:
            cmd_review(argparse.Namespace(root=str(root), round="round_001", kind="PASS", operation=None))
            results.append(("missing check rejected", False, "未拒绝"))
        except HarnessError as exc:
            results.append(("missing check rejected", exc.code == 73, exc.message))

    ok = all(r[1] for r in results)
    return {"ok": ok, "results": [{"name": n, "ok": o, "detail": d} for n, o, d in results]}


# ---------------------------------------------------------------------------
# CLI


def build_parser():
    p = argparse.ArgumentParser(prog="harness.py", description="Harness 2.2.2 deterministic runner")
    p.add_argument("--root", default=".", help="workspace root")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sp = sub.add_parser("admit"); sp.add_argument("--round", required=True)
    sp = sub.add_parser("seal"); sp.add_argument("--round", required=True)
    sp.add_argument("--write", action="store_true"); sp.add_argument("--mode-sensitive", action="store_true")
    sp = sub.add_parser("evidence")
    sp.add_argument("--round", required=True)
    sp.add_argument("action", choices=["record", "verify", "reuse"])
    sp.add_argument("--id"); sp.add_argument("--requirement"); sp.add_argument("--outcome", default="passed")
    sp.add_argument("--command", dest="command_text", default="")
    sp.add_argument("--output"); sp.add_argument("--dep", action="append")
    sp.add_argument("--tool"); sp.add_argument("--verifier", default="manual")
    sp.add_argument("--verifier-sha", dest="verifier_sha", default="NONE")
    sp.add_argument("--env", default=""); sp.add_argument("--seed", default="0")
    sp.add_argument("--key")
    sp = sub.add_parser("review"); sp.add_argument("--round", required=True)
    sp.add_argument("--kind", required=True, choices=sorted(REVIEW_KINDS)); sp.add_argument("--operation", action="append")
    sp = sub.add_parser("consume"); sp.add_argument("--stale", action="store_true")
    sub.add_parser("release")
    sub.add_parser("selftest")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            result = cmd_status(args)
        elif args.command == "admit":
            result = cmd_admit(args)
        elif args.command == "seal":
            result = cmd_seal(args)
        elif args.command == "evidence":
            if hasattr(args, "command_text"):
                args.command = args.command_text
            result = cmd_evidence(args)
        elif args.command == "review":
            result = cmd_review(args)
        elif args.command == "consume":
            result = cmd_consume(args)
        elif args.command == "release":
            result = cmd_release(args)
        elif args.command == "selftest":
            result = run_selftest()
        else:
            raise HarnessError(2, "未知命令")
    except HarnessError as exc:
        print(json.dumps({"ok": False, "error": exc.message, "code": exc.code, "details": exc.details},
                         ensure_ascii=False, indent=2))
        return exc.code
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
