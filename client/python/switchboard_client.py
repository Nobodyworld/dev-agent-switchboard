
import time, requests
from typing import Optional, Dict, Any


DEFAULT_REQUEST_TIMEOUT = 10.0


class SwitchboardClient:
    def __init__(self, base_url: str, agent_id: str, request_timeout: float = DEFAULT_REQUEST_TIMEOUT):
        self.base = base_url.rstrip('/')
        self.agent_id = agent_id
        self.last_checkout_reason: Optional[str] = None
        self._timeout = request_timeout
        r = requests.post(f"{self.base}/api/agents", json={"agent_name": agent_id}, timeout=self._timeout)
        r.raise_for_status()

    def checkout(self) -> Optional[Dict[str, Any]]:
        r = requests.post(
            f"{self.base}/api/tasks/checkout",
            params={"agent_id": self.agent_id},
            timeout=self._timeout,
        )
        r.raise_for_status()
        data = r.json()
        self.last_checkout_reason = data.get("reason")
        return data.get("task")

    def heartbeat(self, task_id: int) -> bool:
        r = requests.post(
            f"{self.base}/api/tasks/{task_id}/heartbeat",
            params={"agent_id": self.agent_id},
            timeout=self._timeout,
        )
        return r.ok and r.json().get("ok", False)

    def complete(self, task_id: int, notes: str="") -> bool:
        r = requests.post(
            f"{self.base}/api/tasks/{task_id}/complete",
            params={"agent_id": self.agent_id},
            json={"notes": notes},
            timeout=self._timeout,
        )
        return r.ok and r.json().get("ok", False)

    def abandon(self, task_id: int) -> bool:
        r = requests.post(
            f"{self.base}/api/tasks/{task_id}/abandon",
            params={"agent_id": self.agent_id},
            timeout=self._timeout,
        )
        return r.ok and r.json().get("ok", False)

    def put_file(self, path: str, content: bytes) -> str:
        r = requests.put(f"{self.base}/api/files/{path}", data=content, timeout=self._timeout)
        r.raise_for_status()
        return r.json()["url"]
