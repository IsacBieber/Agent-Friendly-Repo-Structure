# 本地验证

运行器需要 Python 3.9 及以上。`pytest` 和 `ruff` 适配器使用运行器所在 Python 环境里已有的工具。`junit` 可使用项目已有、会产出 JUnit XML 的命令。优先沿用项目配置和已安装工具。

环境无法运行随包验证器时，可按项目方式执行可用检查，把命令、实际观察和证据位置记入 `check.md`，并注明验证方式。缺少证据的项目保留未验证状态。

## 开工前冻结

在本轮 `input.md` 中把要验收的条目写成 `- [R1] 预期结果`。验证计划列出所有这些要求、候选文件、每项验证的依据和它会读取的本轮固定文件。验收依据用已有独立测试、原始规格、参考数据或有明确期望的样例。Work 执行前确定它们。业务文件可在本轮新建，冻结的测试、输入、配置和样例此时需要存在。

在当轮目录保存 `verification.json`，例如：

```json
{
  "requirements": {"R1": "behavior", "R2": "structure", "R3": "manual"},
  "candidate_files": ["src/export.py"],
  "checks": [
    {
      "id": "export-rows",
      "tool": "pytest",
      "requirements": ["R1"],
      "basis": "已有测试按输入表格逐行核对导出结果，含空值和最后一行",
      "tests": ["tests/test_export.py"],
      "inputs": ["tests/fixtures/expected.csv", "pyproject.toml"]
    },
    {
      "id": "lint",
      "tool": "ruff",
      "requirements": ["R2"],
      "basis": "项目的 Python 静态检查约定",
      "targets": ["src/export.py"],
      "inputs": ["pyproject.toml"]
    }
  ]
}
```

路径相对项目根目录，使用文件路径。列上候选依赖以及测试实际用到的配置、样例和辅助文件。Ruff 的证明范围为结构检查。已有项目测试命令也可用 `tool: "junit"`，在 `argv` 字符串数组中用一次 `{report}` 指定报告输出位置，并在 `inputs` 绑定实际判据文件。通过项目约定核对命令及其参数再执行。默认单项超时 120 秒，可用 `timeout_seconds` 指定。判据或计划有实质变化时在新一轮重新冻结。

## 执行和核验

工作目录为项目根目录，用技能安装目录中的 `scripts/verify.py` 实际路径替换 `VERIFY`，用当轮相对路径替换 `ROUND`。

```text
python VERIFY --round ROUND freeze
python VERIFY --round ROUND run
python VERIFY --round ROUND inspect run-xxxxxxxx
```

`run` 会为每次执行创建独立的 `evidence/run-*`，保存 stdout、stderr、JUnit 报告和 `receipt.json`。`inspect` 使用相同的运行器版本重新核对冻结文件、当前候选和原始证据，再输出逐项摘要。优先读摘要，仅在诊断失败、判断覆盖或独立复核时打开具体记录。

- `PASS` 表示计划中登记的要求有通过的机器证据。空测试、跳过的测试、缺少验证项和人工判据保留为待处理。
- `FAIL` 表示报告含已识别的断言失败或静态检查发现。工具、环境和报告故障单独列为 `CHECK_ERROR`。
- `INVALID` 表示输入、候选或证据无法绑定到这次结果。`NEEDS_REVIEW` 需要人工或独立评审，状态写入验收页。

回执证明的是声明范围、当次工具输出和前后文件内容一致。覆盖正确性由独立复核判断，未声明的依赖、运行中被改回的内容和执行环境变化须另行评估。工作区文件权限决定谁可以改写记录。用户验收与正式发布按各自流程处理。
