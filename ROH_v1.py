# -*- coding: utf-8 -*-
"""
PyPSA + Minimum Daily CF per Generator (LHD2/3/4) - COMPLETE & ROBUST + GEOMAP
- Menambahkan constraint CF harian minimum per generator
- Agregasi/plot dispatch per carrier
- Ekspor dispatch & CF harian
- Peta transfer (topologi) dan Peta transfer (geografis dengan lon/lat + basemap)

Kolom x/y pada n.buses diasumsikan:
    x = longitude (derajat)
    y = latitude  (derajat)
"""

import pypsa
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import xarray as xr
from pathlib import Path

# ========= 1) Path I/O =========
data_folder = Path(r"C:\Users\YOGA\Pypsa\test_data_2")  # ganti jika perlu
plot_png     = data_folder / "plot_dispatch.png"
dispatch_csv = data_folder / "dispatch_generators.csv"
cf_daily_csv = data_folder / "cf_harian_PLTP_LHD234.csv"

# ========= 2) Load network =========
n = pypsa.Network()
n.import_from_csv_folder(str(data_folder))

# ========= 3) Target CF harian per generator =========
targets_exact = {
    "011.2TP.LAHENDONG1": 0.55,
    "012.2TP.LAHENDONG2": 0.70,
    "013.2TP.LAHENDONG3": 0.70,
    "014.2TP.LAHENDONG4": 0.90,
    "015.3TP.LAHENDONG5": 0.91,
    "016.3TP.LAHENDONG6": 0.92,
    "007.3TU.SULUT3#1": 0.55,
    "008.3TU.SULUT3#2": 0.55,
}
CF_min_by_gen = pd.Series(0.0, index=n.generators.index)

# Map exact
for g, cf in targets_exact.items():
    if g in CF_min_by_gen.index:
        CF_min_by_gen.loc[g] = float(cf)

# Fallback substring (jika nama di CSV sedikit beda)
fallback_patterns = {
    "LAHENDONG1": 0.55,
    "LAHENDONG2": 0.70,
    "LAHENDONG3": 0.70,
    "LAHENDONG4": 0.90,
}
for pat, cf in fallback_patterns.items():
    hits = [idx for idx in n.generators.index if pat.lower() in idx.lower()]
    for h in hits:
        CF_min_by_gen.loc[h] = max(CF_min_by_gen.loc[h], float(cf))

print("Target CF harian yang diterapkan:")
print(CF_min_by_gen[CF_min_by_gen > 0].sort_index())
print()

