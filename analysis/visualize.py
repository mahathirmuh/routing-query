"""
visualize.py — Generate Visualizations for Benchmark Results

Creates required charts based on loaded benchmark data:
  1. Bar Plot: Latency comparison (Strategy vs Complexity vs Workload)
  2. Bar Plot: Throughput comparison
  3. Bar Plot: Fairness/Load CV
  4. Scatter/Bubble Plot: Latency vs Throughput trade-off
"""

import os
import logging
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Add project root to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.stats_analysis import load_data

logger = logging.getLogger(__name__)

# Styling configurations (Academic/Professional Look)
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "figure.figsize": (10, 6),
    "figure.dpi": 300,
    "savefig.bbox": "tight"
})

def plot_bar_comparisons(df: pd.DataFrame, out_dir: Path):
    """Plot comprehensive bar charts for Latency and Throughput."""
    metrics = {
        "read_avg_ms": "Average Read Latency (ms)",
        "throughput_qps": "Throughput (QPS)",
        "load_cv": "Load Distribution (CV - Lower is better)"
    }

    for metric, ylabel in metrics.items():
        # Latency needs a log scale sometimes for 'complex', but we'll try linear first
        # separated by Complexity and Workload
        g = sns.catplot(
            data=df, kind="bar",
            x="strategy", y=metric,
            hue="complexity", col="workload",
            errorbar=("ci", 95), capsize=.1,
            height=6, aspect=1.2,
            palette="Set2"
        )
        
        g.set_axis_labels("Routing Strategy", ylabel)
        g.set_titles("Workload: {col_name}")
        g.tick_params(axis='x', rotation=45)
        
        # Adjust layout
        g.figure.subplots_adjust(top=0.9)
        g.figure.suptitle(f"{ylabel} by Strategy, Complexity, and Workload")
        
        # Save
        filename = out_dir / f"bar_{metric}.png"
        g.savefig(filename)
        logger.info(f"Saved {filename}")
        plt.close(g.figure)

def plot_latency_throughput_tradeoff(df: pd.DataFrame, out_dir: Path):
    """Scatter plot: X=Throughput, Y=Latency (Ideal is bottom-right)."""
    
    for workload in df["workload"].unique():
        subset = df[df["workload"] == workload]
        
        plt.figure(figsize=(10, 7))
        # Use bubble size for CV (smaller is better, so maybe inverse CV)
        
        sns.scatterplot(
            data=subset,
            x="throughput_qps",
            y="read_avg_ms",
            hue="strategy",
            style="complexity",
            s=150, # Marker size
            alpha=0.7,
            palette="colorblind"
        )
        
        plt.title(f"Latency vs Throughput Trade-off ({workload})")
        plt.xlabel("Throughput (QPS) → Higher is Better")
        plt.ylabel("Read Avg Latency (ms) → Lower is Better")
        
        # Optionally log-scale if complex latency is 100x higher
        # plt.yscale("log")
        
        # Put legend outside
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        
        filename = out_dir / f"scatter_tradeoff_{workload}.png"
        plt.savefig(filename)
        logger.info(f"Saved {filename}")
        plt.close()

def plot_load_distribution(df: pd.DataFrame, out_dir: Path):
    """Generate stacked horizontal bar chart showing distribution across replicas."""
    # We want a single plot per workload and complexity
    # X = percentage, Y = Strategy
    
    # We need to aggregate the counts
    agg = df.groupby(["workload", "complexity", "strategy"])[["rep1_cnt", "rep2_cnt", "rep3_cnt"]].mean().reset_index()
    
    for w_c, subset in agg.groupby(["workload", "complexity"]):
        workload, complexity = w_c
        
        # Normalize to percentages
        subset["total"] = subset["rep1_cnt"] + subset["rep2_cnt"] + subset["rep3_cnt"]
        subset["Rep1 (%)"] = subset["rep1_cnt"] / subset["total"] * 100
        subset["Rep2 (%)"] = subset["rep2_cnt"] / subset["total"] * 100
        subset["Rep3 (%)"] = subset["rep3_cnt"] / subset["total"] * 100
        
        plot_df = subset.set_index("strategy")[["Rep1 (%)", "Rep2 (%)", "Rep3 (%)"]]
        
        # Plot stacked bar
        ax = plot_df.plot(kind="barh", stacked=True, figsize=(8, 5), color=["#1f77b4", "#ff7f0e", "#2ca02c"])
        
        # Draw vertical lines for target capacity representation (4:2:1 ratio -> ~57%, 29%, 14%)
        ax.axvline(57.1, color='red', linestyle='--', alpha=0.5, label='Target R1 (57%)')
        ax.axvline(57.1 + 28.6, color='purple', linestyle='--', alpha=0.5, label='Target R2 (+29%)')
        
        plt.title(f"Load Distribution Across Replicas\n({workload} | {complexity})")
        plt.xlabel("Percentage of Read Queries")
        plt.ylabel("Strategy")
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        
        filename = out_dir / f"dist_{workload}_{complexity}.png"
        plt.savefig(filename)
        logger.info(f"Saved {filename}")
        plt.close()

def generate_all_plots(results_dir: str = "results", out_dir: str = "analysis_output"):
    """Generate all visualizations from benchmark data."""
    p_out = Path(out_dir)
    p_out.mkdir(exist_ok=True)
    
    df = load_data(results_dir)
    if df.empty:
        logger.error("No data to visualize.")
        return
        
    logger.info("Generating Bar Comparisons...")
    plot_bar_comparisons(df, p_out)
    
    logger.info("Generating Latency/Throughput Trade-off...")
    plot_latency_throughput_tradeoff(df, p_out)
    
    logger.info("Generating Load Distribution...")
    plot_load_distribution(df, p_out)
    
    logger.info("All visualizations generated.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_all_plots()
