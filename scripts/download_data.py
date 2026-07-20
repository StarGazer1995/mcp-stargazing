import json
from pathlib import Path
from typing import Any

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad

# SIMBAD object types that indicate stars (point sources), not deep-sky objects.
# When SIMBAD resolves an NGC/IC number to a star, we discard it.
_STELLAR_TYPES = frozenset(
    {
        '*',
        '**',
        '***',
        'V*',
        'Pu*',
        'Em*',
        'Ae*',
        'Be*',
        'PM*',
        'WD*',
        'TT*',
        'C*',
        'S*',
        'Or*',
        'UV*',
        'WR*',
        'Y*O',
        'pr*',
        'IR',
        'MIR',
        'NIR',
        'FIR',
        'Psr',
        'gam',
        'X',
        'ULX',
        'Bz?',
        'Rad',
        'SB*',
        'No*',
        'As*',
        'Mi*',
        'EB*',
        'Al*',
        'bL*',
        'LP*',
        'Pa*',
        'El*',
        'HB*',
        'RC*',
        'Ro*',
        'RR*',
        'RS*',
        'SN*',
        'Sy*',
        'WD?',
    }
)


# ── angular-size fallback by object type ─────────────────────────────
# When SIMBAD has no galdim_* data, estimate from the object type.
# Values are typical major/minor axis in arcmin; conservative by design.

_FALLBACK_SIZES: dict[str, tuple[float, float]] = {
    # Galaxies (tend to be elongated: min ≈ 0.5 × maj)
    'Gx': (2.0, 1.0),
    'GiG': (2.0, 1.0),
    'GiP': (2.0, 1.0),
    'GiC': (1.5, 0.7),
    'SyG': (1.5, 0.7),
    'Sy1': (1.5, 0.7),
    'Sy2': (1.5, 0.7),
    'LIN': (1.5, 0.7),
    'AGN': (1.5, 0.7),
    'BLL': (1.5, 0.7),
    'SBG': (1.5, 0.7),
    'H2G': (1.5, 0.7),
    'PaG': (1.5, 0.7),
    'G': (2.0, 1.0),
    # Clusters (mostly round)
    'GlC': (5.0, 5.0),
    'Gb': (4.0, 4.0),
    'OpC': (15.0, 15.0),
    'Cl*': (10.0, 10.0),
    'Cl?': (10.0, 10.0),
    'ClG': (10.0, 10.0),
    'OC': (10.0, 10.0),
    # Nebulae
    'PN': (0.5, 0.5),
    'HII': (15.0, 10.0),
    'RNe': (15.0, 10.0),
    'Nb': (15.0, 10.0),
    'C+N': (15.0, 10.0),
    'ISM': (20.0, 12.0),
    'sh': (15.0, 10.0),
    'Em*': (5.0, 5.0),
    # Supernova remnants
    'SNR': (8.0, 8.0),
    # Additional galaxy subtypes
    'AG?': (1.5, 0.7),
    'IG': (2.0, 1.0),
    'rG': (1.5, 1.0),
    'EmG': (2.0, 1.0),
    'BiC': (2.0, 1.0),
    'G?': (2.0, 1.0),
    'PoG': (1.0, 1.0),
    'mul': (2.0, 2.0),
    # Emission / nebulae subtypes
    'GNe': (15.0, 10.0),
    'EmO': (10.0, 10.0),
    'HH': (0.5, 0.5),
    'Opt': (1.0, 1.0),
    # Unknown / SIMBAD error — conservative generic fallback
    'err': (2.0, 1.0),
    '?': (2.0, 1.0),
    '': (2.0, 1.0),
}