# ========= 4) Constraint CF harian (robust + xarray fix) =========
def add_min_daily_cf_per_gen(n, snapshots):
    """
    Untuk setiap generator g dengan CF_min>0 dan setiap 'hari' D:
      sum_t p[g,t]*dt[t] >= CF_min[g] * p_nom[g] * sum_t dt[t]
    """
    m = n.model
    p = m.variables["Generator-p"]            # linopy Variable
    dt = n.snapshot_weightings["generators"]  # Series (jam per snapshot)

    # Deteksi dimensi via overlap label (handle dims seperti ['snapshot','name'])
    dims = list(p.dims)
    coords = {d: pd.Index(p.coords[d].values) for d in dims}
    gen_index  = pd.Index(n.generators.index)
    time_index = pd.Index(n.snapshots)

    gdim = max(dims, key=lambda d: gen_index.intersection(coords[d]).size)
    tdim = max(dims, key=lambda d: time_index.intersection(coords[d]).size)
    print(f"[CF] Using gdim='{gdim}', tdim='{tdim}'")

    gens_var  = coords[gdim]
    snaps_var = coords[tdim]

    # Grup 'harian'
    snaps_n = n.snapshots
    if isinstance(snaps_n, pd.DatetimeIndex) and snaps_n.normalize().nunique() > 1:
        day_index = snaps_n.normalize()
        day_groups = {d: snaps_n[day_index == d] for d in pd.Index(day_index.unique())}
    else:
        day_groups = {"DAY0": snaps_n}

    # Generator bertarget yang tersedia
    gens_with_target = CF_min_by_gen[CF_min_by_gen > 0].index
    gens_use = [g for g in gens_with_target if g in gens_var]
    missing  = [g for g in gens_with_target if g not in gens_var]
    if missing:
        print("Peringatan: target diabaikan utk generator tidak ada di variabel model:", missing)

    for g in gens_use:
        p_nom_g = float(n.generators.p_nom.get(g, 0.0))
        if p_nom_g <= 0:
            print(f"Peringatan: {g} p_nom <= 0, lewati constraint.")
            continue
        cfmin = float(CF_min_by_gen.loc[g])

        for d, snaps in day_groups.items():
            if len(snaps) == 0:
                continue

            # Pakai snapshots yang ada di variabel
            snaps_ok = pd.Index(snaps).intersection(snaps_var)
            if snaps_ok.empty:
                continue

            # dt -> DataArray dgn dim tdim agar broadcast valid
            dt_series = pd.Series(dt).reindex(snaps_ok).astype(float)
            coeff_da = xr.DataArray(
                dt_series.values,
                coords={tdim: snaps_ok},
                dims=(tdim,)
            )

            # Slice variabel: keep 2D (kirim [g])
            var_slice = p.loc[{gdim: [g], tdim: snaps_ok}]

            # LHS & RHS
            lhs = (var_slice * coeff_da).sum()
            rhs = cfmin * p_nom_g * float(dt_series.sum())

            dname = str(d) if isinstance(d, str) else getattr(d, "date", lambda: d)()
            m.add_constraints(lhs >= rhs, name=f"min_daily_cf_{str(g)}_{str(dname)}")

# ========= 5) Optimasi (kompatibel berbagai versi) =========
solver_name = "highs"
res = n.optimize(solver_name=solver_name, extra_functionality=add_min_daily_cf_per_gen)

status = None
termination = None
objective = None
if isinstance(res, dict):
    status = res.get("status")
    termination = res.get("termination_condition") or res.get("condition")
    objective = res.get("objective")
elif isinstance(res, (tuple, list)):
    if len(res) > 0: status = res[0]
    if len(res) > 1: termination = res[1]
    if hasattr(n, "objective") and n.objective is not None:
        objective = n.objective
    elif hasattr(n, "model") and getattr(n.model, "objective", None) is not None:
        obj = n.model.objective
        objective = getattr(obj, "value", obj)

print("\n=== Optimize Summary ===")
print("Status optimasi:", status)
print("Termination     :", termination)
print("Objective value :", objective)
print("Lanjut ke agregasi/plot/export...\n")

# ========= 6) Agregasi output per carrier + sanity check =========
p_carrier = n.generators_t.p.groupby(n.generators.carrier, axis=1).sum()
prefer_cols = ["PLTU", "PLTP", "PLTA", "PLTM", "PLTG", "PLTD", "PLTS"]
cols = [c for c in prefer_cols if c in p_carrier.columns]
p_carrier = p_carrier[cols] if cols else p_carrier

cap = (n.generators.p_nom * n.generators_t.p_max_pu).sum(axis=1)
load = n.loads_t.p_set.sum(axis=1)
print("Capacity/Load/Margin (head):")
print(pd.DataFrame({"cap": cap, "load": load, "margin": cap - load}).head(), "\n")

print("NaN checks:")
print("Any NaN p_max_pu?  ", n.generators_t.p_max_pu.isna().any().any())
print("Any NaN p_set?     ", n.loads_t.p_set.isna().any().any())
print("Min/Max p_max_pu:  ",
      n.generators_t.p_max_pu.min().min(),
      n.generators_t.p_max_pu.max().max())

# ========= 7) Plot dispatch per carrier =========
fig, ax = plt.subplots(1, 1, figsize=(14, 7))
p_carrier.plot(kind="area", ax=ax)
ax.set_title("Dispatch per Jenis Pembangkit")
ax.set_xlabel("Snapshot (waktu)")
ax.set_ylabel("MW")
ax.legend(title="Carrier", loc="upper left", ncol=2, fontsize=8)
ax.grid(True)
plt.tight_layout()
plt.savefig(plot_png, dpi=200)
plt.show()
print(f"Plot disimpan: {plot_png}")

