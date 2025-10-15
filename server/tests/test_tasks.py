
import asyncio, json, os, sys
import httpx
import pytest
from fastapi import status
from server.app import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "OK"

def test_create_and_checkout():
    # create two tasks, one depends on first
    r = client.post("/api/tasks", json={"title":"t1","description":"a","depends_on":[]})
    assert r.status_code == 200
    t1 = r.json()
    r = client.post("/api/tasks", json={"title":"t2","description":"b","depends_on":[t1['id']]})
    assert r.status_code == 200
    client.post("/api/agents", json={"agent_name":"bot1"})
    # checkout should get t1 only
    r = client.post("/api/tasks/checkout", params={"agent_id":"bot1"})
    data = r.json()
    assert data["task"]["id"] == t1["id"]