def _apply_fallback_sizes(objects: list[dict[str, Any]]) -> int:
    """Fill missing angular sizes with type-based estimates.

    Only touches objects where ``angular_size_maj_arcmin`` is ``None``.
    Returns the number of objects that received fallback values.
    """
    filled = 0
    for obj in objects:
        if obj.get('angular_size_maj_arcmin') is not None:
            continue
        maj, min_ = _FALLBACK_SIZES.get(obj['type'], (None, None))
        if maj is None:
            continue
        obj['angular_size_maj_arcmin'] = maj
        obj['angular_size_min_arcmin'] = min_
        obj['angular_size_pa_deg'] = None
        filled += 1
    return filled


def _round_floats(objects: list[dict[str, Any]]) -> None:
    """Round float fields to meaningful precision in-place.

    ======================  ==========  ======
    Field                   Precision   Reason
    ======================  ==========  ======
    ``ra``, ``dec``         4 decimal   ~11 m at equator
    ``magnitude``           2 decimal   tenths of mag are typical
    ``angular_size_*_arcmin`` 1 decimal 0.1 arcmin ≈ visual limit
    ``angular_size_pa_deg`` 0 decimal   integer degrees for PA
    ======================  ==========  ======
    """
    for obj in objects:
        for key in ('ra', 'dec'):
            if isinstance(obj.get(key), float):
                obj[key] = round(obj[key], 4)
        if isinstance(obj.get('magnitude'), float):
            obj['magnitude'] = round(obj['magnitude'], 2)
        for key in ('angular_size_maj_arcmin', 'angular_size_min_arcmin'):
            if isinstance(obj.get(key), float):
                obj[key] = round(obj[key], 1)
        if isinstance(obj.get('angular_size_pa_deg'), float):
            obj['angular_size_pa_deg'] = round(obj['angular_size_pa_deg'])


def _normalize_name(name: str) -> str:
    """Collapse multiple spaces: ``'M   1'`` → ``'M 1'``."""
    return ' '.join(name.strip().split())


def _parse_float(value: Any) -> float | None:
    """Convert astropy/numpy scalar → plain float, or None for masked/NaN."""
    if value is None:
        return None
    try:
        if isinstance(value, np.ma.MaskedArray):
            return None if value.mask else _parse_float(value.data)
        if hasattr(value, 'mask') and value.mask:
            return None
        v = float(value)
        return None if (np.isnan(v) or np.isinf(v)) else v
    except (ValueError, TypeError):
        return None


