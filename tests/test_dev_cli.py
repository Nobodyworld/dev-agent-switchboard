from argparse import Namespace

from scripts import dev


def test_cmd_list_extensions_outputs_builtins(capsys, monkeypatch):
    monkeypatch.delenv("SWITCHBOARD_EXTENSIONS", raising=False)
    monkeypatch.setenv("SWITCHBOARD_ENABLE_BUILTIN_EXTENSIONS", "1")
    dev.cmd_list_extensions(Namespace())
    output = capsys.readouterr().out
    assert "Extension contract:" in output
    assert "builtin.plan_snapshot" in output
