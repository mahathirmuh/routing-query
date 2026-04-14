import json
import random
from pathlib import Path

STRATEGIES = ["round_robin", "load_based", "latency_based", "weighted_rr", "least_conn"]
COMPLEXITIES = ["simple", "medium", "complex"]
WORKLOADS = ["read_heavy", "balanced"]

Path("results").mkdir(exist_ok=True)

for strat in STRATEGIES:
    for comp in COMPLEXITIES:
        for work in WORKLOADS:
            for rep in range(1, 6):
                key = f"{strat}__{comp}__{work}__rep{rep}"
                
                # Biasing mock data slightly to show strategy differences
                base_lat = 10 if comp=="simple" else 30 if comp=="medium" else 80
                if strat == "round_robin": lat = base_lat * random.uniform(1.2, 1.5)
                elif strat == "load_based": lat = base_lat * random.uniform(1.0, 1.2)
                elif strat == "latency_based": lat = base_lat * random.uniform(0.9, 1.1)
                elif strat == "weighted_rr": lat = base_lat * random.uniform(1.1, 1.3)
                else: lat = base_lat * random.uniform(1.0, 1.2)
                
                r1 = random.randint(300, 500)
                r2 = random.randint(200, 400)
                r3 = random.randint(100, 300)
                
                if strat == "weighted_rr":
                    r1 = 400; r2 = 200; r3 = 100
                elif strat == "round_robin":
                    r1 = 300; r2 = 300; r3 = 300
                
                data = {
                    "read_avg_ms": lat,
                    "read_p95_ms": lat * 1.5,
                    "throughput_qps": 20000 / lat,
                    "load_cv": random.uniform(0.1, 0.8),
                    "avg_cpu_pct": random.uniform(2, 8),
                    "router_overhead_ms": random.uniform(0.001, 0.01),
                    "staleness_pct": 0,
                    "replica_query_counts": {"replica1": r1, "replica2": r2, "replica3": r3, "primary": 100},
                    "total_queries": r1+r2+r3+100,
                    "total_reads": r1+r2+r3,
                    "total_writes": 100,
                    "duration_s": 30,
                    "config": {
                        "strategy": strat, "complexity": comp, "workload": work, "seed": rep*100
                    }
                }
                with open(f"results/mock_{key}.json", "w") as f:
                    json.dump(data, f)
                    
print("Mock data generated.")
