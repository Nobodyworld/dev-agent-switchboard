
import time
from switchboard_client import SwitchboardClient

if __name__ == "__main__":
    client = SwitchboardClient("http://localhost:8000", "codex-1")
    while True:
        task = client.checkout()
        if not task:
            print("No tasks available; sleeping...")
            time.sleep(5)
            continue
        tid = task["id"]
        print("Checked out:", task)
        # simulate work loop with heartbeats
        for _ in range(3):
            ok = client.heartbeat(tid)
            print("heartbeat", ok)
            time.sleep(2)
        ok = client.complete(tid, notes="done")
        print("complete", ok)
