"""
Exports ONE map to shapefiles (points/lines/polygons).
Works both with a single .img and with a submap from a container.

Usage:
    python extract_one_map.py <file.img> [out_dir] [submap_id]
"""
import os
import sys
import time
from garmin_img import open_img


def extract(img, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()

    # 1. Points
    n_pts = 0
    try:
        n_pts = sum(1 for _ in img.iter_points())
        if n_pts > 0:
            img.export_shapefile(
                os.path.join(out_dir, "points"), kinds=('points',))
            print(f"  points:    {n_pts:>7}")
        else:
            print(f"  points:    0 (skipped)")
    except Exception as e:
        print(f"  points:    ERROR: {e}")

    # 2. Lines
    n_lns = 0
    try:
        n_lns = sum(1 for _ in img.iter_polylines())
        if n_lns > 0:
            img.export_shapefile(
                os.path.join(out_dir, "lines"), kinds=('lines',))
            print(f"  lines:     {n_lns:>7}")
        else:
            print(f"  lines:     0 (skipped)")
    except Exception as e:
        print(f"  lines:     ERROR: {e}")

    # 3. Polygons
    n_pgn = 0
    try:
        n_pgn = sum(1 for _ in img.iter_polygons())
        if n_pgn > 0:
            img.export_shapefile(
                os.path.join(out_dir, "polygons"), kinds=('polygons',))
            print(f"  polygons:  {n_pgn:>7}")
        else:
            print(f"  polygons:  0 (skipped)")
    except Exception as e:
        print(f"  polygons:  ERROR: {e}")

    print(f"\nDone in {time.time()-t0:.1f} sec -> {out_dir}/")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted_one"
    submap_id = sys.argv[3] if len(sys.argv) > 3 else None

    obj = open_img(path)

    if hasattr(obj, "submaps"):
        # This is a container
        if submap_id:
            img = obj.find(submap_id)
            if img is None:
                print(f"Submap {submap_id} not found")
                sys.exit(1)
        else:
            print(f"This is a container. Specify submap_id as the third argument.")
            print(f"Available maps:")
            for r in obj.list_light():
                print(f"  {r['id']:<10} {r['name']}")
            sys.exit(1)
    else:
        # Single map
        img = obj

    print(f"Map: {img.metadata.name!r}")
    print(f"  map_id:  {img.metadata.map_id}")
    print(f"  bounds:  N={img.metadata.north:.4f} "
          f"S={img.metadata.south:.4f} "
          f"W={img.metadata.west:.4f} "
          f"E={img.metadata.east:.4f}")
    print()
    extract(img, out_dir)


if __name__ == "__main__":
    main()