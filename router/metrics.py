"""
metrics.py — Metrics Collection & Aggregation
Collects per-query timing data and computes benchmark statistics:
  - Read Avg Latency, Read P95 Latency
  - Overall Throughput (qps)
  - Load Distribution CV
  - Per-Replica CPU (%)
  - Staleness Rate (%)
  - Router Overhead (ms)
"""

import time
import math
import json
import csv
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional


@dataclass
class QueryRecord:
    """Single query execution record."""
    timestamp: float
    replica_name: str
    query_type: str           # 'read' or 'write'
    complexity: str           # 'simple', 'medium', 'complex'
    latency_ms: float         # Total latency including routing
    routing_overhead_ms: float  # Router decision time
    is_stale: bool = False    # Whether the read returned stale data


class MetricsCollector:
    """
    Collects and aggregates benchmark metrics per strategy run.

    Usage:
        collector = MetricsCollector()
        collector.record_query(...)
        ...
        results = collector.compute_results()
    """

    def __init__(self):
        self.records: list[QueryRecord] = []
        self.replica_query_counts: dict[str, int] = defaultdict(int)
        self.replica_cpu_samples: dict[str, list[float]] = defaultdict(list)
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None

    def start(self):
        """Mark benchmark start."""
        self._start_time = time.monotonic()
        self.records.clear()
        self.replica_query_counts.clear()
        self.replica_cpu_samples.clear()

    def stop(self):
        """Mark benchmark end."""
        self._end_time = time.monotonic()

    def record_query(
        self,
        replica_name: str,
        query_type: str,
        complexity: str,
        latency_ms: float,
        routing_overhead_ms: float,
        is_stale: bool = False,
    ):
        """Record a single query execution."""
        record = QueryRecord(
            timestamp=time.monotonic(),
            replica_name=replica_name,
            query_type=query_type,
            complexity=complexity,
            latency_ms=latency_ms,
            routing_overhead_ms=routing_overhead_ms,
            is_stale=is_stale,
        )
        self.records.append(record)
        self.replica_query_counts[replica_name] += 1

    def record_cpu_sample(self, replica_name: str, cpu_pct: float):
        """Record a CPU usage sample for a replica."""
        self.replica_cpu_samples[replica_name].append(cpu_pct)

    def compute_results(self) -> dict:
        """Compute all benchmark metrics from collected records."""
        read_records = [r for r in self.records if r.query_type == "read"]
        all_records = self.records

        # Duration
        duration_s = (self._end_time or time.monotonic()) - (self._start_time or 0)
        if duration_s <= 0:
            duration_s = 1.0

        results = {}

        # --- Read Avg Latency (ms) ---
        if read_records:
            read_latencies = [r.latency_ms for r in read_records]
            results["read_avg_ms"] = sum(read_latencies) / len(read_latencies)
        else:
            results["read_avg_ms"] = 0.0

        # --- Read P95 Latency (ms) ---
        if read_records:
            sorted_lat = sorted(r.latency_ms for r in read_records)
            idx = int(math.ceil(0.95 * len(sorted_lat))) - 1
            idx = max(0, min(idx, len(sorted_lat) - 1))
            results["read_p95_ms"] = sorted_lat[idx]
        else:
            results["read_p95_ms"] = 0.0

        # --- Overall Throughput (qps) ---
        results["throughput_qps"] = len(all_records) / duration_s

        # --- Load Distribution CV ---
        counts = list(self.replica_query_counts.values())
        if counts and len(counts) > 1:
            mean_c = sum(counts) / len(counts)
            if mean_c > 0:
                variance = sum((c - mean_c) ** 2 for c in counts) / len(counts)
                std_c = math.sqrt(variance)
                results["load_cv"] = std_c / mean_c
            else:
                results["load_cv"] = 0.0
        else:
            results["load_cv"] = 0.0

        # --- Per-Replica CPU (%) ---
        cpu_avgs = {}
        for name, samples in self.replica_cpu_samples.items():
            if samples:
                cpu_avgs[name] = sum(samples) / len(samples)
            else:
                cpu_avgs[name] = 0.0
        results["per_replica_cpu"] = cpu_avgs
        if cpu_avgs:
            results["avg_cpu_pct"] = sum(cpu_avgs.values()) / len(cpu_avgs)
        else:
            results["avg_cpu_pct"] = 0.0

        # --- Staleness Rate (%) ---
        if read_records:
            stale_count = sum(1 for r in read_records if r.is_stale)
            results["staleness_pct"] = (stale_count / len(read_records)) * 100.0
        else:
            results["staleness_pct"] = 0.0

        # --- Router Overhead (ms) ---
        if all_records:
            overheads = [r.routing_overhead_ms for r in all_records]
            results["router_overhead_ms"] = sum(overheads) / len(overheads)
        else:
            results["router_overhead_ms"] = 0.0

        # --- Distribution details ---
        results["replica_query_counts"] = dict(self.replica_query_counts)
        results["total_queries"] = len(all_records)
        results["total_reads"] = len(read_records)
        results["total_writes"] = len(all_records) - len(read_records)
        results["duration_s"] = duration_s

        return results

    def export_json(self, filepath: str):
        """Export results to JSON."""
        results = self.compute_results()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

    def export_csv(self, filepath: str):
        """Export raw records to CSV."""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "replica", "type", "complexity",
                "latency_ms", "routing_overhead_ms", "is_stale"
            ])
            for r in self.records:
                writer.writerow([
                    r.timestamp, r.replica_name, r.query_type,
                    r.complexity, f"{r.latency_ms:.3f}",
                    f"{r.routing_overhead_ms:.3f}", r.is_stale
                ])

    def reset(self):
        """Reset collector for a new run."""
        self.records.clear()
        self.replica_query_counts.clear()
        self.replica_cpu_samples.clear()
        self._start_time = None
        self._end_time = None
