import argparse
import importlib
import sys
import types
from typing import Any, cast
from unittest import TestCase, mock


class _DummyRequestError(Exception):
    pass


class _DummyHTTPError(_DummyRequestError):
    pass


class _DummySession:
    def request(self, method: str, url: str, **kwargs):  # pragma: no cover - stub
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover - stub
        return None


class _DummyResponse:
    def json(self):  # pragma: no cover - stub
        return {}

    def raise_for_status(self) -> None:  # pragma: no cover - stub
        return None


requests_stub = types.ModuleType("requests")
requests_stub.RequestException = _DummyRequestError
requests_stub.HTTPError = _DummyHTTPError
requests_stub.Session = _DummySession
requests_stub.Response = _DummyResponse
sys.modules["requests"] = requests_stub
requests = cast(Any, requests_stub)


class _DummySwitchboardClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("SwitchboardClient should be patched in tests")


import client.python.switchboard_cli as cli_impl  # noqa: E402

importlib.reload(cli_impl)

import switchboard_cli  # noqa: E402

importlib.reload(switchboard_cli)


class RunCommandTests(TestCase):
    def setUp(self) -> None:
        self.args = argparse.Namespace(
            base="http://example.test",
            agent="cli-agent",
            poll_interval=0.1,
            heartbeat_interval=30.0,
        )

    def test_registration_failure_returns_error(self) -> None:
        with mock.patch(
            "switchboard_cli.SwitchboardClient",
            side_effect=requests.RequestException("boom"),
        ):
            self.assertEqual(1, switchboard_cli.run_command(self.args))

    def test_checkout_failure_returns_error(self) -> None:
        client = mock.Mock()
        client.checkout.side_effect = requests.RequestException("checkout failed")
        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(1, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()

    def test_idle_interrupt_exits_cleanly(self) -> None:
        client = mock.Mock()
        client.checkout.return_value = None

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.time.sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(0, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()

    def test_process_task_failure_propagates(self) -> None:
        client = mock.Mock()
        client.checkout.side_effect = [{"id": 1}]

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=False):
            self.assertEqual(1, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()

    def test_process_task_success_loops_until_interrupt(self) -> None:
        client = mock.Mock()
        client.checkout.side_effect = [{"id": 1}, None]

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=True), mock.patch(
            "switchboard_cli.time.sleep", side_effect=KeyboardInterrupt
        ):
            self.assertEqual(0, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()


class ProcessTaskTests(TestCase):
    def setUp(self) -> None:
        self.task = {
            "id": 5,
            "title": "Write docs",
            "description": "",
            "depends_on": [],
        }
        self.client = mock.Mock()
        self.client.heartbeat.return_value = True

    def _install_loop(self, error: str | None = None):
        class DummyLoop:
            def __init__(self, client, task_id, interval):
                self.client = client
                self.task_id = task_id
                self.interval = interval
                self.started = False
                self.stopped = False
                self.joined_with = None
                self._error = error

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

            def join(self, timeout):
                self.joined_with = timeout

            @property
            def error(self):
                return self._error

        loop = DummyLoop(self.client, self.task["id"], 30.0)
        patcher = mock.patch("switchboard_cli.HeartbeatLoop", return_value=loop)
        return loop, patcher

    def test_process_task_complete_flow(self) -> None:
        loop, patcher = self._install_loop()
        with patcher, mock.patch(
            "switchboard_cli.confirm_completion", return_value=True
        ) as confirm, mock.patch(
            "switchboard_cli.input",
            side_effect=["complete", "All done"],
        ), mock.patch("switchboard_cli.print"):
            self.assertTrue(
                switchboard_cli.process_task(self.client, self.task, 30.0)
            )

        self.assertTrue(loop.started)
        self.assertTrue(loop.stopped)
        self.assertEqual(
            loop.joined_with, switchboard_cli.HEARTBEAT_SHUTDOWN_TIMEOUT
        )
        confirm.assert_called_once()
        self.assertEqual(
            confirm.call_args[0], (self.client, self.task["id"], "All done")
        )
        self.client.heartbeat.assert_not_called()

    def test_process_task_abandon_flow(self) -> None:
        loop, patcher = self._install_loop()
        self.client.abandon.return_value = True
        with patcher, mock.patch(
            "switchboard_cli.input",
            side_effect=["abandon"],
        ), mock.patch("switchboard_cli.print"):
            self.assertTrue(
                switchboard_cli.process_task(self.client, self.task, 30.0)
            )

        self.client.abandon.assert_called_once_with(self.task["id"])
        self.assertTrue(loop.stopped)
        self.assertEqual(
            loop.joined_with, switchboard_cli.HEARTBEAT_SHUTDOWN_TIMEOUT
        )

    def test_process_task_handles_manual_commands(self) -> None:
        loop, patcher = self._install_loop()
        inputs = [
            "heartbeat",
            "status",
            "notes",
            "remember",
            "help",
            "unknown",
            "",
            "abandon",
        ]
        self.client.abandon.return_value = True
        with patcher, mock.patch(
            "switchboard_cli.input", side_effect=inputs
        ), mock.patch("switchboard_cli.print") as printer:
            self.assertTrue(
                switchboard_cli.process_task(self.client, self.task, 10.0)
            )

        self.client.heartbeat.assert_called_once_with(self.task["id"])
        printer.assert_any_call("Unknown command: unknown")

    def test_process_task_aborts_on_loop_error(self) -> None:
        loop, patcher = self._install_loop(error="Server rejected heartbeat")
        with patcher, mock.patch("switchboard_cli.print") as printer:
            self.assertFalse(
                switchboard_cli.process_task(self.client, self.task, 10.0)
            )

        printer.assert_any_call("Server rejected heartbeat", file=sys.stderr)


class HelperFunctionTests(TestCase):
    def test_format_task_renders_dependencies(self) -> None:
        formatted = switchboard_cli.format_task(
            {
                "id": 7,
                "title": "Ship",
                "description": "Deploy the release",
                "depends_on": [1, 2],
            }
        )

        self.assertIn("Task 7: Ship", formatted)
        self.assertIn("Deploy the release", formatted)
        self.assertIn("Depends on: 1, 2", formatted)

    def test_confirm_completion_success(self) -> None:
        client = mock.Mock()
        client.complete.return_value = True
        self.assertTrue(
            switchboard_cli.confirm_completion(client, 9, notes="done")
        )
        client.complete.assert_called_once_with(9, notes="done")

    def test_confirm_completion_handles_http_error(self) -> None:
        client = mock.Mock()
        client.complete.side_effect = requests.HTTPError("fail")

        with mock.patch("switchboard_cli.print") as printer:
            self.assertFalse(
                switchboard_cli.confirm_completion(client, 9, notes=None)
            )

        printer.assert_called()


class MainFunctionTests(TestCase):
    def test_main_without_subcommand_prints_help(self) -> None:
        parser = mock.Mock()
        parser.parse_args.return_value = argparse.Namespace(func=None)
        parser.print_help.return_value = None

        with mock.patch.object(
            switchboard_cli, "build_parser", return_value=parser
        ), mock.patch.object(parser, "print_help") as help_mock:
            self.assertEqual(1, switchboard_cli.main([]))

        help_mock.assert_called_once()

    def test_main_dispatches_to_subcommand(self) -> None:
        func = mock.Mock(return_value=3)
        parser = mock.Mock()
        parser.parse_args.return_value = argparse.Namespace(func=func)

        with mock.patch.object(switchboard_cli, "build_parser", return_value=parser):
            self.assertEqual(3, switchboard_cli.main(["run"]))

        func.assert_called_once()
