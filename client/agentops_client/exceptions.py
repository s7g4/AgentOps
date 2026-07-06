"""Exception hierarchy for the AgentOps client.

Mirrors the server's own typed-exception approach: callers catch
AgentOpsClientError to handle any client failure, or AgentOpsHTTPError
specifically when they need the status code (e.g. to retry on 429/503
but not on 404).
"""

from __future__ import annotations


class AgentOpsClientError(Exception):
    """Base class for all errors raised by this client."""


class AgentOpsHTTPError(AgentOpsClientError):
    """The server responded with a non-2xx status code."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")
