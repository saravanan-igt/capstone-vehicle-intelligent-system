"""Closed-loop load test against the FastAPI backend (bypasses the BFF; dev auth headers).

    python loadtest/load_test.py --base-url http://127.0.0.1:8001 --secret <DEV_BFF_SHARED_SECRET> \
        --workers 8 --duration 30 --out loadtest/results.json

Each iteration runs one applicant journey: create application -> evaluate -> affordable vehicles
(approved only) -> catalogue page. Point it at a disposable database: it creates real records."""

import argparse
import json
import random
import statistics
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

APPLICANTS = ("u-alice", "u-arjun")


def applicant_payload(rng: random.Random) -> dict:
    return {
        "income_amount": str(rng.choice([40000, 60000, 90000, 120000, 200000])), "income_frequency": "monthly",
        "credit_score": rng.randint(600, 850), "score_provider": "CIBIL", "employment_category": "salaried",
        "employment_months": rng.randint(3, 120), "existing_monthly_obligations": str(rng.choice([0, 5000, 15000])),
        "active_loans": rng.randint(0, 3),
        "requested_principal": str(rng.choice([300000, 800000, 1200000, 2000000])),
        "requested_tenure_months": rng.choice([36, 60, 84]),
        "down_payment_available": str(rng.choice([50000, 200000, 400000])),
        "currency": "INR", "jurisdiction": "IN", "region": "IN-MH",
    }


class Recorder:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, int] = defaultdict(int)

    def call(self, name: str, fn):  # type: ignore[no-untyped-def]
        start = time.perf_counter()
        try:
            resp = fn()
        except httpx.HTTPError:
            with self.lock:
                self.errors[name] += 1
            return None
        elapsed = (time.perf_counter() - start) * 1000
        with self.lock:
            self.latency[name].append(elapsed)
            if resp.status_code >= 400:
                self.errors[name] += 1
        return resp


def worker(base: str, secret: str, deadline: float, seed: int, rec: Recorder) -> int:
    rng = random.Random(seed)
    journeys = 0
    with httpx.Client(base_url=base, timeout=30) as client:
        while time.perf_counter() < deadline:
            headers = {"X-Dev-User": rng.choice(APPLICANTS), "X-Dev-Secret": secret}
            created = rec.call("POST /v1/applications",
                               lambda: client.post("/v1/applications", json=applicant_payload(rng), headers=headers))
            if created is None or created.status_code != 201:
                continue
            app_id = created.json()["id"]
            decided = rec.call("POST /v1/applications/{id}/evaluate",
                               lambda: client.post(f"/v1/applications/{app_id}/evaluate", headers=headers))
            if decided is not None and decided.status_code == 201 and decided.json()["outcome"] == "APPROVED":
                decision_id = decided.json()["id"]
                rec.call("GET /v1/decisions/{id}/vehicles",
                         lambda: client.get(f"/v1/decisions/{decision_id}/vehicles", headers=headers))
            rec.call("GET /v1/vehicles", lambda: client.get("/v1/vehicles?limit=20", headers=headers))
            journeys += 1
    return journeys


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--secret", required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--duration", type=float, default=30)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rec = Recorder()
    started = time.perf_counter()
    deadline = started + args.duration
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        journeys = sum(pool.map(lambda i: worker(args.base_url, args.secret, deadline, i, rec), range(args.workers)))
    wall = time.perf_counter() - started

    endpoints = {}
    for name, values in sorted(rec.latency.items()):
        endpoints[name] = {"requests": len(values), "errors": rec.errors.get(name, 0),
                           "rps": round(len(values) / wall, 1), "p50_ms": round(statistics.median(values), 1),
                           "p95_ms": round(percentile(values, 95), 1), "p99_ms": round(percentile(values, 99), 1),
                           "max_ms": round(max(values), 1)}
    total = sum(e["requests"] for e in endpoints.values())
    summary = {"workers": args.workers, "duration_s": round(wall, 1), "journeys": journeys,
               "total_requests": total, "total_rps": round(total / wall, 1),
               "total_errors": sum(rec.errors.values()), "endpoints": endpoints}
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps(summary, indent=2), "utf-8")


if __name__ == "__main__":
    main()
