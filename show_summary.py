import csv

rows = list(csv.DictReader(open('results/summary.csv')))
print(f"{'Strategy':15s} | {'QPS':>8s} | {'ReadAvg':>10s} | {'ReadP95':>10s} | {'LoadCV':>7s} | {'Errors':>6s}")
print("-" * 70)
for r in rows:
    print(f"{r['strategy']:15s} | {float(r['throughput_qps']):8.1f} | {float(r['read_avg_ms']):8.2f}ms | {float(r['read_p95_ms']):8.2f}ms | {float(r['load_cv']):7.3f} | {r['errors']:>6s}")
