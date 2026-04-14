"""
statistics.py — Statistical Analysis for Benchmark Results

Performs formal statistical tests on the benchmark results:
  - Kruskal-Wallis H-test + Dunn's post-hoc (non-parametric comparison of 5 strategies)
  - Two-way ANOVA (Parametric: Strategy × Complexity interaction)
  - Gini Coefficient (Fairness of query distribution)
"""

import os
import json
import numpy as np
import pandas as pd
import scipy.stats as stats
import scikit_posthocs as sp
import logging

from pathlib import Path

logger = logging.getLogger(__name__)

# Alpha level for significance
ALPHA = 0.05

def load_data(results_dir: str = "results") -> pd.DataFrame:
    """Load benchmark results from JSON files into a Pandas DataFrame."""
    p_dir = Path(results_dir)
    if not p_dir.exists():
        logger.error(f"Directory {results_dir} not found.")
        return pd.DataFrame()
    
    rows = []
    for json_file in p_dir.glob("*.json"):
        if json_file.name == "summary.json":
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            config = data.get("config", {})
            # Only include valid runs
            if "error" in data:
                continue
                
            row = {
                "strategy": config.get("strategy"),
                "complexity": config.get("complexity"),
                "workload": config.get("workload"),
                "rep": config.get("seed"), # Proxy for repetition
                "read_avg_ms": data.get("read_avg_ms"),
                "read_p95_ms": data.get("read_p95_ms"),
                "throughput_qps": data.get("throughput_qps"),
                "load_cv": data.get("load_cv"),
                "router_overhead_ms": data.get("router_overhead_ms"),
                "avg_cpu_pct": data.get("avg_cpu_pct"),
            }
            # Also extract replica query counts for Gini
            replica_counts = data.get("replica_query_counts", {})
            row["rep1_cnt"] = replica_counts.get("replica1", 0)
            row["rep2_cnt"] = replica_counts.get("replica2", 0)
            row["rep3_cnt"] = replica_counts.get("replica3", 0)
            row["primary_cnt"] = replica_counts.get("primary", 0)
            
            rows.append(row)
        except Exception as e:
            logger.warning(f"Error reading {json_file}: {e}")
            
    return pd.DataFrame(rows)

def gini_coefficient(x) -> float:
    """Calculate the Gini coefficient of a numpy array."""
    # based on bottom eq: http://www.statsdirect.com/help/content/image/stat0206_wmf.gif
    # from: http://www.statsdirect.com/help/default.htm#nonparametric_methods/gini.htm
    array = np.array(x, dtype=np.float64)
    # If all values are 0, distribution is perfectly equal (though empty)
    if np.amin(array) < 0:
        array -= np.amin(array) # Values cannot be negative
    array += 0.0000001 # Values cannot be 0
    array = np.sort(array) # Values must be sorted
    index = np.arange(1,array.shape[0]+1) # Index per array element
    n = array.shape[0]
    return ((np.sum((2 * index - n  - 1) * array)) / (n * np.sum(array)))

def analyze_kruskal_dunn(df: pd.DataFrame, metric: str = "read_avg_ms") -> str:
    """Perform Kruskal-Wallis and Dunn's post-hoc test on a metric."""
    report = [f"--- Kruskal-Wallis + Dunn's Test for {metric} ---"]
    
    for workload in df["workload"].unique():
        for complexity in df["complexity"].unique():
            subset = df[(df["workload"] == workload) & (df["complexity"] == complexity)]
            if subset.empty or len(subset["strategy"].unique()) < 2:
                continue
                
            report.append(f"\nCondition: {workload} | {complexity}")
            
            # Format data for kw
            groups = [group[metric].values for name, group in subset.groupby("strategy")]
            
            # 1. Kruskal-Wallis H-test
            h_stat, p_val = stats.kruskal(*groups)
            sig = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else "ns"
            report.append(f"Kruskal-Wallis: H={h_stat:.2f}, p={p_val:.4e} ({sig})")
            
            # 2. Dunn's Post-hoc (if significant)
            if p_val < ALPHA:
                report.append("Dunn's Post-hoc (p-values):")
                # Need to reshape for scikit-posthocs
                dunn_p = sp.posthoc_dunn(subset, val_col=metric, group_col='strategy', p_adjust='holm')
                report.append(dunn_p.round(4).to_string())
            else:
                report.append("No significant differences found.")
                
    return "\n".join(report)

def analyze_two_way_anova(df: pd.DataFrame, metric: str = "read_avg_ms") -> str:
    """Perform Two-way ANOVA (Strategy x Complexity) via OLS."""
    import statsmodels.api as sm
    from statsmodels.formula.api import ols
    
    report = [f"--- Two-way ANOVA ({metric}: Strategy x Complexity) ---"]
    
    for workload in df["workload"].unique():
        subset = df[df["workload"] == workload]
        if subset.empty or len(subset["strategy"].unique()) < 2:
            continue
            
        report.append(f"\nWorkload: {workload}")
        
        try:
            # Fit OLS model
            model = ols(f'{metric} ~ C(strategy) + C(complexity) + C(strategy):C(complexity)', data=subset).fit()
            # Perform ANOVA
            anova_table = sm.stats.anova_lm(model, typ=2)
            
            report.append("ANOVA Table:")
            report.append(anova_table.to_string())
        except Exception as e:
            report.append(f"ANOVA Failed: Ensure statsmodels is installed and enough reps exist. Error: {e}")

    return "\n".join(report)

def calculate_fairness(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Gini coefficient (fairness) of query distribution per run."""
    
    fairness_records = []
    for _, row in df.iterrows():
        # Extracted counts for the 3 replicas
        counts = [row["rep1_cnt"], row["rep2_cnt"], row["rep3_cnt"]]
        gini = gini_coefficient(counts)
        fairness_records.append({
            "strategy": row["strategy"],
            "complexity": row["complexity"],
            "workload": row["workload"],
            "gini": gini
        })
        
    f_df = pd.DataFrame(fairness_records)
    # Aggregate
    agg = f_df.groupby(["workload", "complexity", "strategy"])["gini"].mean().reset_index()
    return agg

def run_all_analysis(results_dir: str = "results", out_dir: str = "analysis_output"):
    """Run all statistical analyses and save reports."""
    Path(out_dir).mkdir(exist_ok=True)
    
    df = load_data(results_dir)
    if df.empty:
        logger.error("No data to analyze. Run benchmarks first.")
        return
        
    num_runs = len(df)
    expected_runs = 30 * 5 # 30 combos * 5 reps
    logger.info(f"Loaded {num_runs} runs (Expected: {expected_runs})")
    
    # 1. Kruskal-Wallis on Latency and Throughput
    with open(f"{out_dir}/kruskal_dunn.txt", "w") as f:
        f.write(analyze_kruskal_dunn(df, "read_avg_ms"))
        f.write("\n\n")
        f.write(analyze_kruskal_dunn(df, "throughput_qps"))
        
    logger.info("Kruskal-Wallis analysis complete.")
    
    # 2. ANOVA
    try:
        import statsmodels
        with open(f"{out_dir}/anova.txt", "w") as f:
            f.write(analyze_two_way_anova(df, "read_avg_ms"))
        logger.info("Two-way ANOVA complete.")
    except ImportError:
        logger.warning("statsmodels not installed; skipping ANOVA. (pip install statsmodels)")
        
    # 3. Gini Fairness
    gini_df = calculate_fairness(df)
    gini_df.to_csv(f"{out_dir}/gini_fairness.csv", index=False)
    logger.info("Gini fairness analysis complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_analysis()
