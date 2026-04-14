"""
workload.py — Workload Profiles for Read/Write Ratio Control

Manages the mix of read vs write queries according to:
  - Read-Heavy: 95% reads, 5% writes (ratio 95:5)
  - Balanced:   70% reads, 30% writes (ratio 70:30)
"""

import random
from dataclasses import dataclass

from benchmark.queries import QueryTemplate, get_query_pool


@dataclass
class WorkloadConfig:
    """Configuration for a workload profile."""
    name: str
    read_pct: float     # Percentage of reads (0-100)
    write_pct: float    # Percentage of writes (0-100)
    label: str          # Display label


# Predefined workload profiles
WORKLOAD_PROFILES = {
    "read_heavy": WorkloadConfig(
        name="read_heavy",
        read_pct=95.0,
        write_pct=5.0,
        label="Read-Heavy (95:5)",
    ),
    "balanced": WorkloadConfig(
        name="balanced",
        read_pct=70.0,
        write_pct=30.0,
        label="Balanced (70:30)",
    ),
}


class WorkloadGenerator:
    """
    Generates a stream of queries according to a workload profile.

    Each call to next_query() returns a QueryTemplate selected
    based on the configured read/write ratio.
    """

    def __init__(
        self,
        complexity: str,
        workload_name: str,
        seed: int = 42,
    ):
        self.complexity = complexity
        self.config = WORKLOAD_PROFILES[workload_name]
        self.seed = seed
        self.rng = random.Random(seed)

        # Get query pools
        self._read_queries, self._write_queries = get_query_pool(
            complexity=complexity, seed=seed
        )

        # Threshold for read vs write decision
        self._read_threshold = self.config.read_pct / 100.0

        # Separate RNG for query parameter generation (each query call)
        self._param_rng = random.Random(seed + 1000)

        # Counters
        self.total_generated = 0
        self.reads_generated = 0
        self.writes_generated = 0

    def next_query(self) -> QueryTemplate:
        """
        Get the next query based on read/write ratio.
        Returns a QueryTemplate with fresh parameters.
        """
        if self.rng.random() < self._read_threshold:
            # Read query
            template = self.rng.choice(self._read_queries)
            self.reads_generated += 1
        else:
            # Write query
            template = self.rng.choice(self._write_queries)
            self.writes_generated += 1

        self.total_generated += 1
        return template

    def get_stats(self) -> dict:
        """Get generation statistics."""
        total = max(self.total_generated, 1)
        return {
            "total": self.total_generated,
            "reads": self.reads_generated,
            "writes": self.writes_generated,
            "actual_read_pct": (self.reads_generated / total) * 100,
            "target_read_pct": self.config.read_pct,
        }

    def reset(self, new_seed: int = None):
        """Reset generator for a new run."""
        if new_seed is not None:
            self.seed = new_seed
        self.rng = random.Random(self.seed)
        self._param_rng = random.Random(self.seed + 1000)
        self._read_queries, self._write_queries = get_query_pool(
            complexity=self.complexity, seed=self.seed
        )
        self.total_generated = 0
        self.reads_generated = 0
        self.writes_generated = 0


def all_workload_names() -> list[str]:
    """Return all available workload profile names."""
    return list(WORKLOAD_PROFILES.keys())


def get_workload_config(name: str) -> WorkloadConfig:
    """Get workload config by name."""
    if name not in WORKLOAD_PROFILES:
        available = ", ".join(WORKLOAD_PROFILES.keys())
        raise ValueError(f"Unknown workload '{name}'. Available: {available}")
    return WORKLOAD_PROFILES[name]
