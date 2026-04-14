"""
strategies.py — 5 Pluggable Query Routing Strategies
Each strategy selects which replica to route a read query to.

Strategies:
  1. RoundRobinStrategy       — Circular selection
  2. LoadBasedStrategy         — Lowest CPU load
  3. LatencyBasedStrategy      — Lowest EMA latency
  4. WeightedRoundRobinStrategy — Weighted circular (proportional to CPU capacity)
  5. LeastConnectionsStrategy  — Fewest active connections
"""

from abc import ABC, abstractmethod
from typing import Optional


class ReplicaInfo:
    """Runtime state for a single replica."""

    def __init__(self, name: str, host: str, port: int, weight: int = 1):
        self.name = name
        self.host = host
        self.port = port
        self.weight = weight            # For weighted round-robin

        # Health & metrics (updated by health checker)
        self.healthy: bool = True
        self.ema_latency_ms: float = 0.0   # EMA-smoothed latency
        self.cpu_pct: float = 0.0          # Current CPU usage %
        self.active_connections: int = 0   # Current active connections
        self.replication_lag_bytes: int = 0

    def __repr__(self):
        return (f"ReplicaInfo({self.name}, healthy={self.healthy}, "
                f"ema_lat={self.ema_latency_ms:.1f}ms, "
                f"cpu={self.cpu_pct:.1f}%, "
                f"conns={self.active_connections})")


class RoutingStrategy(ABC):
    """Abstract base class for routing strategies."""

    @abstractmethod
    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        """
        Select a replica to route a read query to.
        Only healthy replicas are passed in.
        Returns None if no suitable replica found.
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """Strategy display name."""
        pass

    def reset(self):
        """Reset any internal state (called between benchmark runs)."""
        pass


# =============================================================================
# 1. Round-Robin Strategy
# =============================================================================
class RoundRobinStrategy(RoutingStrategy):
    """Simple circular selection across all healthy replicas."""

    def __init__(self):
        self._index = 0

    def name(self) -> str:
        return "RoundRobin"

    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        if not replicas:
            return None
        replica = replicas[self._index % len(replicas)]
        self._index += 1
        return replica

    def reset(self):
        self._index = 0


# =============================================================================
# 2. Load-Based Strategy
# =============================================================================
class LoadBasedStrategy(RoutingStrategy):
    """Select the replica with the lowest current CPU usage."""

    def name(self) -> str:
        return "Load-Based"

    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        if not replicas:
            return None
        return min(replicas, key=lambda r: r.cpu_pct)


# =============================================================================
# 3. Latency-Based Strategy
# =============================================================================
class LatencyBasedStrategy(RoutingStrategy):
    """Select the replica with the lowest EMA-smoothed latency."""

    def name(self) -> str:
        return "Latency-Based"

    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        if not replicas:
            return None
        return min(replicas, key=lambda r: r.ema_latency_ms)


# =============================================================================
# 4. Weighted Round-Robin Strategy
# =============================================================================
class WeightedRoundRobinStrategy(RoutingStrategy):
    """
    Weighted circular selection based on replica CPU capacity.
    Higher-capacity replicas receive proportionally more queries.
    Weights: replica1=4, replica2=2, replica3=1 (matching 2/1/0.5 CPU ratio).

    Uses a smooth weighted round-robin (Nginx-style) for even distribution.
    """

    def __init__(self):
        self._current_weights: dict[str, float] = {}

    def name(self) -> str:
        return "Weighted-RR"

    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        if not replicas:
            return None

        # Initialize current weights if needed
        for r in replicas:
            if r.name not in self._current_weights:
                self._current_weights[r.name] = 0.0

        # Clean stale entries
        active_names = {r.name for r in replicas}
        self._current_weights = {
            k: v for k, v in self._current_weights.items() if k in active_names
        }

        total_weight = sum(r.weight for r in replicas)

        # Add effective weight to current weight
        for r in replicas:
            self._current_weights[r.name] += r.weight

        # Select replica with highest current weight
        best = max(replicas, key=lambda r: self._current_weights.get(r.name, 0))

        # Reduce selected replica's current weight
        self._current_weights[best.name] -= total_weight

        return best

    def reset(self):
        self._current_weights.clear()


# =============================================================================
# 5. Least-Connections Strategy
# =============================================================================
class LeastConnectionsStrategy(RoutingStrategy):
    """Select the replica with the fewest active connections."""

    def name(self) -> str:
        return "Least-Conn"

    def select_replica(self, replicas: list[ReplicaInfo]) -> Optional[ReplicaInfo]:
        if not replicas:
            return None
        return min(replicas, key=lambda r: r.active_connections)


# =============================================================================
# Strategy registry
# =============================================================================
STRATEGIES: dict[str, type[RoutingStrategy]] = {
    "round_robin":     RoundRobinStrategy,
    "load_based":      LoadBasedStrategy,
    "latency_based":   LatencyBasedStrategy,
    "weighted_rr":     WeightedRoundRobinStrategy,
    "least_conn":      LeastConnectionsStrategy,
}


def get_strategy(name: str) -> RoutingStrategy:
    """Get a strategy instance by name."""
    cls = STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(STRATEGIES.keys())
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return cls()


def all_strategy_names() -> list[str]:
    """Return all registered strategy names."""
    return list(STRATEGIES.keys())
