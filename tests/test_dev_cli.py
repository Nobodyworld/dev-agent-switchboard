from argparse import Namespace

import pytest
from scripts import dev


def test_cmd_list_extensions_outputs_builtins(capsys, monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_EXTENSIONS", raising=False)
    monkeypatch.setenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")
    dev.cmd_list_extensions(Namespace())
    output = capsys.readouterr().out
    assert "Extension contract:" in output
    assert "builtin.plan_snapshot" in output


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
