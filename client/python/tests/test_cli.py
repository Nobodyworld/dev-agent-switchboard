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


def _make_context_client() -> mock.MagicMock:
    client = mock.MagicMock()
    client.close = mock.Mock()
    client.__enter__.return_value = client

    def _exit(_exc_type, _exc, _tb):
        client.close()
        return False

    client.__exit__.side_effect = _exit
    return client


class RunCommandTests(TestCase):
    def setUp(self) -> None:
        self.args = argparse.Namespace(
            base="http://example.test",
            agent="cli-agent",
            poll_interval=0.1,
            heartbeat_interval=30.0,
        )

    def _make_client(self) -> mock.MagicMock:
        client = _make_context_client()
        client.get_system_state.return_value = {"maintenance_mode": False}
        return client

    def test_registration_failure_returns_error(self) -> None:
        with mock.patch(
            "switchboard_cli.SwitchboardClient",
            side_effect=requests.RequestException("boom"),
        ):
            self.assertEqual(1, switchboard_cli.run_command(self.args))

    def test_checkout_failure_returns_error(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.checkout.side_effect = requests.RequestException("checkout failed")
        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(1, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()

    def test_idle_interrupt_exits_cleanly(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.checkout.return_value = None

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.time.sleep", side_effect=KeyboardInterrupt):
            self.assertEqual(0, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()

    def test_process_task_failure_propagates(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.checkout.side_effect = [{"id": 1}]
        self.args.heartbeat_interval = 500.0

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=False) as proc:
            self.assertEqual(1, switchboard_cli.run_command(self.args))
        proc.assert_called_once()
        called_args, called_kwargs = proc.call_args
        self.assertEqual(called_args[2], 150.0)
        self.assertIsNone(called_kwargs.get("max_heartbeats"))
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()

    def test_process_task_success_loops_until_interrupt(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.checkout.side_effect = [{"id": 1}, None]

        with mock.patch(
            "switchboard_cli.SwitchboardClient", return_value=client
        ), mock.patch("switchboard_cli.process_task", return_value=True), mock.patch(
            "switchboard_cli.time.sleep", side_effect=KeyboardInterrupt
        ):
            self.assertEqual(0, switchboard_cli.run_command(self.args))
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()

    def test_settings_fetch_failure_logs_warning(self) -> None:
        client = self._make_client()
        client.get_settings.side_effect = requests.RequestException("boom")
        client.checkout.side_effect = [None]

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.time.sleep", side_effect=KeyboardInterrupt),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.run_command(self.args))

        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()
        warning_calls = [
            call
            for call in printer.call_args_list
            if "Warning: failed" in str(call)
        ]
        self.assertTrue(warning_calls)

    def test_invalid_lease_payload_emits_warning(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": -1}}
        client.checkout.side_effect = [None]

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.time.sleep", side_effect=KeyboardInterrupt),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.run_command(self.args))

        warnings = [
            call
            for call in printer.call_args_list
            if "non-positive" in str(call)
        ]
        self.assertTrue(warnings)
        client.get_system_state.assert_called_once()

    def test_run_command_exits_when_maintenance_active(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.get_system_state.return_value = {
            "maintenance_mode": True,
            "message": "Upgrading",
        }

        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(2, switchboard_cli.run_command(self.args))

        client.checkout.assert_not_called()
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()

    def test_run_command_exits_when_checkout_reports_maintenance(self) -> None:
        client = self._make_client()
        client.get_settings.return_value = {"lease": {"duration_seconds": 300}}
        client.checkout.return_value = None
        client.last_checkout_reason = "maintenance_mode"
        client.last_checkout_message = "Paused"

        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(2, switchboard_cli.run_command(self.args))

        client.checkout.assert_called_once()
        client.close.assert_called_once()
        client.get_settings.assert_called_once()
        client.get_system_state.assert_called_once()


class ConfigurationCommandTests(TestCase):
    def setUp(self) -> None:
        self.args = argparse.Namespace(
            base="http://example.test",
            agent="config-cli",
            json=False,
        )

    def test_configuration_command_handles_error(self) -> None:
        with mock.patch(
            "switchboard_cli.SwitchboardClient",
            side_effect=requests.RequestException("boom"),
        ):
            self.assertEqual(
                1, switchboard_cli.configuration_command(self.args)
            )

    def test_configuration_command_prints_summary(self) -> None:
        client = _make_context_client()
        client.get_configuration.return_value = {
            "settings": {
                "rate_limit": {
                    "requests": 10,
                    "window_seconds": 5,
                    "enabled": True,
                    "trusted_bypass": [],
                    "trusted_proxies": [],
                },
                "lease": {"duration_seconds": 42},
                "extensions": {
                    "modules": ["alpha"],
                    "registered": [{"name": "alpha"}],
                    "contract_version": "2025.2",
                },
            },
            "storage": {
                "root": "/var/lib/switchboard/files",
                "exists": True,
                "writable": True,
                "free_bytes": 1024,
                "total_bytes": 4096,
            },
            "database": {
                "url": "sqlite://",
                "driver": "sqlite",
                "configured_via_env": False,
            },
            "runtime": {
                "started_at": "2025-02-17T00:00:00Z",
                "uptime_seconds": 12.3,
            },
            "admin": {"configured": True},
            "warnings": ["Check storage permissions."],
            "environment": [
                {
                    "name": "FILES_ROOT",
                    "value": "/var/lib/switchboard/files",
                    "source": "derived",
                }
            ],
        }

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.configuration_command(self.args))

        client.close.assert_called_once()
        client.get_configuration.assert_called_once()
        printed_output = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Rate limit", printed_output)
        self.assertIn("Warnings:", printed_output)

    def test_configuration_command_json_output(self) -> None:
        client = _make_context_client()
        client.get_configuration.return_value = {"settings": {}}
        args = argparse.Namespace(
            base="http://example.test", agent="config-cli", json=True
        )

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.configuration_command(args))

        client.close.assert_called_once()
        client.get_configuration.assert_called_once()
        printer.assert_called_once()

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

    def _install_loop(
        self, error: str | None = None, *, limit_reached: bool = False
    ):
        class DummyLoop:
            def __init__(
                self,
                client,
                task_id,
                interval,
                *,
                _max_heartbeats=None,
            ):
                self.client = client
                self.task_id = task_id
                self.interval = interval
                self.started = False
                self.stopped = False
                self.joined_with = None
                self._error = error
                self._limit_reached = limit_reached

            def start(self):
                self.started = True

            def stop(self):
                self.stopped = True

            def join(self, timeout):
                self.joined_with = timeout

            @property
            def error(self):
                return self._error

            @property
            def limit_reached(self):
                return self._limit_reached

            @property
            def heartbeats_sent(self):  # pragma: no cover - exposed for parity
                return 0

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
        _loop, patcher = self._install_loop()
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

    def test_process_task_auto_abandons_on_limit(self) -> None:
        _loop, patcher = self._install_loop(limit_reached=True)
        self.client.abandon.return_value = True
        with patcher, mock.patch("switchboard_cli.print") as printer:
            self.assertTrue(
                switchboard_cli.process_task(
                    self.client, self.task, 10.0, max_heartbeats=3
                )
            )

        self.client.abandon.assert_called_once_with(self.task["id"])
        printer.assert_any_call(
            "Heartbeat limit reached; abandoning task automatically.",
            file=sys.stderr,
        )

    def test_process_task_aborts_on_loop_error(self) -> None:
        _loop, patcher = self._install_loop(error="Server rejected heartbeat")
        with patcher, mock.patch("switchboard_cli.print") as printer:
            self.assertFalse(
                switchboard_cli.process_task(self.client, self.task, 10.0)
            )

        printer.assert_any_call("Server rejected heartbeat", file=sys.stderr)


class MaintenanceCommandTests(TestCase):
    def test_inspect_maintenance_state(self) -> None:
        args = argparse.Namespace(
            base="http://example.test",
            agent="cli",
            admin_token=None,
            enable=False,
            disable=False,
            message=None,
            expected_version=None,
        )
        client = _make_context_client()
        client.get_system_state.return_value = {
            "maintenance_mode": False,
            "version": 2,
        }

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.maintenance_command(args))

        client.get_system_state.assert_called_once()
        client.set_system_state.assert_not_called()
        printer.assert_any_call("Maintenance mode disabled.")

    def test_toggle_maintenance_state_uses_admin_token(self) -> None:
        args = argparse.Namespace(
            base="http://example.test",
            agent="cli",
            admin_token="token-123",  # noqa: S106 - test fixture token
            enable=True,
            disable=False,
            message="Upgrading",
            expected_version=4,
        )
        client = _make_context_client()
        client.set_system_state.return_value = {"maintenance_mode": True}

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.maintenance_command(args))

        client.set_admin_token.assert_called_with("token-123")
        client.set_system_state.assert_called_once_with(
            True,
            message="Upgrading",
            expected_version=4,
            admin_token="token-123",  # noqa: S106 - test fixture token
        )
        client.get_system_state.assert_not_called()
        printer.assert_any_call("Maintenance mode enabled.")

    def test_toggle_failure_returns_error(self) -> None:
        args = argparse.Namespace(
            base="http://example.test",
            agent="cli",
            admin_token="token-123",  # noqa: S106 - test fixture token
            enable=True,
            disable=False,
            message=None,
            expected_version=None,
        )
        client = _make_context_client()
        client.set_system_state.side_effect = requests.RequestException("boom")

        with mock.patch("switchboard_cli.SwitchboardClient", return_value=client):
            self.assertEqual(1, switchboard_cli.maintenance_command(args))


class AnalyticsCommandTests(TestCase):
    def test_stats_command_formats_table_output(self) -> None:
        args = argparse.Namespace(base="http://example.test", agent="stats", json=False)
        client = _make_context_client()
        client.get_task_analytics.return_value = {
            "total_tasks": 5,
            "pending_tasks": 2,
            "in_progress_tasks": 1,
            "completed_tasks": 2,
            "ready_tasks": 3,
            "blocked_tasks": 1,
            "with_dependencies": 2,
            "without_dependencies": 3,
            "dependency_edges": 4,
            "average_dependencies": 0.8,
            "missing_dependency_tasks": 0,
            "missing_dependency_edges": 0,
        }

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.analytics_command(args))

        client.get_task_analytics.assert_called_once()
        rendered = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("Total tasks", rendered)
        self.assertIn("Blocked", rendered)

    def test_stats_command_supports_json_output(self) -> None:
        args = argparse.Namespace(base="http://example.test", agent="stats", json=True)
        client = _make_context_client()
        payload = {"total_tasks": 7, "ready_tasks": 4}
        client.get_task_analytics.return_value = payload

        with (
            mock.patch("switchboard_cli.SwitchboardClient", return_value=client),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(0, switchboard_cli.analytics_command(args))

        printer.assert_called_once()
        printed_payload = printer.call_args[0][0]
        self.assertIn("\"total_tasks\"", printed_payload)
        self.assertIn("\"ready_tasks\"", printed_payload)

    def test_stats_command_handles_request_errors(self) -> None:
        args = argparse.Namespace(base="http://example.test", agent="stats", json=False)

        with (
            mock.patch(
                "switchboard_cli.SwitchboardClient",
                side_effect=requests.RequestException("boom"),
            ),
            mock.patch("switchboard_cli.print") as printer,
        ):
            self.assertEqual(1, switchboard_cli.analytics_command(args))

        printer.assert_called_with(
            "Failed to fetch task analytics: boom", file=sys.stderr
        )


class LeaseExtractionTests(TestCase):
    def test_extracts_valid_duration(self) -> None:
        lease_seconds, warnings = switchboard_cli.extract_lease_duration(
            {"lease": {"duration_seconds": 120}}
        )

        self.assertEqual(lease_seconds, 120.0)
        self.assertFalse(warnings)

    def test_handles_missing_lease_block(self) -> None:
        lease_seconds, warnings = switchboard_cli.extract_lease_duration({})

        self.assertIsNone(lease_seconds)
        self.assertTrue(any("did not include" in message for message in warnings))

    def test_handles_non_mapping_payload(self) -> None:
        lease_seconds, warnings = switchboard_cli.extract_lease_duration(None)

        self.assertIsNone(lease_seconds)
        self.assertTrue(any("not a mapping" in message for message in warnings))

    def test_handles_non_numeric_duration(self) -> None:
        lease_seconds, warnings = switchboard_cli.extract_lease_duration(
            {"lease": {"duration_seconds": "soon"}}
        )

        self.assertIsNone(lease_seconds)
        self.assertTrue(any("not numeric" in message for message in warnings))

    def test_handles_missing_duration(self) -> None:
        lease_seconds, warnings = switchboard_cli.extract_lease_duration(
            {"lease": {}}
        )

        self.assertIsNone(lease_seconds)
        self.assertTrue(any("missing" in message for message in warnings))


class SanitizeHeartbeatIntervalTests(TestCase):
    def test_defaults_when_request_is_none(self) -> None:
        interval, reason = switchboard_cli.sanitize_heartbeat_interval(None, None)

        self.assertEqual(interval, switchboard_cli.DEFAULT_HEARTBEAT_INTERVAL)
        self.assertIsNone(reason)

    def test_returns_interval_when_positive_without_lease(self) -> None:
        interval, reason = switchboard_cli.sanitize_heartbeat_interval(15.0, None)

        self.assertEqual(interval, 15.0)
        self.assertIsNone(reason)

    def test_halves_interval_when_exceeding_lease(self) -> None:
        interval, reason = switchboard_cli.sanitize_heartbeat_interval(120.0, 60.0)

        self.assertEqual(interval, 30.0)
        self.assertIn("half the lease", reason or "")

    def test_converts_negative_to_safe_default(self) -> None:
        interval, reason = switchboard_cli.sanitize_heartbeat_interval(-5.0, 50.0)

        self.assertEqual(interval, 25.0)
        self.assertIn("non-positive", reason or "")


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