def download_messier_objects() -> list[dict[str, Any]]:
    print('Downloading Messier Catalog via Simbad...')

    # Configure Simbad to retrieve relevant fields
    # id(M) is deprecated, just use main_id or assume query order
    # flux(V) is deprecated in favor of 'V'
    custom_simbad = Simbad()
    custom_simbad.add_votable_fields(
        'otype',
        'flux(V)',
        'galdim_majaxis',
        'galdim_minaxis',
        'galdim_angle',
    )
    # Actually, let's stick to simple defaults + otype + flux

    # Note: Simbad API changes frequently.
    # Let's try to remove 'id(M)' which caused the crash.

    messier_objects = []

    # M1 to M110
    identifiers = [f'M {i}' for i in range(1, 111)]

    # Query in batches to be safe, or one big query
    # Simbad query_objects can handle a list
    try:
        table = custom_simbad.query_objects(identifiers)

        if table is None:
            print('Error: No results from Simbad for Messier objects.')
            return []

        for row in table:
            # Parse RA/Dec
            # Simbad returns RA/Dec as strings usually "HH MM SS", "DD MM SS"
            # Column names might be 'RA_d' or 'DEC_d' if we asked for degrees, or just 'RA'/'DEC'
            # Let's check typical defaults. Simbad default is usually 'RA' and 'DEC' in sexagesimal.

            ra_key = 'RA' if 'RA' in table.colnames else 'ra'
            dec_key = 'DEC' if 'DEC' in table.colnames else 'dec'

            if ra_key not in table.colnames:
                # Fallback: maybe 'RA_2000' or similar?
                # Let's print columns if we fail
                print(f'Columns found: {table.colnames}')
                raise KeyError('RA')

            ra_val = row[ra_key]
            dec_val = row[dec_key]

            # SIMBAD returns RA as float (decimal degrees) with newer API,
            # or string (sexagesimal) with older default columns.
            if isinstance(ra_val, (int, float)):
                coord = SkyCoord(ra=ra_val * u.deg, dec=dec_val * u.deg)
            else:
                coord = SkyCoord(f'{ra_val} {dec_val}', unit=(u.hourangle, u.deg))

            # Parse Magnitude (Flux V)
            mag = 99.9
            if 'FLUX_V' in row.colnames:
                mag = float(row['FLUX_V'])
            elif 'V' in row.colnames:
                mag = float(row['V'])

            # Parse Object Type
            # Column might be 'OTYPE' or 'OTYPE_S' or similar
            otype = 'Unknown'
            if 'OTYPE' in table.colnames:
                otype = str(row['OTYPE'])
            elif 'otype' in table.colnames:
                otype = str(row['otype'])
            if otype in _STELLAR_TYPES:
                continue

            # Parse Name (Main ID)
            name = 'Unknown'
            if 'MAIN_ID' in table.colnames:
                name = str(row['MAIN_ID'])
            elif 'main_id' in table.colnames:
                name = str(row['main_id'])
            name = _normalize_name(name)

            messier_objects.append(
                {
                    'name': name,
                    'type': otype,
                    'ra': float(coord.ra.deg),
                    'dec': float(coord.dec.deg),
                    'magnitude': mag,
                    'catalog': 'Messier',
                    'angular_size_maj_arcmin': _parse_float(row['galdim_majaxis']),
                    'angular_size_min_arcmin': _parse_float(row['galdim_minaxis']),
                    'angular_size_pa_deg': _parse_float(row['galdim_angle']),
                }
            )

        print(f'Successfully fetched {len(messier_objects)} Messier objects.')
        return messier_objects

    except Exception as e:
        print(f'Failed to download Messier objects: {e}')
        return []


def _download_catalog_objects(
    prefix: str,
    first: int,
    last: int,
    catalog_label: str,
) -> list[dict[str, Any]]:
    """Download objects from SIMBAD by name range in a single query.

    Each object carries coords, type, V magnitude, and ``galdim_*`` angular-size
    data — all returned by SIMBAD in one request.
    """
    print(f'Downloading {catalog_label} objects via SIMBAD …')

    simbad = Simbad()
    simbad.add_votable_fields(
        'otype',
        'flux(V)',
        'galdim_majaxis',
        'galdim_minaxis',
        'galdim_angle',
    )

    all_names = [f'{prefix} {i}' for i in range(first, last + 1)]
    print(f'  Querying {len(all_names):,} names …', end=' ', flush=True)

    table = simbad.query_objects(all_names)
    if table is None or len(table) == 0:
        print('0 results')
        return []

    result: list[dict[str, Any]] = []
    for row in table:
        ra_val = row['RA'] if 'RA' in table.colnames else row['ra']
        dec_val = row['DEC'] if 'DEC' in table.colnames else row['dec']
        try:
            if isinstance(ra_val, (int, float)):
                coord = SkyCoord(ra=ra_val * u.deg, dec=dec_val * u.deg)
            else:
                coord = SkyCoord(f'{ra_val} {dec_val}', unit=(u.hourangle, u.deg))
        except Exception:
            continue

        mag = 99.9
        for col in ('FLUX_V', 'V'):
            if col in table.colnames:
                try:
                    mag = float(row[col])
                except (ValueError, TypeError):
                    pass
                break

        otype = str(row.get('OTYPE', row.get('otype', 'Unknown')))
        if otype in _STELLAR_TYPES:
            continue
        name = _normalize_name(str(row.get('MAIN_ID', row.get('main_id', ''))))

        result.append(
            {
                'name': name,
                'type': otype,
                'ra': float(coord.ra.deg),
                'dec': float(coord.dec.deg),
                'magnitude': mag,
                'catalog': catalog_label,
                'angular_size_maj_arcmin': _parse_float(row['galdim_majaxis']),
                'angular_size_min_arcmin': _parse_float(row['galdim_minaxis']),
                'angular_size_pa_deg': _parse_float(row['galdim_angle']),
            }
        )

    print(f'{len(result):,} found.')
    return result


