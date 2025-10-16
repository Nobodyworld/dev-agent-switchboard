import argparse
import sys
import types
from unittest import TestCase, mock


class _DummyRequestException(Exception):
    pass


class _DummyHTTPError(_DummyRequestException):
    pass


sys.modules.setdefault(
    "requests",
    types.SimpleNamespace(
        RequestException=_DummyRequestException, HTTPError=_DummyHTTPError
    ),
)


class _DummySwitchboardClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError("SwitchboardClient should be patched in tests")


sys.modules.setdefault(
    "switchboard_client",
    types.SimpleNamespace(SwitchboardClient=_DummySwitchboardClient),
)

import requests  # type: ignore  # noqa: E402  (module injected above)


class RunCommandTests(TestCase):
    def setUp(self) -> None:
        self.args = argparse.Namespace(
            base="http://example.test",
            agent="cli-agent",
            poll_interval=0.1,
            heartbeat_interval=30.0,
        )

    def test_registration_failure_returns_error(self) -> None:
        from switchboard_cli import run_command

        with mock.patch(
            "switchboard_cli.SwitchboardClient",
            side_effect=requests.RequestException("boom"),
        ):
            self.assertEqual(1, run_command(self.args))

    def test_checkout_failure_returns_error(self) -> None:
        from switchboard_cli import run_command

        client = mock.Mock()
        client.checkout.side_effect = requests.RequestException("checkout failed")
        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(1, run_command(self.args))

    def test_idle_interrupt_exits_cleanly(self) -> None:
        from switchboard_cli import run_command

        client = mock.Mock()
        client.checkout.return_value = None

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.time.sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(0, run_command(self.args))

    def test_process_task_failure_propagates(self) -> None:
        from switchboard_cli import run_command

        client = mock.Mock()
        client.checkout.side_effect = [{"id": 1}]

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=False):
            self.assertEqual(1, run_command(self.args))

    def test_process_task_success_loops_until_interrupt(self) -> None:
        from switchboard_cli import run_command

        client = mock.Mock()
        client.checkout.side_effect = [{"id": 1}, None]

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=True), mock.patch(
            "switchboard_cli.time.sleep", side_effect=KeyboardInterrupt
        ):
            self.assertEqual(0, run_command(self.args))
