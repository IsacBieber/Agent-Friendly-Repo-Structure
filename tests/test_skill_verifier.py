import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VERIFY = Path(__file__).resolve().parents[1] / "skills/agent-harness/scripts/verify.py"


class SkillVerifierTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.round = self.root / ".agent-harness/example/3_runs/round_001"
        self.round.mkdir(parents=True)
        self.candidate = self.root / "calculator.py"
        self.candidate.write_text("def add(x, y):\n    return x + y\n", encoding="utf-8")
        self.oracle = self.root / "test_report.py"
        self.oracle.write_text(
            "from pathlib import Path\nimport sys\n"
            "mode, target = sys.argv[1:]\n"
            "nodes = {'pass': '<testcase name=\"addition\"/>',\n"
            "         'fail': '<testcase name=\"addition\"><failure/></testcase>',\n"
            "         'error': '<testcase name=\"addition\"><error/></testcase>',\n"
            "         'skip': '<testcase name=\"addition\"><skipped/></testcase>',\n"
            "         'empty': '', 'missing': ''}\n"
            "if mode != 'missing':\n"
            "    Path(target).write_text('<testsuite>' + nodes[mode] + '</testsuite>')\n"
            "sys.exit({'fail': 1, 'error': 1, 'empty': 5}.get(mode, 0))\n",
            encoding="utf-8",
        )
        self.plan = {
            "requirements": {"R1": "behavior"},
            "candidate_files": [self.candidate.name],
            "checks": [{"id": "example", "tool": "junit", "requirements": ["R1"],
                        "basis": "Test fixture for JUnit output", "inputs": [self.oracle.name],
                        "argv": [sys.executable, self.oracle.name, "pass", "{report}"]}],
        }
        self.input = self.round / "input.md"
        self.input.write_text("- [R1] Addition is correct.\n", encoding="utf-8")

    def freeze(self):
        (self.round / "verification.json").write_text(json.dumps(self.plan), encoding="utf-8")
        return self.invoke("freeze")

    def invoke(self, *args):
        command = [sys.executable, "-B", str(VERIFY), "--root", str(self.root), "--round",
                   str(self.round.relative_to(self.root)), *args]
        result = subprocess.run(command, cwd=self.root, check=False, capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_pass_and_inspect_same_receipt(self):
        self.assertEqual(self.freeze()[0], 0)
        exit_code, result = self.invoke("run")
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["requirements"], {"R1": "PASS"})
        attempt = Path(result["receipt"]).parent
        self.assertEqual(self.invoke("inspect", attempt.name), (0, result))
        self.candidate.write_text("# new candidate\n", encoding="utf-8")
        self.assertEqual(self.invoke("inspect", attempt.name)[1]["verdict"], "INVALID")

    def test_reject_modified_and_missing_evidence(self):
        self.assertEqual(self.freeze()[0], 0)
        for name in ("stdout.log", "report.xml"):
            with self.subTest(file=name):
                attempt = Path(self.invoke("run")[1]["receipt"]).parent
                path = attempt / "example" / name
                if name == "report.xml":
                    path.unlink()
                else:
                    path.write_text("changed", encoding="utf-8")
                self.assertEqual(self.invoke("inspect", attempt.name)[1]["verdict"], "INVALID")

    def test_freeze_rejects_omitted_requirement_or_ruff_as_behavior_proof(self):
        self.input.write_text("- [R1] A\n- [R2] B\n", encoding="utf-8")
        self.assertEqual(self.freeze()[1]["verdict"], "INVALID")
        self.plan["requirements"]["R2"] = "manual"
        self.plan["checks"][0].update(tool="ruff", targets=[self.candidate.name])
        self.assertEqual(self.freeze()[1]["verdict"], "INVALID")

    def test_check_uses_frozen_oracle(self):
        self.assertEqual(self.freeze()[0], 0)
        self.assertEqual(self.invoke("freeze")[1]["verdict"], "INVALID")
        self.oracle.write_text("# replaced oracle\n", encoding="utf-8")
        self.assertEqual(self.invoke("run")[1]["verdict"], "INVALID")

    def test_invalid_if_candidate_changes_mid_run(self):
        text = self.oracle.read_text(encoding="utf-8").replace(
            "sys.exit(", "Path('calculator.py').write_text('# changed during check')\nsys.exit(")
        self.oracle.write_text(text, encoding="utf-8")
        self.assertEqual(self.freeze()[0], 0)
        self.assertEqual(self.invoke("run")[1]["verdict"], "INVALID")
        self.assertEqual(list(self.round.glob("evidence/run-*/receipt.json")), [])

    def test_manual_requirement_stays_blocked(self):
        self.input.write_text("- [R1] A\n- [R2] Review tone.\n", encoding="utf-8")
        self.plan["requirements"]["R2"] = "manual"
        self.assertEqual(self.freeze()[0], 0)
        code, result = self.invoke("run")
        self.assertEqual((code, result["verdict"], result["requirements"]["R2"]), (2, "BLOCKED", "NEEDS_REVIEW"))

    def test_problem_classes(self):
        for mode, expected in (("fail", "FAIL"), ("error", "CHECK_ERROR"), ("skip", "UNVERIFIED"),
                               ("empty", "UNVERIFIED"), ("missing", "CHECK_ERROR")):
            with self.subTest(mode=mode):
                self.plan["checks"][0]["argv"][2] = mode
                self.assertEqual(self.freeze()[0], 0)
                result = self.invoke("run")[1]
                self.assertEqual(result["requirements"]["R1"], expected)
                self.assertEqual(result["verdict"], "FAIL" if expected == "FAIL" else "BLOCKED")
                (self.round / "verification.lock.json").unlink()

    @unittest.skipUnless(importlib.util.find_spec("pytest") and importlib.util.find_spec("ruff"),
                         "pytest and ruff are optional")
    def test_real_pytest_and_ruff(self):
        self.oracle.write_text("from calculator import add\n\ndef test_add():\n    assert add(2, 2) == 4\n",
                               encoding="utf-8")
        self.input.write_text("- [R1] Addition is correct.\n- [R2] Python lint passes.\n", encoding="utf-8")
        self.plan["requirements"]["R2"] = "structure"
        self.plan["checks"] = [
            {"id": "unit", "tool": "pytest", "basis": "Independent sum", "requirements": ["R1"],
             "tests": [self.oracle.name]},
            {"id": "lint", "tool": "ruff", "basis": "Project lint", "requirements": ["R2"],
             "targets": [self.candidate.name]},
        ]
        self.assertEqual(self.freeze()[0], 0)
        code, result = self.invoke("run")
        self.assertEqual((code, result["requirements"]), (0, {"R1": "PASS", "R2": "PASS"}))
        self.candidate.write_text("import math\n\ndef add(x, y):\n    return x - y\n", encoding="utf-8")
        code, result = self.invoke("run")
        self.assertEqual((code, result["requirements"]), (1, {"R1": "FAIL", "R2": "FAIL"}))


if __name__ == "__main__":
    unittest.main()
