import json
from pathlib import Path
from typing import Any

import astropy.units as u
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad
from astroquery.vizier import Vizier


def download_messier_objects() -> list[dict[str, Any]]:
    print('Downloading Messier Catalog via Simbad...')

    # Configure Simbad to retrieve relevant fields
    # id(M) is deprecated, just use main_id or assume query order
    # flux(V) is deprecated in favor of 'V'
    custom_simbad = Simbad()
    custom_simbad.add_votable_fields(
        'otype', 'flux(V)'
    )  # Simbad might still accept flux(V) or we should use 'V'
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

            ra_str = row[ra_key]
            dec_str = row[dec_key]

            coord = SkyCoord(f'{ra_str} {dec_str}', unit=(u.hourangle, u.deg))

            # Parse Magnitude (Flux V)
            # Column name changed to 'FLUX_V' or just 'V'
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

            # Parse Name (Main ID)
            # Default main_id
            name = 'Unknown'
            if 'MAIN_ID' in table.colnames:
                name = str(row['MAIN_ID'])
            elif 'main_id' in table.colnames:
                name = str(row['main_id'])

            messier_objects.append(
                {
                    'name': name,
                    'type': otype,
                    'ra': float(coord.ra.deg),
                    'dec': float(coord.dec.deg),
                    'magnitude': mag,
                    'catalog': 'Messier',
                }
            )

        print(f'Successfully fetched {len(messier_objects)} Messier objects.')
        return messier_objects

    except Exception as e:
        print(f'Failed to download Messier objects: {e}')
        return []


def download_ngc_objects(max_mag: float = 10.0) -> list[dict[str, Any]]:
    print(f'Downloading NGC Objects (Mag < {max_mag}) via Vizier...')

    # Use Vizier to query NGC 2000.0 Catalog (VII/118)
    # We want objects brighter than max_mag

    v = Vizier(
        columns=['NGC', 'Type', 'RA2000', 'DE2000', 'Mag', 'Const'], row_limit=10000
    )  # Get enough rows

    # Filter: Mag < max_mag
    # Note: Vizier filters are strings like "< 10"

    try:
        # Catalog VII/118: NGC 2000.0 (Sky Publishing, ed. Sinnott 1988)
        # It seems requesting specific columns is filtering out the main ID column if we don't guess it right?
        # Or maybe Vizier is returning a different subset.

        # Let's try NOT specifying columns initially to see what we get by default.
        # This usually returns the default view.

        v = Vizier(row_limit=10000)
        catalogs = v.query_constraints(catalog='VII/118', Mag=f'<{max_mag}')

        if not catalogs:
            print('Error: No results from Vizier for NGC objects.')
            return []

        table = catalogs[0]

        # Determine column names
        ngc_col = 'NGC' if 'NGC' in table.colnames else 'Name'  # Fallback
        type_col = 'Type' if 'Type' in table.colnames else 'Otype'
        mag_col = 'Mag' if 'Mag' in table.colnames else 'V'

        if ngc_col not in table.colnames:
            # Try one more fallback: maybe it's just index?
            # But VII/118 definitely has 'NGC' column usually.
            print(f'NGC Columns found: {table.colnames}')
            return []  # Fail gracefully

        # Now re-query with the exact columns we want + hidden coordinates
        # We must use the exact names we found.

        cols = [ngc_col, type_col, mag_col, 'Const', '_RAJ2000', '_DEJ2000']
        v = Vizier(columns=cols, row_limit=10000)
        catalogs = v.query_constraints(catalog='VII/118', Mag=f'<{max_mag}')
        table = catalogs[0]

        ngc_objects = []

        for row in table:
            # Skip Messier objects (duplicates)
            # NGC objects that are also Messier usually have standard mapping, but simple check:
            # We will dedup later by position if needed, or just let them be.
            # Actually, let's keep them, or maybe filter known duplicates later.

            name = f'NGC {row[ngc_col]}'
            ra = float(row['_RAJ2000'])
            dec = float(row['_DEJ2000'])

            mag_val = 99.9
            if (
                mag_col in row.colnames
                and row[mag_col] is not None
                and str(row[mag_col]).strip() != ''
            ):
                mag_val = float(row[mag_col])

            otype = str(row[type_col])

            ngc_objects.append(
                {
                    'name': name,
                    'type': otype,
                    'ra': ra,
                    'dec': dec,
                    'magnitude': mag_val,
                    'catalog': 'NGC',
                }
            )

        print(f'Successfully fetched {len(ngc_objects)} NGC objects.')
        return ngc_objects

    except Exception as e:
        print(f'Failed to download NGC objects: {e}')
        return []


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
    ngc = download_ngc_objects(max_mag=8.0)  # Conservative limit for "Showpiece"

    final_list: list[dict[str, Any]] = list(messier)

    # Spatial-index deduplication: 1° grid avoids O(N×M) pairwise SkyCoord
    # separation calls.  With ~110 Messier objects spread across the sky, each
    # NGC object only checks the Messier objects in its own + adjacent cells
    # (typically 0-2 objects rather than all 110).
    messier_coords = [SkyCoord(m['ra'], m['dec'], unit='deg') for m in messier]
    grid = _build_spatial_index(messier, grid_size=1.0)

    separation_threshold_deg = 0.1  # 6 arcmin — same object, different catalog

    print('Deduplicating...')
    duplicates = 0
    for n in ngc:
        n_coord = SkyCoord(n['ra'], n['dec'], unit='deg')
        ra_bin = int(n['ra'] / 1.0)
        dec_bin = int(n['dec'] / 1.0)
        is_dup = False

        # Only check Messier objects in this cell + 8 neighbours
        for dra in (-1, 0, 1):
            for ddec in (-1, 0, 1):
                for idx in grid.get((ra_bin + dra, dec_bin + ddec), []):
                    if n_coord.separation(messier_coords[idx]).deg < separation_threshold_deg:
                        is_dup = True
                        break
                if is_dup:
                    break
            if is_dup:
                break

        if not is_dup:
            final_list.append(n)
        else:
            duplicates += 1

    print(f'Removed {duplicates} duplicates (NGC objects that are Messier objects).')
    print(f'Total objects: {len(final_list)}')

    # Save to file
    output_path = Path(__file__).resolve().parents[1] / 'src' / 'data' / 'objects.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open('w') as f:
        json.dump(final_list, f, indent=2)

    print(f'Saved to {output_path}')


if __name__ == '__main__':
    main()