# ========= 8) Ekspor hasil =========
# a) Dispatch semua generator
n.generators_t.p.to_csv(dispatch_csv)
print(f"Dispatch generator diekspor: {dispatch_csv}")

# b) Verifikasi CF harian aktual utk generator bertarget
p = n.generators_t.p
dt = n.snapshot_weightings["generators"]
snaps_n = n.snapshots

if isinstance(snaps_n, pd.DatetimeIndex) and snaps_n.normalize().nunique() > 1:
    day_index = snaps_n.normalize()
else:
    day_index = pd.Index(["DAY0"] * len(snaps_n), name="day")

gens_check = CF_min_by_gen[CF_min_by_gen > 0.0].index.tolist()
if gens_check:
    energy_daily = (p[gens_check].mul(dt, axis=0).groupby(day_index).sum())  # MWh/hari
    total_hours_per_day = pd.Series(dt).groupby(day_index).sum()
    cap_daily = pd.DataFrame({
        g: n.generators.p_nom.loc[g] * total_hours_per_day for g in gens_check
    })
    cf_daily = energy_daily / cap_daily
    cf_daily.to_csv(cf_daily_csv, float_format="%.6f")
    print("\nCF harian aktual (kolom=generator, baris=tanggal):")
    print(cf_daily.tail())
    print(f"CF harian diekspor: {cf_daily_csv}")
else:
    print("Tidak ada generator dengan target CF untuk diverifikasi.")

# ========= 9) UTIL POSISI (topologi) =========
def _get_positions(n):
    """
    Ambil posisi bus dari n.buses.x/y; jika tidak tersedia, pakai spring layout (networkx).
    """
    has_xy = all(col in n.buses.columns for col in ["x", "y"]) \
             and n.buses["x"].notna().all() and n.buses["y"].notna().all()
    if has_xy:
        pos = {b: (float(n.buses.at[b, "x"]), float(n.buses.at[b, "y"])) for b in n.buses.index}
        coord_label = "geo"
    else:
        try:
            import networkx as nx
        except ImportError:
            raise RuntimeError("networkx belum terpasang. Install networkx untuk layout topologis.")
        G = nx.Graph()
        G.add_nodes_from(n.buses.index)
        if not n.lines.empty:
            G.add_edges_from(zip(n.lines["bus0"], n.lines["bus1"]))
        if not n.links.empty:
            G.add_edges_from(zip(n.links["bus0"], n.links["bus1"]))
        if not n.transformers.empty:
            G.add_edges_from(zip(n.transformers["bus0"], n.transformers["bus1"]))
        pos_nx = nx.spring_layout(G, seed=42)  # layout topologis
        pos = {node: tuple(map(float, coords)) for node, coords in pos_nx.items()}
        coord_label = "topology"
    return pos, coord_label

