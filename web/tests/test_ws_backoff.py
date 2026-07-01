from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NODE_EXECUTABLE = shutil.which("node")

if NODE_EXECUTABLE is None:  # pragma: no cover - fallback for environments without Node
    pytest.skip(
        "node runtime is required for websocket backoff tests",
        allow_module_level=True,
    )

NODE_PATH = Path(NODE_EXECUTABLE)

EXPECTED_ATTEMPT_COUNT = 5
EXPECTED_DELAYS = [100, 200, 400, 800, 1000]
EXPECTED_FIRST_MIN = 200
EXPECTED_FIRST_MAX = 250
EXPECTED_THIRD_MIN = 600
EXPECTED_THIRD_MAX = 1000
EXPECTED_THIRD_DELAY = 800
EXPECTED_RESET_DELAY = 100


def _run_node(script: str) -> dict[str, object]:
    result = subprocess.run(
        [str(NODE_PATH), "--input-type=module", "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    if result.stderr:
        raise RuntimeError(result.stderr)
    return json.loads(stdout or "{}")


def test_backoff_exponential_growth_respects_cap() -> None:
    script = """
import { BackoffController } from './web/static/ws_backoff.js';

const controller = new BackoffController({
  initialDelayMs: 100,
  maxDelayMs: 1000,
  multiplier: 2,
  jitterRatio: 0,
  random: () => 0,
});

const delays = [];
for (let i = 0; i < 5; i += 1) {
  delays.push(controller.nextDelay());
}

console.log(JSON.stringify({ attempts: controller.attempts, delays }));
"""
    result = _run_node(script)
    assert result["attempts"] == EXPECTED_ATTEMPT_COUNT
    assert result["delays"] == EXPECTED_DELAYS


def test_backoff_applies_jitter_within_expected_bounds() -> None:
    script = """
import { BackoffController } from './web/static/ws_backoff.js';

const minController = new BackoffController({
  initialDelayMs: 200,
  maxDelayMs: 10000,
  multiplier: 2,
  jitterRatio: 0.25,
  random: () => 0,
});

const maxController = new BackoffController({
  initialDelayMs: 200,
  maxDelayMs: 10000,
  multiplier: 2,
  jitterRatio: 0.25,
  random: () => 1,
});

const midController = new BackoffController({
  initialDelayMs: 200,
  maxDelayMs: 10000,
  multiplier: 2,
  jitterRatio: 0.25,
  random: () => 0.5,
});

const firstMin = minController.nextDelay();
const firstMax = maxController.nextDelay();

midController.nextDelay();
midController.nextDelay();
const thirdDelay = midController.nextDelay();

const baseThird = 200 * Math.pow(2, 2);
const jitterThird = baseThird * 0.25;
const thirdMin = Math.max(200, baseThird - jitterThird);
const thirdMax = baseThird + jitterThird;

console.log(JSON.stringify({ firstMin, firstMax, thirdDelay, thirdMin, thirdMax }));
"""
    result = _run_node(script)
    assert result["firstMin"] == EXPECTED_FIRST_MIN
    assert result["firstMax"] == EXPECTED_FIRST_MAX
    assert result["thirdMin"] == EXPECTED_THIRD_MIN
    assert result["thirdMax"] == EXPECTED_THIRD_MAX
    assert result["thirdDelay"] == EXPECTED_THIRD_DELAY


def test_backoff_reset_clears_attempt_attempts() -> None:
    script = """
import { BackoffController } from './web/static/ws_backoff.js';

const controller = new BackoffController({
  initialDelayMs: 100,
  maxDelayMs: 1000,
  multiplier: 2,
  jitterRatio: 0,
  random: () => 0,
});

controller.nextDelay();
controller.nextDelay();
controller.reset();
const delayAfterReset = controller.nextDelay();

console.log(JSON.stringify({ attempts: controller.attempts, delayAfterReset }));
"""
    result = _run_node(script)
    assert result["attempts"] == 1
    assert result["delayAfterReset"] == EXPECTED_RESET_DELAY
