import argparse
import json
import time
import uuid

import requests

API = __import__("os").getenv("API_URL", "http://api-server:8000")


def post(payload=None, key=None):
    payload = payload or {"client_id": "student", "message": "lab order", "amount": 42.5}
    r = requests.post(f"{API}/orders", json=payload, headers={"Idempotency-Key": key} if key else {}, timeout=10)
    print(r.status_code, json.dumps(r.json(), indent=2))
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=["normal", "idempotency", "rate-limit", "dlq", "backlog", "search", "trace"])
    p.add_argument("--count", type=int, default=25)
    args = p.parse_args()
    if args.scenario == "normal":
        post()
    elif args.scenario == "idempotency":
        key = f"demo-{uuid.uuid4()}"
        first, second = post(key=key), post(key=key)
        assert first.json()["order_id"] == second.json()["order_id"]
        print("Expected: both responses contain the same order_id")
    elif args.scenario == "rate-limit":
        client = f"rate-{uuid.uuid4().hex[:8]}"
        for _ in range(args.count):
            post({"client_id": client, "message": "rate test", "amount": 1})
    elif args.scenario == "dlq":
        r = post({"client_id": "poison", "message": "must reach DLQ", "amount": 1, "simulate_error": True})
        print("Expected: retries, then orders.dlq; order_id:", r.json().get("order_id"))
    elif args.scenario == "backlog":
        for i in range(args.count):
            post({"client_id": f"backlog-{i}", "message": "backlog test", "amount": i + 1})
    elif args.scenario == "search":
        print(requests.get(f"{API}/search", params={"q": "lab"}, timeout=10).json())
    else:
        r = post()
        time.sleep(8)
        print(requests.get(f"{API}/logs/search", params={"trace_id": r.json()["trace_id"]}, timeout=10).json())


if __name__ == "__main__":
    main()
