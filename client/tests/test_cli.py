"""CLI tests via typer's CliRunner, driven against a real server subprocess.

The CLI builds its own client per command using AGENTOPS_BASE_URL, which
means it needs a real bound base_url. The server runs as a genuine
subprocess (not an in-process thread) so its structlog JSON output goes to
its own stdout pipe rather than bleeding into CliRunner's captured stdout —
which is also a more faithful test of the packaged CLI talking to a
separately-running server, the way it's actually used.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentops_client.cli import app as cli_app

REPO_ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server_base_url():  # noqa: ANN201
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "app.main"],
        cwd=REPO_ROOT,
        env={"HOST": "127.0.0.1", "PORT": str(port), "PATH": os.environ["PATH"]},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{base_url}/health", timeout=1)  # noqa: S310
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("server did not become ready in time")
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_health_command(live_server_base_url: str) -> None:
    result = runner.invoke(cli_app, ["health"], env={"AGENTOPS_BASE_URL": live_server_base_url})
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ok"


def test_tools_command(live_server_base_url: str) -> None:
    result = runner.invoke(cli_app, ["tools"], env={"AGENTOPS_BASE_URL": live_server_base_url})
    assert result.exit_code == 0
    assert "refund_policy" in json.loads(result.stdout)


def test_send_command(live_server_base_url: str) -> None:
    result = runner.invoke(
        cli_app,
        ["send", "I want a refund", "--customer-id", "cust_1"],
        env={"AGENTOPS_BASE_URL": live_server_base_url},
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["intent"] == "refund"


def test_workflows_create_and_run(live_server_base_url: str, tmp_path: Path) -> None:
    spec = tmp_path / "wf.json"
    steps = [{"id": "s", "tool_name": "refund_policy"}]
    spec.write_text(json.dumps({"name": "cli-e2e", "steps": steps}))

    created = runner.invoke(
        cli_app,
        ["workflows", "create", "--file", str(spec)],
        env={"AGENTOPS_BASE_URL": live_server_base_url},
    )
    assert created.exit_code == 0
    wf_id = json.loads(created.stdout)["id"]

    ran = runner.invoke(
        cli_app,
        ["workflows", "run", wf_id],
        env={"AGENTOPS_BASE_URL": live_server_base_url},
    )
    assert ran.exit_code == 0
    assert json.loads(ran.stdout)["status"] == "completed"


def test_agents_list_and_route(live_server_base_url: str) -> None:
    listed = runner.invoke(
        cli_app, ["agents", "list"], env={"AGENTOPS_BASE_URL": live_server_base_url}
    )
    assert listed.exit_code == 0
    names = {a["name"] for a in json.loads(listed.stdout)}
    assert "support_pipeline" in names

    routed = runner.invoke(
        cli_app,
        ["agents", "route", "please echo this"],
        env={"AGENTOPS_BASE_URL": live_server_base_url},
    )
    assert routed.exit_code == 0
    assert json.loads(routed.stdout)["status"] == "completed"


def test_unknown_workflow_reports_error(live_server_base_url: str) -> None:
    result = runner.invoke(
        cli_app,
        ["workflows", "get", "does-not-exist"],
        env={"AGENTOPS_BASE_URL": live_server_base_url},
    )
    assert result.exit_code == 1
