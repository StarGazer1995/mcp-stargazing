import json
import argparse
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord, get_constellation

def compute_centers(step: int = 2) -> list[dict]:
    ra_vals = np.arange(0, 360, step, dtype=float)
    dec_vals = np.arange(-90, 91, step, dtype=float)
    ra_grid, dec_grid = np.meshgrid(ra_vals, dec_vals)
    ra_flat = ra_grid.ravel()
    dec_flat = dec_grid.ravel()
    sc = SkyCoord(ra=ra_flat * u.deg, dec=dec_flat * u.deg, frame="icrs")
    names = np.array(get_constellation(sc, constellation_list='iau'))
    ra_rad = np.deg2rad(ra_flat)
    dec_rad = np.deg2rad(dec_flat)
    w = np.cos(dec_rad)
    x = np.cos(dec_rad) * np.cos(ra_rad) * w
    y = np.cos(dec_rad) * np.sin(ra_rad) * w
    z = np.sin(dec_rad) * w
    centers = {}
    for i, n in enumerate(names):
        if n not in centers:
            centers[n] = {"sx": 0.0, "sy": 0.0, "sz": 0.0}
        centers[n]["sx"] += x[i]
        centers[n]["sy"] += y[i]
        centers[n]["sz"] += z[i]
    out = []
    for n, s in centers.items():
        vx = s["sx"]
        vy = s["sy"]
        vz = s["sz"]
        norm = np.sqrt(vx * vx + vy * vy + vz * vz)
        if norm == 0:
            continue
        vx /= norm
        vy /= norm
        vz /= norm
        ra = (np.rad2deg(np.arctan2(vy, vx)) + 360.0) % 360.0
        dec = np.rad2deg(np.arcsin(vz))
        out.append({"name": n, "ra": float(ra), "dec": float(dec)})
    out.sort(key=lambda d: d["name"])
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="src/data/constellation_centers.json")
    p.add_argument("--step", type=int, default=2)
    args = p.parse_args()
    centers = compute_centers(step=args.step)
    with open(args.out, "w") as f:
        json.dump(centers, f, ensure_ascii=False, indent=2)
    print(f"written {len(centers)} entries to {args.out}")

if __name__ == "__main__":
    main()
