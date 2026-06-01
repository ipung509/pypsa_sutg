# pypsa_sutg
<!--
SPDX-FileCopyrightText: PyPSA Contributors

SPDX-License-Identifier: MIT
-->

<picture align="center">
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/PyPSA/PyPSA/refs/heads/master/docs/assets/logo/logo-primary-dark.svg">
  <img alt="PyPSA Banner" src="https://raw.githubusercontent.com/PyPSA/PyPSA/refs/heads/master/docs/assets/logo/logo-primary-light.svg">
</picture>

# PyPSA SUTG

Model simulasi sistem tenaga listrik menggunakan PyPSA untuk analisis operasi sistem, aliran daya (*power flow*), dan evaluasi pembangkitan pada Sistem Sulawesi Utara dan Gorontalo (SUTG).

---

## Struktur Folder

```text
pypsa_sutg/
│
├── data/
│   ├── buses.csv
│   ├── carriers.csv
│   ├── generators.csv
│   ├── generators-p_max_pu.csv
│   ├── generators-p_min_pu.csv
│   ├── lines.csv
│   ├── loads.csv
│   ├── loads-p_set.csv
│   ├── snapshots.csv
│   └── transformers.csv
│
├── ROH_v1.py
└── README.md
```

---

## Persyaratan Sistem

* Python 3.10 atau lebih baru
* PyPSA
* Pandas
* NumPy
* Matplotlib (opsional untuk visualisasi)
* HiGHS Solver atau Gurobi Solver (opsional)

---

## Instalasi

### 1. Clone Repository

```bash
git clone https://github.com/ipung509/pypsa_sutg.git
cd pypsa_sutg
```

### 2. Buat Environment Python

Menggunakan Conda:

```bash
conda create -n pypsa_sutg python=3.11
conda activate pypsa_sutg
```

### 3. Install PyPSA dan Library Pendukung

```bash
pip install pypsa pandas numpy matplotlib
```

### 4. Install Solver HiGHS (Direkomendasikan)

```bash
conda install -c conda-forge highspy
```

### 5. Install Gurobi (Opsional)

Pastikan Gurobi telah terinstal dan lisensi aktif.

```bash
pip install gurobipy
```

---

## Eksekusi Lokal Menggunakan Anaconda dan Spyder

### 1. Download Repository

Clone repository:

```bash
git clone https://github.com/ipung509/pypsa_sutg.git
```

atau pilih:

```text
Code → Download ZIP
```

kemudian ekstrak ke folder lokal.

Contoh:

```text
C:\Users\Username\Documents\pypsa_sutg
```

---

### 2. Download Folder Data

Pastikan seluruh file pada folder `data` telah tersedia.

```text
data/
├── buses.csv
├── carriers.csv
├── generators.csv
├── generators-p_max_pu.csv
├── generators-p_min_pu.csv
├── lines.csv
├── loads.csv
├── loads-p_set.csv
├── snapshots.csv
└── transformers.csv
```

> **Penting:** Simulasi tidak dapat dijalankan apabila folder `data` atau salah satu file CSV tidak tersedia karena seluruh parameter sistem dibaca dari file tersebut.

---

### 3. Aktivasi Environment

Buka **Anaconda Prompt**:

```bash
conda activate pypsa_sutg
```

Verifikasi instalasi package:

```bash
pip list
```

---

### 4. Install dan Jalankan Spyder

Jika Spyder belum tersedia:

```bash
conda install spyder
```

Jalankan Spyder:

```bash
spyder
```

---

### 5. Membuka Project

Pada Spyder:

1. Pilih **File → Open**
2. Buka file:

```text
ROH_v1.py
```

3. Atur **Working Directory** ke folder repository:

```text
C:\Users\Username\Documents\pypsa_sutg
```

Struktur folder harus seperti berikut:

```text
pypsa_sutg/
│
├── data/
│   └── seluruh file CSV
│
└── ROH_v1.py
```

