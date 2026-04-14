# 📋 Analisis Tugas: TOPIK 2C — Optimasi Query Routing pada Arsitektur Read Replica PostgreSQL

**Mata Kuliah:** Komputasi Berbasis Jaringan — S2 Tesis  
**Area:** Database  
**Tipe:** Detail Mini Project

---

## 1. Deskripsi Proyek

Proyek ini bertujuan untuk **membandingkan 5 strategi query routing** pada arsitektur PostgreSQL dengan **1 primary + 3 read replica heterogen**:

| # | Strategi | Deskripsi |
|---|----------|-----------|
| 1 | **Round-Robin** | Distribusi query secara bergiliran |
| 2 | **Load-Based** | Routing berdasarkan beban (load) server |
| 3 | **Latency-Based** | Routing berdasarkan latensi terendah |
| 4 | **Weighted Round-Robin** | Round-robin dengan bobot berbeda per replica |
| 5 | **Least-Connections** | Routing ke replica dengan koneksi paling sedikit |

Evaluasi dilakukan pada variasi **query complexity** dan **read/write ratio**.

---

## 2. Infrastruktur yang Diperlukan

- **PostgreSQL 16** di Docker: 1 primary + 3 replica (async)
- **Heterogeneous resources**: 2 / 1 / 0.5 CPU
- **Total RAM**: ~1.5 GB
- **Data**: 500K rows
- **Custom Query Router Proxy**: Python (~200 LOC), 5 strategi pluggable
  - Health check: 5 detik
  - EMA (Exponential Moving Average): 0.3

---

## 3. Timeline / Langkah

| Pekan | Kegiatan |
|-------|----------|
| **Pekan 1** | Setup PG cluster + replication + data |
| **Pekan 2** | Implementasi Router + 5 strategies |
| **Pekan 3** | Integrasi keseluruhan |
| **Pekan 4** | Eksekusi benchmark + report |

---

## 4. Skenario Uji Coba

### 4.1 Variabel Tetap (Fixed Variables)
- PG 16.x, 3 replica heterogen
- 500K rows, async replication
- Pool: 20 connections
- Health check: 5 detik
- EMA: 0.3
- 50 concurrent clients
- Seed tetap (reproducible)
- Warm-up: 1000 queries

### 4.2 Variabel Manipulasi (Independent Variables)

| Variabel | Level |
|----------|-------|
| **Routing Strategy** | Round-Robin, Load-Based, Latency-Based, Weighted-RR, Least-Conn |
| **Query Complexity** | Simple (PK lookup), Medium (JOIN 2 tabel), Complex (JOIN 3 + aggregasi) |
| **Read/Write Ratio** | Read-Heavy (95:5), Balanced (70:30) |

> [!IMPORTANT]
> **Total kombinasi eksperimen:**  
> 5 strategi × 3 complexity × 2 ratio = **30 kombinasi**  
> 5 repetisi × 10 menit per run = **150 run** → ~25 jam (3 hari)  
> **Prioritas:** Read-Heavy = 15 × 5 = 75 run (~12.5 jam)

### 4.3 Variabel Respon (Dependent Variables / Metrics)

| Variabel | Satuan | Cara Pengukuran |
|----------|--------|-----------------|
| Read Avg Latency | ms | Rata-rata read query |
| Read P95 Latency | ms | Persentil ke-95 read |
| Overall Throughput | qps | Query berhasil per detik |
| Load Distribution CV | float | CV query count across replicas |
| Per-Replica CPU | % | Rata-rata CPU per replica |
| Staleness Rate | % | Read yang return stale data |
| Router Overhead | ms | Tambahan latency routing |

---

## 4.4 Template Pengumpulan Data

Terdapat **6 tabel data** yang harus diisi (Tabel 4.4a – 4.4f):

| Tabel | Read/Write Ratio | Query Complexity |
|-------|-----------------|------------------|
| **4.4a** | Read-Heavy (95:5) | Simple (PK lookup) |
| **4.4b** | Read-Heavy (95:5) | Medium (JOIN 2 tabel) |
| **4.4c** | Read-Heavy (95:5) | Complex (JOIN 3 + aggregasi) |
| **4.4d** | Balanced (70:30) | Simple |
| **4.4e** | Balanced (70:30) | Medium |
| **4.4f** | Balanced (70:30) | Complex |

Setiap tabel berisi metrik berikut per strategi (5 kolom: RoundRobin, Load-Based, Latency-Based, Weighted-RR, Least-Conn):
- Read Avg (ms)
- Read P95 (ms)
- Throughput (qps)
- Load CV
- Staleness (%)
- Router Overhead (ms)

> [!NOTE]
> Tabel 4.4d dan 4.4e (Balanced, Simple & Medium) lebih ringkas — tidak menyertakan metrik Read P95 dan Router Overhead.

---

## 4.5 Uji Statistik + Visualisasi

| Analisis | Detail |
|----------|--------|
| **Kruskal-Wallis + Dunn's** | 5 strategi per kombinasi |
| **Two-way ANOVA** | strategy × complexity |
| **Gini coefficient** | Fairness distribusi query |
| **Radar chart** | Per strategi (5 dimensi) |
| **Stacked bar** | Per-replica query distribution |
| **Heatmap** | Latency — strategy (row) × complexity×ratio (col) |

---

## 🔑 Rangkuman Poin Kunci

1. **Proyek ini adalah benchmark perbandingan** 5 strategi query routing pada PostgreSQL read replica
2. **Infrastruktur berbasis Docker** dengan replica heterogen (resource berbeda-beda)
3. **Custom router proxy** dalam Python (~200 baris) yang harus mendukung ke-5 strategi secara pluggable
4. **30 kombinasi eksperimen** dengan 5 repetisi masing-masing
5. **7 metrik yang diukur**: latency (avg & P95), throughput, load distribution, CPU, staleness, router overhead
6. **Analisis statistik formal** menggunakan Kruskal-Wallis, ANOVA, dan Gini coefficient
7. **Visualisasi** mencakup radar chart, stacked bar, dan heatmap
8. **Timeline 4 minggu** dari setup hingga report final

> [!TIP]
> Proyek ini membutuhkan:
> - Penguasaan **Docker Compose** untuk orchestration PostgreSQL cluster
> - Pemahaman **PostgreSQL streaming replication** (async)
> - Kemampuan **Python networking** untuk custom proxy/router
> - **Benchmarking methodology** yang rigorous (seed tetap, warm-up, repetisi)
> - **Statistical analysis** (non-parametric & parametric tests)
