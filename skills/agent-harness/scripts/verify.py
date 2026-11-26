"""Freeze, run and inspect local verification for an Agent Harness round."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.etree import ElementTree

TOOLS = {"pytest", "junit", "ruff"}
EVIDENCE_FILES = ("stdout.log", "stderr.log", "report.xml")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value, mode="w"):
    with path.open(mode, encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def strings(value, label, nonempty=True):
    require(isinstance(value, list) and all(isinstance(s, str) and s.strip() for s in value),
            f"{label} must be a list of nonempty strings")
    require(value or not nonempty, f"{label} is empty")
    return value


def below(root, name):
    path = Path(name)
    require(not path.anchor, f"Expected a relative path: {name}")
    resolved = (root / path).resolve()
    require(resolved != root and resolved.is_relative_to(root), f"Path leaves its scope: {name}")
    return resolved


def load_plan(root, round_dir):
    plan_bytes = (round_dir / "verification.json").read_bytes()
    input_bytes = (round_dir / "input.md").read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))
    require(isinstance(plan, dict), "verification.json must be an object")
    require(isinstance(plan.get("requirements"), dict), "requirements must be an object")
    requirements = plan["requirements"]
    input_text = input_bytes.decode("utf-8")
    input_ids = re.findall(r"(?m)^- \[(R[1-9][0-9]*)\] +\S", input_text)
    require(input_ids and len(set(input_ids)) == len(input_ids) and set(input_ids) == set(requirements),
            "Every '- [R1] ...' requirement in input.md must appear once in the plan")
    require(all(kind in ("behavior", "structure", "manual") for kind in requirements.values()),
            "Requirement kinds must be behavior, structure or manual")

    candidate = strings(plan.get("candidate_files"), "candidate_files")
    checks = plan.get("checks")
    require(isinstance(checks, list), "checks must be a list")
    frozen = set()
    check_ids = set()
    for check in checks:
        require(isinstance(check, dict), "Each check must be an object")
        name = check.get("id")
        require(isinstance(name, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,47}", name) and name not in check_ids,
                "Each check needs a unique lowercase id")
        check_ids.add(name)
        tool = check.get("tool")
        require(isinstance(tool, str) and tool in TOOLS, f"Unknown tool for {name}")
        ids = strings(check.get("requirements"), f"{name}.requirements")
        kinds = ("structure",) if tool == "ruff" else ("structure", "behavior")
        require(len(set(ids)) == len(ids) and all(requirements.get(item) in kinds for item in ids),
                f"{name} has duplicate requirements or cannot verify their kinds")
        require(isinstance(check.get("basis"), str) and check["basis"].strip(), f"{name} needs a basis")
        timeout = check.get("timeout_seconds", 120)
        require(type(timeout) is int and timeout > 0, f"{name} needs a positive integer timeout")
        frozen.update(strings(check.get("inputs", []), f"{name}.inputs", nonempty=tool == "junit"))
        if tool == "pytest":
            frozen.update(strings(check.get("tests"), f"{name}.tests"))
        elif tool == "ruff":
            targets = strings(check.get("targets"), f"{name}.targets")
            require(all(item in candidate and Path(item).suffix in (".py", ".pyi") for item in targets),
                    f"{name}.targets must be Python candidate files")
        else:
            argv = strings(check.get("argv"), f"{name}.argv")
            require("{report}" not in argv[0] and sum(arg.count("{report}") for arg in argv) == 1,
                    f"{name}.argv must use {{report}} once in the arguments")

    paths = {}
    for name in set(candidate) | frozen:
        path = below(root, name)
        require(not path.is_relative_to(round_dir), f"Tracked file is inside the round: {name}")
        require(path not in paths, f"Aliases name the same tracked file: {name}, {paths.get(path)}")
        paths[path] = name
    require(not set(candidate) & frozen, "Candidate and frozen verification inputs must be separate files")
    read_identity = {"input": hashlib.sha256(input_bytes).hexdigest(),
                     "plan": hashlib.sha256(plan_bytes).hexdigest()}
    return plan, sorted(frozen), read_identity


def fingerprint(root, names):
    return {name: digest(below(root, name)) for name in sorted(set(names))}


def frozen_state(root, round_dir, frozen):
    return {
        "input": digest(round_dir / "input.md"),
        "plan": digest(round_dir / "verification.json"),
        "verifier": digest(Path(__file__)),
        "verification_inputs": fingerprint(root, frozen),
    }


def junit_result(report, returncode):
    if not report.is_file():
        return "CHECK_ERROR", "JUnit report missing"
    root = ElementTree.parse(report).getroot()
    if root.tag not in ("testsuite", "testsuites"):
        return "CHECK_ERROR", "Unexpected JUnit root element"
    cases = list(root.iter("testcase"))
    counts = {tag: sum(case.find(tag) is not None for case in cases)
              for tag in ("error", "failure", "skipped")}
    suites = [root, *root.findall(".//testsuite")]
    if counts["error"] or any(int(suite.get("errors", 0)) for suite in suites):
        return "CHECK_ERROR", "JUnit reports test or setup errors"
    inconsistent = any(not counts[tag] and any(int(suite.get(attribute, 0)) for suite in suites)
                       for tag, attribute in (("failure", "failures"), ("skipped", "skipped")))
    if inconsistent:
        return "CHECK_ERROR", "JUnit suite and case results disagree"
    if returncode == 1 and counts["failure"]:
        return "FAIL", f"{counts['failure']} test cases failed"
    if (returncode, len(cases)) == (5, 0) or (returncode == 0 and not counts["failure"]
                                           and (not cases or counts["skipped"])):
        return "UNVERIFIED", f"{len(cases)} cases reported, {counts['skipped']} skipped"
    if returncode == 0 and not counts["failure"]:
        return "PASS", f"{len(cases)} test cases passed"
    return "CHECK_ERROR", f"Exit {returncode} is inconsistent with a passing JUnit report"


def ruff_result(output, returncode):
    findings = read_json(output)
    if not isinstance(findings, list):
        return "CHECK_ERROR", "Ruff output is not a JSON list"
    if returncode == 0 and not findings:
        return "PASS", "Ruff reported no findings"
    if returncode == 1 and findings:
        return "FAIL", f"Ruff reported {len(findings)} findings"
    return "CHECK_ERROR", f"Ruff exit {returncode} with {len(findings)} findings"


def tool_result(tool, folder, returncode):
    if returncode is None:
        return "CHECK_ERROR", "Tool launch or execution failed. See stderr.log"
    try:
        if tool == "ruff":
            return ruff_result(folder / "stdout.log", returncode)
        return junit_result(folder / "report.xml", returncode)
    except (OSError, ValueError, ElementTree.ParseError) as exc:
        return "CHECK_ERROR", f"Cannot read structured tool output: {exc}"


def run_check(root, check, folder):
    folder.mkdir()
    tool = check["tool"]
    report = str(folder / "report.xml")
    if tool == "pytest":
        command = [sys.executable, "-m", "pytest", f"--junitxml={report}",
                   *(str(below(root, item)) for item in check["tests"])]
    elif tool == "ruff":
        command = [sys.executable, "-m", "ruff", "check", "--output-format=json", "--no-cache",
                   *(str(below(root, item)) for item in check["targets"])]
    else:
        command = [arg.replace("{report}", report) for arg in check["argv"]]
    started = time.monotonic()
    returncode = None
    with (folder / "stdout.log").open("wb") as stdout, (folder / "stderr.log").open("wb") as stderr:
        try:
            run = subprocess.run(command, cwd=root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 timeout=check.get("timeout_seconds", 120), check=False)
            returncode = run.returncode
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            stderr.write(f"\n{type(exc).__name__}: {exc}\n".encode())
    return {"command": command, "returncode": returncode, "elapsed_seconds": round(time.monotonic() - started, 3),
            "evidence": evidence_hashes(folder)}


def evidence_hashes(folder):
    return {name: digest(folder / name) for name in EVIDENCE_FILES if (folder / name).is_file()}


def summarize(plan, attempt, receipt):
    by_requirement = {item: [] for item in plan["requirements"]}
    results = {}
    for check in plan["checks"]:
        name = check["id"]
        record = receipt["checks"][name]
        folder = below(attempt, name)
        require({"stdout.log", "stderr.log"} <= record["evidence"].keys()
                and evidence_hashes(folder) == record["evidence"], f"Evidence is missing or changed: {name}")
        status, note = tool_result(check["tool"], folder, record["returncode"])
        results[name] = {"status": status, "note": note, "seconds": record["elapsed_seconds"],
                         "evidence": str(folder)}
        for item in check["requirements"]:
            by_requirement[item].append(status)

    requirements = {}
    for item, statuses in by_requirement.items():
        if not statuses:
            status = "NEEDS_REVIEW" if plan["requirements"][item] == "manual" else "UNVERIFIED"
        else:
            status = next(value for value in ("FAIL", "CHECK_ERROR", "UNVERIFIED", "PASS") if value in statuses)
        requirements[item] = status
    values = set(requirements.values())
    verdict = "FAIL" if "FAIL" in values else "PASS" if values == {"PASS"} else "BLOCKED"
    return {"verdict": verdict, "requirements": requirements, "checks": results,
            "receipt": str(attempt / "receipt.json")}


def execute(args):
    root = args.root.resolve()
    round_dir = below(root, args.round)
    plan, frozen, read_identity = load_plan(root, round_dir)
    state = frozen_state(root, round_dir, frozen)
    require(all(state[key] == value for key, value in read_identity.items()), "Input or plan changed while being read")
    anchor = round_dir / "verification.lock.json"
    if args.action == "freeze":
        write_json(anchor, state, mode="x")
        return {"verdict": "FROZEN", "lock": str(anchor)}
    require(read_json(anchor) == state, "Frozen input, plan, verifier or verification files changed")
    candidate = fingerprint(root, plan["candidate_files"])
    if args.action == "run":
        evidence = below(round_dir, "evidence")
        evidence.mkdir(exist_ok=True)
        attempt = Path(tempfile.mkdtemp(prefix="run-", dir=evidence))
        records = {check["id"]: run_check(root, check, attempt / check["id"]) for check in plan["checks"]}
        require(state == frozen_state(root, round_dir, frozen), "Frozen files changed during verification")
        require(candidate == fingerprint(root, plan["candidate_files"]), "Candidate changed during verification")
        receipt = {"frozen": state, "candidate": candidate, "checks": records}
        write_json(attempt / "receipt.json", receipt, mode="x")
    else:
        require(re.fullmatch(r"run-[a-z0-9_]+", args.attempt), "Invalid attempt name")
        attempt = below(round_dir, f"evidence/{args.attempt}")
        receipt = read_json(attempt / "receipt.json")
        require(receipt["frozen"] == state and receipt["candidate"] == candidate,
                "Receipt does not match the current frozen plan and candidate")
    return summarize(plan, attempt, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project directory")
    parser.add_argument("--round", required=True, help="round directory relative to project")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("freeze")
    actions.add_parser("run")
    actions.add_parser("inspect").add_argument("attempt", help="run-* directory name shown in receipt path")
    try:
        result = execute(parser.parse_args())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        result = {"verdict": "INVALID", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return {"FROZEN": 0, "PASS": 0, "FAIL": 1, "BLOCKED": 2, "INVALID": 3}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
