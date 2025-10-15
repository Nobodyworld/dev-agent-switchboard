
import time, requests
from typing import Optional, Dict, Any

class SwitchboardClient:
    def __init__(self, base_url: str, agent_id: str):
        self.base = base_url.rstrip('/')
        self.agent_id = agent_id
        requests.post(f"{self.base}/api/agents", json={"agent_name": agent_id})

    def checkout(self) -> Optional[Dict[str, Any]]:
        r = requests.post(f"{self.base}/api/tasks/checkout", params={"agent_id": self.agent_id})
        r.raise_for_status()
        data = r.json()
        return data.get("task")

    def heartbeat(self, task_id: int) -> bool:
        r = requests.post(f"{self.base}/api/tasks/{task_id}/heartbeat", params={"agent_id": self.agent_id})
        return r.ok and r.json().get("ok", False)

    def complete(self, task_id: int, notes: str="") -> bool:
        r = requests.post(f"{self.base}/api/tasks/{task_id}/complete", params={"agent_id": self.agent_id}, json={"notes": notes})
        return r.ok and r.json().get("ok", False)

    def abandon(self, task_id: int) -> bool:
        r = requests.post(f"{self.base}/api/tasks/{task_id}/abandon", params={"agent_id": self.agent_id})
        return r.ok and r.json().get("ok", False)

    def put_file(self, path: str, content: bytes) -> str:
        r = requests.put(f"{self.base}/api/files/{path}", data=content)
        r.raise_for_status()
        return r.json()["url"]