def _edge_flows(n, snapshot=None, reduce="none", include=("lines","links","trafos"), side="p0"):
    """
    Kembalikan dataframe tepi (from_bus, to_bus, flow_MW) gabungan lines/links/trafo.
    """
    edges = []

    def pick_series(ts):
        if ts.empty:
            return None
        ts_num = ts.apply(pd.to_numeric, errors="coerce")
        if snapshot is not None:
            snap = snapshot
            if snap not in ts_num.index:
                try:
                    snap = pd.to_datetime(snapshot)
                except Exception:
                    pass
            if snap not in ts_num.index:
                raise KeyError(f"Snapshot {snapshot} tidak ditemukan.")
            return ts_num.loc[snap]
        else:
            if reduce == "max":
                return ts_num.abs().max(axis=0)
            elif reduce == "mean":
                return ts_num.abs().mean(axis=0)
            else:
                return ts_num.iloc[-1]  # last

    # Lines
    if "lines" in include and not n.lines.empty and hasattr(n.lines_t, side):
        s = pick_series(getattr(n.lines_t, side))
        if s is not None is not False:
            df = pd.DataFrame({
                "elem": n.lines.index,
                "bus0": n.lines["bus0"].values,
                "bus1": n.lines["bus1"].values,
                "flow": s.reindex(n.lines.index).values
            })
            df["kind"] = "line"
            edges.append(df)

    # Links
    if "links" in include and not n.links.empty and hasattr(n.links_t, side):
        s = pick_series(getattr(n.links_t, side))
        if s is not None is not False:
            df = pd.DataFrame({
                "elem": n.links.index,
                "bus0": n.links["bus0"].values,
                "bus1": n.links["bus1"].values,
                "flow": s.reindex(n.links.index).values
            })
            df["kind"] = "link"
            edges.append(df)

    # Transformers
    if "trafos" in include and not n.transformers.empty and hasattr(n.transformers_t, side):
        s = pick_series(getattr(n.transformers_t, side))
        if s is not None is not False:
            df = pd.DataFrame({
                "elem": n.transformers.index,
                "bus0": n.transformers["bus0"].values,
                "bus1": n.transformers["bus1"].values,
                "flow": s.reindex(n.transformers.index).values
            })
            df["kind"] = "trafo"
            edges.append(df)

    if not edges:
        return pd.DataFrame(columns=["elem","bus0","bus1","flow","kind"])

    out = pd.concat(edges, ignore_index=True)
    out["flow"] = pd.to_numeric(out["flow"], errors="coerce").fillna(0.0)
    return out

def _bus_size_series(n, mode="load"):
    """
    Ukuran bus: total beban (energi) atau degree topologis.
    """
    idx = n.buses.index
    if mode == "load" and hasattr(n.loads_t, "p_set") and not n.loads_t.p_set.empty and not n.loads.empty:
        load_ts = n.loads_t.p_set.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        col2bus = n.loads["bus"].to_dict()
        if col2bus:
            by_bus = load_ts.rename(columns=col2bus).groupby(level=0, axis=1).sum().abs().sum()
            return by_bus.reindex(idx).fillna(0.0)

    # fallback degree
    def vc(series):
        if series is None or len(series) == 0:
            return pd.Series(0, index=idx, dtype=int)
        return pd.Series(series).value_counts().reindex(idx).fillna(0).astype(int)

    lines_inc = vc(pd.concat([n.lines["bus0"], n.lines["bus1"]], ignore_index=True) if not n.lines.empty else pd.Series([], dtype=object))
    links_inc = vc(pd.concat([n.links["bus0"], n.links["bus1"]], ignore_index=True) if not n.links.empty else pd.Series([], dtype=object))
    trafos_inc = vc(pd.concat([n.transformers["bus0"], n.transformers["bus1"]], ignore_index=True) if not n.transformers.empty else pd.Series([], dtype=object))
    gens_inc  = vc(n.generators["bus"] if not n.generators.empty else pd.Series([], dtype=object))

    return (lines_inc + links_inc + trafos_inc + gens_inc).astype(float).reindex(idx).fillna(0.0)