---

### 6. Menjalankan Simulasi

Tekan tombol **Run File (F5)** atau jalankan:

```python
runfile('ROH_v1.py')
```

Script akan membaca seluruh data pada folder `data` dan menjalankan simulasi optimasi sistem tenaga menggunakan PyPSA.

---

### 7. Verifikasi Hasil

Apabila simulasi berhasil, Console Spyder akan menampilkan:

* Status optimasi
* Objective function
* Dispatch pembangkit
* Aliran daya sistem
* Loading saluran transmisi
* Loading transformator
* Informasi reserve margin
* Renewable energy curtailment (jika dimodelkan)

---

## Format Data Input

### buses.csv

Berisi data bus/substation.

Contoh:

| name   | v_nom |
| ------ | ----- |
| MANADO | 150   |

### generators.csv

Berisi data unit pembangkit.

Contoh:

| name          | bus    | carrier | p_nom |
| ------------- | ------ | ------- | ----- |
| PLTA_Tanggari | MANADO | hydro   | 18    |

### loads.csv

Berisi data beban sistem.

### lines.csv

Berisi data saluran transmisi.

### transformers.csv

Berisi data transformator.

### snapshots.csv

Berisi horizon atau periode simulasi.

### generators-p_max_pu.csv

Profil maksimum output pembangkit.

### generators-p_min_pu.csv

Profil minimum output pembangkit.

### loads-p_set.csv

Profil beban sistem.

---

## Menjalankan Simulasi Melalui Command Line

Aktifkan environment:

```bash
conda activate pypsa_sutg
```

Jalankan model:

```bash
python ROH_v1.py
```

---

## Output Simulasi

Output yang dihasilkan dapat berupa:

* Dispatch pembangkit
* Loading saluran transmisi
* Loading transformator
* Aliran daya tiap bus
* Biaya operasi sistem
* Renewable Energy Curtailment (REC)
* Reserve Margin
* Grafik hasil simulasi
* Ringkasan operasi sistem

---

## Pengembangan Model

### Menambahkan Pembangkit Baru

1. Tambahkan data pada `generators.csv`
2. Tambahkan profil operasi pada:

   * `generators-p_max_pu.csv`
   * `generators-p_min_pu.csv`
3. Jalankan ulang simulasi

### Menambahkan Beban Baru

1. Tambahkan data pada `loads.csv`
2. Tambahkan profil beban pada `loads-p_set.csv`

### Menambahkan Saluran Transmisi Baru

1. Tambahkan data pada `lines.csv`
2. Pastikan bus asal dan tujuan telah terdaftar pada `buses.csv`

---

## Solver

Model dapat dijalankan menggunakan:

* HiGHS (Open Source)
* Gurobi (Commercial)
* GLPK
* CBC

### Contoh Penggunaan Gurobi

```python
network.optimize(solver_name="gurobi")
```

### Contoh Penggunaan HiGHS

```python
network.optimize(solver_name="highs")
```

---

## Troubleshooting

### Error: No module named pypsa

Install PyPSA:

```bash
pip install pypsa
```

### Error: Solver not found

Install solver:

```bash
conda install -c conda-forge highspy
```

### Error: FileNotFoundError

Periksa:

* Folder `data` tersedia
* Nama file CSV sesuai
* Working Directory Spyder sudah benar
* Lokasi `ROH_v1.py` dan folder `data` sesuai struktur repository

### Power Flow Tidak Konvergen

Periksa:

* Data saluran transmisi
* Parameter transformator
* Keseimbangan daya sistem
* Slack Bus
* Kapasitas pembangkit mencukupi kebutuhan beban

---

## Author

**Ipung Rahmad**
PT PLN (Persero)

---

## License

Repository ini digunakan untuk keperluan penelitian, pengembangan model sistem tenaga listrik, dan pembelajaran PyPSA.
