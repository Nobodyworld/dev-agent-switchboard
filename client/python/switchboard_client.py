
import requests
from typing import Optional, Dict, Any, List

class SwitchboardClient:
    def __init__(self, base_url: str, agent_id: str, *, auto_register: bool = True, session: Optional[requests.Session] = None):
        self.base = base_url.rstrip('/')
        self.agent_id = agent_id
        self._session = session or requests.Session()
        if auto_register:
            self.register()

    @property
    def session(self) -> requests.Session:
        return self._session

    def register(self) -> Dict[str, Any]:
        r = self.session.post(f"{self.base}/api/agents", json={"agent_name": self.agent_id})
        r.raise_for_status()
        return r.json()

    def checkout(self) -> Optional[Dict[str, Any]]:
        r = self.session.post(f"{self.base}/api/tasks/checkout", params={"agent_id": self.agent_id})
        r.raise_for_status()
        data = r.json()
        return data.get("task")

    def heartbeat(self, task_id: int) -> bool:
        r = self.session.post(f"{self.base}/api/tasks/{task_id}/heartbeat", params={"agent_id": self.agent_id})
        return r.ok and r.json().get("ok", False)

    def complete(self, task_id: int, notes: str="") -> bool:
        r = self.session.post(
            f"{self.base}/api/tasks/{task_id}/complete",
            params={"agent_id": self.agent_id},
            json={"notes": notes},
        )
        return r.ok and r.json().get("ok", False)

    def abandon(self, task_id: int) -> bool:
        r = self.session.post(f"{self.base}/api/tasks/{task_id}/abandon", params={"agent_id": self.agent_id})
        return r.ok and r.json().get("ok", False)

    def put_file(self, path: str, content: bytes) -> str:
        r = self.session.put(f"{self.base}/api/files/{path}", data=content)
        r.raise_for_status()
        return r.json()["url"]

    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"status": status} if status else None
        r = self.session.get(f"{self.base}/api/tasks", params=params)
        r.raise_for_status()
        return r.json()