# ========= 10) PLOT TRANSFER (TOPLOGI XY ATAU GEO XY TANPA BASEMAP) =========
def plot_transfer_map(
    n,
    snapshot=None,          # contoh: None (pakai last), atau "2025-01-01 12:00"
    reduce="none",          # "none" | "max" | "mean" saat snapshot=None
    side="p0",              # p0 atau p1
    unit="MW",              # label unit
    scale_width=0.04,       # skala tebal garis (coba 0.02..0.1)
    min_width=0.6,          # tebal minimum
    annotate_edges=True,    # tulis nilai MW di tengah garis
    annotate_buses=False,   # tulis nama bus
    bus_size_mode="load",   # "load" | "degree"
    arrow=True,             # panah arah aliran (dari bus0 → bus1 jika flow>0 utk p0)
    savepath=None
):
    """
    Plot bus, garis antar-bus, dan BESAR TRANSFER, memakai koordinat di n.buses.x/y (jika ada)
    atau layout topologi.
    """
    pos, coord_label = _get_positions(n)
    edges = _edge_flows(n, snapshot=snapshot, reduce=reduce, side=side)
    ax = plt.figure(figsize=(13, 9)).gca()

    # Normalisasi untuk warna
    if edges.empty:
        print("[INFO] Tidak ada data aliran untuk digambar.")
    else:
        mag = edges["flow"].abs()
        vmax = max(mag.max(), 1e-6)
        vmin = 0.0
        cmap = plt.cm.viridis

        for _, row in edges.iterrows():
            b0, b1 = row["bus0"], row["bus1"]
            if b0 not in pos or b1 not in pos:
                continue
            x0, y0 = pos[b0]; x1, y1 = pos[b1]
            f = float(row["flow"])
            w = min_width + scale_width * abs(f)  # tebal garis
            c = cmap((abs(f) - vmin) / (vmax - vmin))

            # garis utama
            ax.plot([x0, x1], [y0, y1], lw=w, color=c, alpha=0.85, solid_capstyle="round", zorder=1)

            # panah arah (opsional)
            if arrow and abs(f) > 1e-6:
                if f >= 0:
                    xa, ya, xb, yb = x0, y0, x1, y1
                else:
                    xa, ya, xb, yb = x1, y1, x0, y0
                dx, dy = xb - xa, yb - ya
                L = np.hypot(dx, dy)
                if L > 1e-9:
                    shrink = 0.05
                    xa2 = xa + dx * shrink
                    ya2 = ya + dy * shrink
                    xb2 = xb - dx * shrink
                    yb2 = yb - dy * shrink
                    ax.annotate("",
                        xy=(xb2, yb2), xytext=(xa2, ya2),
                        arrowprops=dict(arrowstyle="->", lw=max(0.8, w*0.6), color=c, alpha=0.9),
                        zorder=2
                    )

            # anotasi nilai MW (opsional)
            if annotate_edges and abs(f) > 1e-6:
                xm, ym = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                ax.text(xm, ym, f"{abs(f):.1f}", fontsize=8, ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.7, lw=0),
                        zorder=3)

        # colorbar (berdasarkan magnitude)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cb = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label(f"|Transfer| ({unit})")

    # BUS: ukuran sesuai total beban/degree
    bsize = _bus_size_series(n, mode=bus_size_mode)
    ms = 30 * (bsize / (bsize.max() if bsize.max() > 0 else 1)) + 18 if (bsize > 0).any() else pd.Series(28.0, index=n.buses.index)
    xs = [pos[b][0] for b in n.buses.index]
    ys = [pos[b][1] for b in n.buses.index]
    ms_sizes = [float(ms.get(b, 20.0)) for b in n.buses.index]
    ax.scatter(xs, ys, s=ms_sizes, edgecolor="k", linewidths=0.5, alpha=0.95, zorder=4)

    if annotate_buses:
        for b in n.buses.index:
            x, y = pos[b]
            ax.text(x, y, b, fontsize=8, ha="center", va="bottom", zorder=5)

    title = ["Transfer Map", f"coords={coord_label}", f"side={side}"]
    if snapshot is not None:
        title.append(f"@ {snapshot}")
    elif reduce != "none":
        title.append(f"({reduce} over time)")
    ax.set_title(" | ".join(title))
    ax.set_xlabel("x"); ax.set_ylabel("y"); ax.grid(True)
    plt.tight_layout()
    if savepath:
        plt.savefig(savepath, dpi=200)
        print("Saved:", savepath)
    plt.show()

