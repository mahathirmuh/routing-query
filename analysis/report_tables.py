"""
report_tables.py — Generate Summary Tables for Final Report

Aggregates raw JSON data into clean CSV tables suitable for insertion
into the final academic report (Means and Std Devs).
"""

import os
import logging
import pandas as pd
from pathlib import Path

# Add project root to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.stats_analysis import load_data

logger = logging.getLogger(__name__)

def generate_summary_tables(results_dir: str = "results", out_dir: str = "analysis_output"):
    p_out = Path(out_dir)
    p_out.mkdir(exist_ok=True)
    
    df = load_data(results_dir)
    if df.empty:
        logger.error("No data to format.")
        return
        
    # Group by Workload, Complexity, Strategy
    grouped = df.groupby(["workload", "complexity", "strategy"])
    
    # Calculate Mean and Std
    mean_df = grouped.mean(numeric_only=True)
    std_df = grouped.std(numeric_only=True)
    
    # We want formatted strings: "Mean ± Std"
    metrics = ["read_avg_ms", "throughput_qps", "load_cv", "avg_cpu_pct"]
    
    summary_data = {}
    for metric in metrics:
        combo_df = pd.DataFrame()
        combo_df[metric] = mean_df[metric].round(2).astype(str) + " ± " + std_df[metric].round(2).astype(str)
        summary_data[metric] = combo_df
        
    # Combine into one large table
    final_table = pd.concat(summary_data.values(), axis=1)
    
    # Reorder columns and rename for LaTeX/Word insertion
    final_table.columns = ["Latency (ms)", "Throughput (QPS)", "Load CV", "CPU (%)"]
    
    # Save to CSV
    csv_path = p_out / "report_summary_table.csv"
    final_table.to_csv(csv_path)
    logger.info(f"Summary table generated: {csv_path}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_summary_tables()