def _build_spatial_index(
    objects: list[dict[str, Any]], grid_size: float = 1.0
) -> dict[tuple[int, int], list[int]]:
    """Bucket objects into a 2-D spatial grid for fast proximity lookup."""
    from collections import defaultdict

    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, obj in enumerate(objects):
        ra_bin = int(obj['ra'] / grid_size)
        dec_bin = int(obj['dec'] / grid_size)
        grid[(ra_bin, dec_bin)].append(i)
    return grid


def main():
    messier = download_messier_objects()
    ngc = _download_catalog_objects('NGC', 1, 7840, 'NGC')
    ic = _download_catalog_objects('IC', 1, 5386, 'IC')

    final_list: list[dict[str, Any]] = list(messier)

    # Spatial-index deduplication: maintain a grid of all accepted objects so
    # that NGC and IC entries which duplicate Messier or each other are removed.
    separation_threshold_deg = 0.1  # 6 arcmin — same object, different catalog

    print('Deduplicating (M vs NGC vs IC) …')
    duplicates = 0
    for catalog_objects in (ngc, ic):
        # Rebuild grid against current final_list for each catalog
        accepted_coords = [SkyCoord(o['ra'], o['dec'], unit='deg') for o in final_list]
        grid = _build_spatial_index(final_list, grid_size=1.0)

        for obj in catalog_objects:
            obj_coord = SkyCoord(obj['ra'], obj['dec'], unit='deg')
            ra_bin = int(obj['ra'] / 1.0)
            dec_bin = int(obj['dec'] / 1.0)
            is_dup = False

            for dra in (-1, 0, 1):
                for ddec in (-1, 0, 1):
                    for idx in grid.get((ra_bin + dra, dec_bin + ddec), []):
                        if (
                            obj_coord.separation(accepted_coords[idx]).deg
                            < separation_threshold_deg
                        ):
                            is_dup = True
                            break
                    if is_dup:
                        break
                if is_dup:
                    break

            if not is_dup:
                final_list.append(obj)
            else:
                duplicates += 1

    print(f'  {duplicates} spatial duplicates removed.')

    # Name-based dedup — SIMBAD may return identical rows for the same input name
    seen_names: set[str] = set()
    name_dups = 0
    deduped: list[dict[str, Any]] = []
    for obj in final_list:
        if obj['name'] not in seen_names:
            seen_names.add(obj['name'])
            deduped.append(obj)
        else:
            name_dups += 1
    final_list = deduped
    print(f'  {name_dups} name duplicates removed.')
    print(f'  Total objects: {len(final_list):,}')

    # Type-based fallback for objects without SIMBAD angular-size data
    filled = _apply_fallback_sizes(final_list)
    print(f'Fallback sizes: {filled} objects filled by type estimate.')

    # Coverage summary
    with_size = sum(1 for o in final_list if o.get('angular_size_maj_arcmin') is not None)
    print(
        f'Angular-size coverage: {with_size}/{len(final_list)} '
        f'({with_size / len(final_list) * 100:.1f}%)'
    )

    # ── Compact: round floats and strip whitespace ───────────────────
    _round_floats(final_list)

    # Save to file
    output_path = Path(__file__).resolve().parents[1] / 'src' / 'data' / 'objects.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w') as f:
        json.dump(final_list, f, separators=(',', ':'))

    size_kb = output_path.stat().st_size / 1024
    print(f'Saved to {output_path} ({size_kb:.0f} KB)')


if __name__ == '__main__':
    main()