# ========= 11) PLOT TRANSFER GEOGRAFIS (lon/lat + basemap) =========
def _load_bus_lonlat(n, csv_fallback=None):
    """
    Ambil posisi bus dari n.buses.x/y (diasumsikan lon/lat derajat).
    Jika tidak ada/NaN, coba baca CSV fallback (buses.csv) yang punya kolom: name,x,y.
    Return: dict {bus: (lon, lat)}
    """
    pos = {}

    has_xy = all(c in n.buses.columns for c in ["x","y"]) and \
             n.buses["x"].notna().any() and n.buses["y"].notna().any()
    if has_xy:
        try:
            for b, row in n.buses[["x","y"]].dropna().iterrows():
                lon = float(row["x"]); lat = float(row["y"])
                pos[b] = (lon, lat)
        except Exception as e:
            print("[WARN] Gagal baca n.buses x/y:", e)

    # Fallback ke CSV (kalau belum lengkap)
    if csv_fallback and len(pos) < len(n.buses.index):
        try:
            df = pd.read_csv(csv_fallback)
            cols = {c.lower(): c for c in df.columns}
            assert "name" in cols and "x" in cols and "y" in cols
            df = df.rename(columns={cols["name"]: "name", cols["x"]: "x", cols["y"]: "y"})
            df = df.set_index("name")
            for b in n.buses.index:
                if b not in pos and b in df.index and pd.notna(df.at[b,"x"]) and pd.notna(df.at[b,"y"]):
                    pos[b] = (float(df.at[b,"x"]), float(df.at[b,"y"]))
            print(f"[INFO] Posisi bus dilengkapi dari CSV fallback: {csv_fallback}")
        except Exception as e:
            print("[WARN] Fallback CSV tidak dipakai:", e)

    return pos

