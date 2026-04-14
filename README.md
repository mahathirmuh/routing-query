# 🚀 Optimasi Query Routing pada Arsitektur Read Replica PostgreSQL

> **TOPIK 2C** — Mini Project Mata Kuliah Komputasi Berbasis Jaringan (KBJ)  
> Membandingkan 5 strategi query routing pada arsitektur PostgreSQL dengan 1 primary + 3 read replica heterogen.

---

## 📋 Daftar Isi

- [Deskripsi Proyek](#-deskripsi-proyek)
- [Arsitektur Sistem](#-arsitektur-sistem)
- [Strategi Routing](#-strategi-routing)
- [Struktur Direktori](#-struktur-direktori)
- [Prasyarat](#-prasyarat)
- [Instalasi & Setup](#-instalasi--setup)
- [Menjalankan Benchmark](#-menjalankan-benchmark)
- [Analisis & Visualisasi](#-analisis--visualisasi)
- [Skenario Eksperimen](#-skenario-eksperimen)
- [Metrik yang Diukur](#-metrik-yang-diukur)
- [Uji Statistik](#-uji-statistik)
- [Teknologi](#-teknologi)

---

## 📖 Deskripsi Proyek

Proyek ini mengimplementasikan **Custom Query Router Proxy** dalam Python yang secara otomatis mengarahkan query ke server PostgreSQL yang tepat:

- **Write queries** (INSERT, UPDATE, DELETE) → selalu dikirim ke **Primary**
- **Read queries** (SELECT) → diarahkan ke salah satu **Replica** berdasarkan strategi routing yang dipilih

Tujuan utama adalah membandingkan performa 5 strategi routing yang berbeda melalui benchmark yang rigorous, dengan variasi kompleksitas query dan rasio read/write.

---

## 🏗 Arsitektur Sistem

```
                    ┌──────────────────────────────────┐
                    │        Query Router Proxy         │
                    │   (Python asyncio + asyncpg)      │
                    │                                    │
                    │  ┌────────────┐ ┌──────────────┐  │
  Client ──────────►│  │  Query     │ │  Routing     │  │
  (50 concurrent)   │  │ Classifier │ │  Strategy    │  │
                    │  │ R/W split  │ │  (pluggable) │  │
                    │  └─────┬──────┘ └──────┬───────┘  │
                    │        │               │           │
                    │  ┌─────┴───────────────┴───────┐  │
                    │  │     Health Checker           │  │
                    │  │     (EMA α=0.3, 5s interval) │  │
                    │  └─────────────────────────────┘  │
                    └────────────┬───────────────────────┘
                                 │
              ┌──────────────────┼──────────────────────┐
              │                  │                       │
              ▼                  ▼                       ▼
    ┌─────────────────┐ ┌───────────────┐ ┌──────────────────┐
    │  pg_primary      │ │  pg_replica1  │ │  pg_replica2     │
    │  (READ + WRITE)  │ │  (READ only)  │ │  (READ only)     │
    │  2 CPU, 512 MB   │ │  2 CPU, 384MB │ │  1 CPU, 384MB    │
    │  Port: 5439      │ │  Port: 5440   │ │  Port: 5441      │
    └─────────────────┘ └───────────────┘ └──────────────────┘
                                                     │
                                          ┌──────────────────┐
                                          │  pg_replica3     │
                                          │  (READ only)     │
                                          │  0.5 CPU, 384MB  │
                                          │  Port: 5442      │
                                          └──────────────────┘
```

**Replikasi**: Asynchronous Streaming Replication (PostgreSQL 16)  
**Data**: 500.000 rows (tabel `orders`, `customers`, `products`)  
**Connection Pool**: 20 koneksi per backend

---

## 🔀 Strategi Routing

| # | Strategi | Key | Deskripsi |
|---|----------|-----|-----------|
| 1 | **Round-Robin** | `round_robin` | Distribusi query secara bergiliran ke semua replica yang sehat |
| 2 | **Load-Based** | `load_based` | Routing ke replica dengan penggunaan CPU terendah |
| 3 | **Latency-Based** | `latency_based` | Routing ke replica dengan latensi EMA terendah |
| 4 | **Weighted Round-Robin** | `weighted_rr` | Round-robin berbobot proporsional terhadap kapasitas CPU (4:2:1) |
| 5 | **Least-Connections** | `least_conn` | Routing ke replica dengan koneksi aktif paling sedikit |

Semua strategi diimplementasikan secara **pluggable** menggunakan Abstract Base Class dan strategy registry pattern.

---

## 📁 Struktur Direktori

```
KBJFP/
├── docker-compose.yml          # Konfigurasi cluster PostgreSQL (1 primary + 3 replica)
├── requirements.txt            # Dependency Python
├── test_router.py              # Smoke test untuk query router
├── verify_cluster.py           # Verifikasi koneksi cluster
│
├── docker/                     # Konfigurasi Docker
│   ├── primary/                # Setup primary (postgresql.conf, pg_hba.conf, init.sql)
│   └── replica/                # Setup replica (entrypoint.sh)
│
├── router/                     # 🔧 Core Query Router Module
│   ├── __init__.py
│   ├── query_router.py         # Main router proxy — klasifikasi & routing query
│   ├── strategies.py           # 5 strategi routing (pluggable)
│   ├── health_checker.py       # Background health check (EMA latency, CPU, koneksi)
│   └── metrics.py              # Kolektor metrik dan agregasi statistik
│
├── benchmark/                  # 📊 Benchmark Engine
│   ├── __init__.py
│   ├── queries.py              # Template query (simple, medium, complex)
│   ├── workload.py             # Profil workload (read-heavy 95:5, balanced 70:30)
│   ├── runner.py               # Eksekutor benchmark (50 concurrent clients, warm-up)
│   └── run_all.py              # Orkestrator: iterasi semua kombinasi eksperimen
│
├── analysis/                   # 📈 Analisis & Visualisasi
│   ├── __init__.py
│   ├── stats_analysis.py       # Kruskal-Wallis, Dunn's post-hoc, Two-way ANOVA, Gini
│   ├── visualize.py            # Bar chart, scatter plot, load distribution
│   ├── report_tables.py        # Tabel ringkasan untuk laporan
│   └── generate_mock_data.py   # Generator data mock untuk testing
│
├── results/                    # 📂 Output Benchmark (JSON per run + summary.csv)
│   ├── *.json                  # Hasil per kombinasi (strategy__complexity__workload__repN)
│   └── summary.csv             # Ringkasan semua run
│
└── analysis_output/            # 📉 Output Analisis
    ├── anova.txt               # Hasil Two-way ANOVA
    ├── kruskal_dunn.txt         # Hasil Kruskal-Wallis + Dunn's post-hoc
    ├── gini_fairness.csv       # Koefisien Gini per strategi
    ├── bar_*.png               # Bar chart perbandingan metrik
    ├── scatter_tradeoff_*.png  # Scatter plot latency vs throughput
    ├── dist_*.png              # Distribusi load per replica
    ├── heatmap_latency.png     # Heatmap latensi
    ├── radar_chart.png         # Radar chart multidimensi
    └── box_plots.png           # Box plot perbandingan
```

---

## ⚙ Prasyarat

- **Docker** & **Docker Compose** (untuk menjalankan cluster PostgreSQL)
- **Python** 3.11+
- ~2 GB RAM tersedia (untuk 4 container PostgreSQL)

---

## 🛠 Instalasi & Setup

### 1. Clone Repository

```bash
git clone https://github.com/mahathirmuh/routing-query.git
cd routing-query
```

### 2. Install Dependency Python

```bash
pip install -r requirements.txt
```

**Dependency utama:**
| Package | Fungsi |
|---------|--------|
| `asyncpg` | Async PostgreSQL driver |
| `psycopg2-binary` | Sync PostgreSQL driver (utilities) |
| `numpy`, `scipy`, `pandas` | Komputasi data & analisis |
| `matplotlib`, `seaborn` | Visualisasi |
| `scikit-posthocs` | Dunn's post-hoc test |
| `tqdm` | Progress bar |

### 3. Setup Cluster PostgreSQL

```bash
# Jalankan cluster (1 primary + 3 replica)
docker compose up -d

# Verifikasi semua container berjalan
docker compose ps

# Verifikasi koneksi & replikasi
python verify_cluster.py
```

### 4. Smoke Test Router

```bash
# Test semua 5 strategi routing
python test_router.py
```

Output yang diharapkan:
```
  [ALL PASS] All 5 strategies working correctly!
```

---

## 🏃 Menjalankan Benchmark

### Full Benchmark (30 kombinasi × 5 repetisi = 150 run)

```bash
# Full benchmark (~25 jam)
python -m benchmark.run_all

# Custom parameter
python -m benchmark.run_all --duration 300 --reps 3 --concurrency 30
```

### Quick Smoke Test

```bash
# Mode cepat: 60s per run, 1 repetisi, 10 concurrency
python -m benchmark.run_all --quick
```

### Benchmark Selektif

```bash
# Hanya strategi tertentu
python -m benchmark.run_all --strategies round_robin load_based

# Hanya workload read_heavy
python -m benchmark.run_all --workloads read_heavy

# Hanya kompleksitas simple
python -m benchmark.run_all --complexities simple

# Re-run semua (tanpa skip yang sudah selesai)
python -m benchmark.run_all --no-resume
```

### Parameter CLI

| Parameter | Default | Deskripsi |
|-----------|---------|-----------|
| `--duration` | 600 (10 menit) | Durasi per run dalam detik |
| `--concurrency` | 50 | Jumlah concurrent client |
| `--warmup` | 1000 | Jumlah query warm-up |
| `--reps` | 5 | Jumlah repetisi per kombinasi |
| `--strategies` | semua | Strategi yang diuji |
| `--complexities` | semua | Level kompleksitas query |
| `--workloads` | semua | Profil workload |
| `--no-resume` | false | Re-run semua (jangan skip yang selesai) |
| `--quick` | false | Mode cepat (60s, 1 rep, 10 concurrency) |

---

## 📊 Analisis & Visualisasi

### Jalankan Analisis Statistik

```bash
python -m analysis.stats_analysis
```

Output: `analysis_output/kruskal_dunn.txt`, `anova.txt`, `gini_fairness.csv`

### Generate Visualisasi

```bash
python -m analysis.visualize
```

Output: Chart PNG di folder `analysis_output/`

### Generate Tabel Laporan

```bash
python -m analysis.report_tables
```

---

## 🧪 Skenario Eksperimen

### Variabel Independen

| Variabel | Level |
|----------|-------|
| **Routing Strategy** | Round-Robin, Load-Based, Latency-Based, Weighted-RR, Least-Conn |
| **Query Complexity** | Simple (PK lookup), Medium (JOIN 2 tabel), Complex (JOIN 3 + aggregasi) |
| **Read/Write Ratio** | Read-Heavy (95:5), Balanced (70:30) |

### Variabel Tetap

| Parameter | Nilai |
|-----------|-------|
| PostgreSQL Version | 16.x |
| Jumlah Replica | 3 (heterogen: 2/1/0.5 CPU) |
| Dataset | 500.000 rows |
| Replikasi | Asynchronous Streaming |
| Connection Pool | 20 koneksi per backend |
| Health Check Interval | 5 detik |
| EMA Alpha | 0.3 |
| Concurrent Clients | 50 |
| Random Seed | Fixed (reproducible) |
| Warm-up | 1.000 queries |

### Total Kombinasi

```
5 strategi × 3 complexity × 2 ratio = 30 kombinasi
30 kombinasi × 5 repetisi = 150 total run
```

---

## 📐 Metrik yang Diukur

| # | Metrik | Satuan | Deskripsi |
|---|--------|--------|-----------|
| 1 | **Read Avg Latency** | ms | Rata-rata latensi read query |
| 2 | **Read P95 Latency** | ms | Persentil ke-95 latensi read |
| 3 | **Overall Throughput** | qps | Query berhasil per detik |
| 4 | **Load Distribution CV** | float | Coefficient of Variation distribusi query antar replica |
| 5 | **Per-Replica CPU** | % | Rata-rata penggunaan CPU per replica |
| 6 | **Staleness Rate** | % | Persentase read yang mendapat data basi |
| 7 | **Router Overhead** | ms | Waktu tambahan untuk keputusan routing |

---

## 📈 Uji Statistik

| Analisis | Fungsi |
|----------|--------|
| **Kruskal-Wallis H-test** | Perbandingan non-parametrik 5 strategi per kombinasi |
| **Dunn's Post-Hoc** | Identifikasi pasangan strategi yang berbeda signifikan (α = 0.05) |
| **Two-way ANOVA** | Interaksi Strategy × Complexity (parametrik) |
| **Gini Coefficient** | Fairness distribusi query ke replica |

### Visualisasi yang Dihasilkan

| Jenis | Deskripsi |
|-------|-----------|
| **Bar Chart** | Perbandingan latency, throughput, dan load CV |
| **Scatter Plot** | Trade-off latency vs throughput (ideal: kanan bawah) |
| **Stacked Bar** | Distribusi query per replica per strategi |
| **Heatmap** | Latensi — strategy (baris) × complexity×ratio (kolom) |
| **Radar Chart** | Perbandingan multidimensi per strategi |
| **Box Plot** | Distribusi metrik antar repetisi |

---

## 🧰 Teknologi

| Komponen | Teknologi |
|----------|-----------|
| **Database** | PostgreSQL 16 |
| **Containerization** | Docker & Docker Compose |
| **Bahasa** | Python 3.11+ |
| **Async I/O** | asyncio + asyncpg |
| **Data Analysis** | pandas, numpy, scipy |
| **Visualization** | matplotlib, seaborn |
| **Statistical Tests** | scipy.stats, scikit-posthocs, statsmodels |

---

## Lisensi

Proyek ini dikembangkan untuk keperluan akademis pada mata kuliah **Komputasi Berbasis Jaringan — S2 Tesis**.
