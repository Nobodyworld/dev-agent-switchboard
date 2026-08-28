import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest
from scripts import dev


def test_verify_scans_production_server_code_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(
        dev, "_run_command", lambda command: commands.append(list(command))
    )
    monkeypatch.setattr(dev, "cmd_coverage_gate", lambda _args: None)

    dev.cmd_verify(
        Namespace(coverage_json=str(tmp_path / "coverage.json"), skip_audit=True)
    )

    assert [
        sys.executable,
        "-m",
        "bandit",
        "-q",
        "-r",
        "server",
        "-x",
        "server/tests",
    ] in commands
    pytest_command = next(command for command in commands if "pytest" in command)
    assert "--cov=server.observability.overview" in pytest_command


def test_cmd_list_extensions_outputs_builtins(capsys, monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_EXTENSIONS", raising=False)
    monkeypatch.setenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")
    dev.cmd_list_extensions(Namespace())
    output = capsys.readouterr().out
    assert "Extension contract:" in output
    assert "builtin.plan_snapshot" in output


def test_operator_commands_import_from_source_checkout() -> None:
    for command in ("validation-lifecycle", "inspect-validation-runtime"):
        result = subprocess.run(  # noqa: S603
            [sys.executable, "scripts/dev.py", command, "--help"],
            cwd=dev.REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_todo_check_ignores_virtual_environments(tmp_path):
    virtual_env_file = tmp_path / ".venv311" / "dependency.py"
    virtual_env_file.parent.mkdir()
    virtual_env_file.write_text("# TODO(third-party): ignored\n", encoding="utf-8")
    source_file = tmp_path / "source.py"
    source_file.write_text("# TODO(P2, 1d) - valid\n", encoding="utf-8")

    dev.cmd_check_todos(Namespace(root=str(tmp_path)))


def test_todo_check_rejects_unqualified_project_todo(tmp_path):
    source_file = tmp_path / "source.py"
    source_file.write_text("# TODO(owner): missing metadata\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        dev.cmd_check_todos(Namespace(root=str(tmp_path)))