def plot_transfer_map_geo(
    n,
    snapshot=None,          # None (last) | "YYYY-mm-dd HH:MM"
    reduce="none",          # "none"|"max"|"mean" jika snapshot=None
    side="p0",              # p0 atau p1
    annotate_edges=True,
    annotate_buses=False,
    bus_size_mode="load",   # "load"|"degree"
    zoom=8,                 # zoom untuk tile peta
    tiles_provider="osm",   # "osm"|"stamen-terrain"|"stamen-toner"|"stamen-watercolor"
    csv_fallback=None,      # path ke buses.csv kalau n.buses.x/y kosong
    savepath=None
):
    """
    Tampilkan peta (OpenStreetMap/Stamen) + node (lon/lat) + garis aliran.
    - Menggunakan lon=X, lat=Y dari n.buses (derajat).
    - Jika belum ada, bisa fallback dari CSV.
    """
    # 1) Siapkan posisi lon/lat
    pos = _load_bus_lonlat(n, csv_fallback=csv_fallback)
    if not pos:
        raise RuntimeError("Tidak ada posisi lon/lat untuk bus. Pastikan kolom x/y berisi longitude/latitude atau berikan csv_fallback.")

    # 2) Ambil tepi (flow)
    edges = _edge_flows(n, snapshot=snapshot, reduce=reduce, side=side)

    # 3) Batas peta dari sebaran lon/lat
    lons = [pos[b][0] for b in n.buses.index if b in pos]
    lats = [pos[b][1] for b in n.buses.index if b in pos]
    if not lons or not lats:
        raise RuntimeError("Koordinat lon/lat kosong untuk seluruh bus.")

    pad_lon = max(0.05, (max(lons) - min(lons)) * 0.15)
    pad_lat = max(0.05, (max(lats) - min(lats)) * 0.15)
    extent = [min(lons) - pad_lon, max(lons) + pad_lon,
              min(lats) - pad_lat, max(lats) + pad_lat]

    # 4) Siapkan cartopy (fallback jika tidak tersedia)
    try:
        import cartopy.crs as ccrs
        import cartopy.feature as cfeature
        from cartopy.io import img_tiles

        # pilih provider
        if tiles_provider.lower() == "osm":
            tiles = img_tiles.OSM()
        elif tiles_provider.lower() == "stamen-terrain":
            tiles = img_tiles.Stamen('terrain')
        elif tiles_provider.lower() == "stamen-toner":
            tiles = img_tiles.Stamen('toner')
        elif tiles_provider.lower() == "stamen-watercolor":
            tiles = img_tiles.Stamen('watercolor')
        else:
            tiles = img_tiles.OSM()

        fig = plt.figure(figsize=(13, 9))
        ax = plt.axes(projection=tiles.crs)  # WebMercator
        ax.set_extent(extent, crs=ccrs.PlateCarree())
        try:
            ax.add_image(tiles, zoom)  # base map tiles
        except Exception as e:
            print("[WARN] Gagal memuat tiles (mungkin offline):", e)
            ax.coastlines(resolution="10m", linewidth=0.6)
            ax.add_feature(cfeature.LAND, alpha=0.2)
            ax.add_feature(cfeature.BORDERS, linewidth=0.4)
            ax.add_feature(cfeature.LAKES, alpha=0.2)
            ax.add_feature(cfeature.RIVERS, alpha=0.2)

        # 5) Gambar edges
        if not edges.empty:
            mag = edges["flow"].abs()
            vmax = max(mag.max(), 1e-6)
            vmin = 0.0
            cmap = plt.cm.viridis

            for _, row in edges.iterrows():
                b0, b1 = row["bus0"], row["bus1"]
                if b0 not in pos or b1 not in pos:
                    continue
                lon0, lat0 = pos[b0]
                lon1, lat1 = pos[b1]
                f = float(row["flow"])
                w = 0.6 + 0.04 * abs(f)  # ketebalan garis
                c = cmap((abs(f) - vmin) / (vmax - vmin))

                ax.plot([lon0, lon1], [lat0, lat1],
                        transform=ccrs.PlateCarree(),
                        linewidth=w, color=c, alpha=0.9)

                # anotasi nilai MW di tengah
                if annotate_edges and abs(f) > 1e-6:
                    xm, ym = (lon0 + lon1) / 2.0, (lat0 + lat1) / 2.0
                    ax.text(xm, ym, f"{abs(f):.1f}",
                            transform=ccrs.PlateCarree(),
                            fontsize=8, ha="center", va="center",
                            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.7, lw=0))

            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
            sm.set_array([])
            cb = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
            cb.set_label("|Transfer| (MW)")

        # 6) Ukuran node
        bsize = _bus_size_series(n, mode=bus_size_mode)
        if (bsize > 0).any():
            scale = 30 * (bsize / bsize.max()) + 18
        else:
            scale = pd.Series(28.0, index=n.buses.index)

        # 7) Gambar node
        xs = [pos[b][0] for b in n.buses.index if b in pos]
        ys = [pos[b][1] for b in n.buses.index if b in pos]
        ss = [float(scale.get(b, 20.0)) for b in n.buses.index if b in pos]
        ax.scatter(xs, ys,
                   transform=ccrs.PlateCarree(),
                   s=ss, edgecolor="k", linewidths=0.5, alpha=0.95, zorder=5)

        if annotate_buses:
            for b in n.buses.index:
                if b in pos:
                    ax.text(pos[b][0], pos[b][1], b,
                            transform=ccrs.PlateCarree(),
                            fontsize=8, ha="center", va="bottom", zorder=6)

        # 8) Judul
        title = ["Transfer Map (Geographic)", f"side={side}"]
        if snapshot is not None:
            title.append(f"@ {snapshot}")
        elif reduce != "none":
            title.append(f"({reduce} over time)")
        ax.set_title(" | ".join(title))
        plt.tight_layout()

        if savepath:
            plt.savefig(savepath, dpi=200)
            print("Saved:", savepath)
        plt.show()

    except ImportError:
        # Fallback tanpa peta (masih sesuai lon/lat, tapi plot biasa)
        print("[WARN] cartopy tidak terpasang. Menampilkan scatter/line sederhana tanpa peta.")
        fig, ax = plt.subplots(figsize=(13, 9))
        # edges
        if not edges.empty:
            mag = edges["flow"].abs()
            vmax = max(mag.max(), 1e-6)
            vmin = 0.0
            cmap = plt.cm.viridis
            for _, row in edges.iterrows():
                b0, b1 = row["bus0"], row["bus1"]
                if b0 not in pos or b1 not in pos:
                    continue
                x0, y0 = pos[b0]; x1, y1 = pos[b1]
                f = float(row["flow"])
                w = 0.6 + 0.04 * abs(f)
                c = cmap((abs(f) - vmin) / (vmax - vmin))
                ax.plot([x0, x1], [y0, y1], lw=w, color=c, alpha=0.9)
                if annotate_edges and abs(f) > 1e-6:
                    xm, ym = (x0+x1)/2.0, (y0+y1)/2.0
                    ax.text(xm, ym, f"{abs(f):.1f}", fontsize=8,
                            ha="center", va="center",
                            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.7, lw=0))
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
            sm.set_array([])
            cb = plt.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
            cb.set_label("|Transfer| (MW)")

        # nodes
        bsize = _bus_size_series(n, mode=bus_size_mode)
        if (bsize > 0).any():
            scale = 30 * (bsize / bsize.max()) + 18
        else:
            scale = pd.Series(28.0, index=n.buses.index)

        xs = [pos[b][0] for b in n.buses.index if b in pos]
        ys = [pos[b][1] for b in n.buses.index if b in pos]
        ss = [float(scale.get(b, 20.0)) for b in n.buses.index if b in pos]
        ax.scatter(xs, ys, s=ss, edgecolor="k", linewidths=0.5, alpha=0.95, zorder=5)

        if annotate_buses:
            for b in n.buses.index:
                if b in pos:
                    ax.text(pos[b][0], pos[b][1], b, fontsize=8, ha="center", va="bottom", zorder=6)

        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_xlabel("Longitude"); ax.set_ylabel("Latitude")
        title = ["Transfer Map (Geographic - NO BASEMAP)", f"side={side}"]
        if snapshot is not None:
            title.append(f"@ {snapshot}")
        elif reduce != "none":
            title.append(f"({reduce} over time)")
        ax.set_title(" | ".join(title))
        ax.grid(True)
        plt.tight_layout()
        if savepath:
            plt.savefig(savepath, dpi=200)
            print("Saved:", savepath)
        plt.show()

# ========= 12) CONTOH PEMAKAIAN =========
# 1) Snapshot terakhir (default), anotasi nilai MW, panah aktif (topologi/geo-xy)
plot_transfer_map(
    n,
    snapshot=None, reduce="none", side="p0",
    annotate_edges=True, annotate_buses=False,
    bus_size_mode="load",
    savepath=str(data_folder / "transfer_last.png")
)

# 2) Transfer MAKSIMUM (|p|) sepanjang waktu, tampilkan nama bus (topologi/geo-xy)
plot_transfer_map(
    n,
    snapshot=None, reduce="max", side="p0",
    annotate_edges=True, annotate_buses=True,
    bus_size_mode="degree",
    savepath=str(data_folder / "transfer_max.png")
)

# 3) Peta GEOGRAFIS (lon/lat + basemap OSM)
#    - Jika n.buses sudah punya x=lon,y=lat di derajat, tidak perlu csv_fallback.
#    - Jika belum ada, siapkan file buses.csv: kolom [name,x,y] (name = nama bus persis di n.buses.index).
#       Contoh path fallback: data_folder / "buses.csv"
try:
    plot_transfer_map_geo(
        n,
        snapshot=None, reduce="none", side="p0",
        annotate_edges=True, annotate_buses=False,
        bus_size_mode="load",
        zoom=8,
        tiles_provider="osm",  # "osm"|"stamen-terrain"|"stamen-toner"|"stamen-watercolor"
        csv_fallback=str(data_folder / "buses.csv"),
        savepath=str(data_folder / "transfer_geo_last.png")
    )

    plot_transfer_map_geo(
        n,
        snapshot=None, reduce="max", side="p0",
        annotate_edges=True, annotate_buses=True,
        bus_size_mode="degree",
        zoom=8,
        tiles_provider="stamen-terrain",
        csv_fallback=str(data_folder / "buses.csv"),
        savepath=str(data_folder / "transfer_geo_max.png")
    )
except Exception as e:
    print("[GEOMAP] PLOT SKIPPED:", e)
    print("Pastikan kolom n.buses['x','y'] berisi longitude/latitude (derajat), atau siapkan buses.csv (name,x,y).")


