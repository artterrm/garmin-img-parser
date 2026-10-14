"""
Извлекает все классические карты из контейнера gmapsupp.img
в отдельные папки (по имени карты), каждая — с шейпфайлами
для точек, линий и полигонов (если есть).

Папка для каждой карты: <out_dir>/<safe_name>/
Файлы: points.shp, lines.shp, polygons.shp (+ .shx, .dbf, .prj, .cpg)
"""
import os
import sys
import time
import logging
from garmin_img import open_img, GarminImgError

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def safe_name(name, sid):
    """Делает безопасное имя папки из имени карты или ID."""
    base = name or sid or "unnamed"
    base = base.strip() or sid
    bad = '<>:"/\\|?*'
    for ch in bad:
        base = base.replace(ch, "_")
    return base[:80] or sid


def extract_one(img, out_dir, sub_dir):
    """Экспортирует одну карту — три слоя."""
    folder = os.path.join(out_dir, sub_dir)
    os.makedirs(folder, exist_ok=True)

    results = {}

    # 1. Точки
    n_points = 0
    try:
        n_points = sum(1 for _ in img.iter_points())
        if n_points > 0:
            img.export_shapefile(
                os.path.join(folder, "points"),
                kinds=('points',))
            results['points'] = n_points
    except Exception as e:
        logging.warning("  points: ошибка %s", e)
        results['points'] = f"ERR: {e}"

    # 2. Линии
    n_lines = 0
    try:
        n_lines = sum(1 for _ in img.iter_polylines())
        if n_lines > 0:
            img.export_shapefile(
                os.path.join(folder, "lines"),
                kinds=('lines',))
            results['lines'] = n_lines
    except Exception as e:
        logging.warning("  lines: ошибка %s", e)
        results['lines'] = f"ERR: {e}"

    # 3. Полигоны (если есть)
    n_poly = 0
    try:
        n_poly = sum(1 for _ in img.iter_polygons())
        if n_poly > 0:
            img.export_shapefile(
                os.path.join(folder, "polygons"),
                kinds=('polygons',))
            results['polygons'] = n_poly
    except Exception as e:
        logging.warning("  polygons: ошибка %s", e)
        results['polygons'] = f"ERR: {e}"

    return results


def main():
    if len(sys.argv) < 2:
        print("Использование: python extract_all_maps.py <gmapsupp.img> [out_dir]")
        sys.exit(1)

    path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted"
    os.makedirs(out_dir, exist_ok=True)

    t0 = time.time()
    print(f"Открываю: {path}")
    cont = open_img(path)

    if not hasattr(cont, "submaps"):
        print("Это одиночная карта, а не контейнер.")
        print("Используйте open_img(...).export_shapefile(...)")
        sys.exit(1)

    n_maps = len(cont)
    print(f"Классических карт: {n_maps}")
    print(f"Папка назначения: {os.path.abspath(out_dir)}")
    print(f"Пропущено NT:      {cont.n_nt_skipped}")
    print()
    print(f"{'#':>3}  {'Карта':<38}  {'Точки':>8}  {'Линии':>9}  {'Полигоны':>9}  {'Папка'}")
    print("-" * 110)

    total = {'points': 0, 'lines': 0, 'polygons': 0}
    errors = []

    for i, img in enumerate(cont, 1):
        sid = img.submap_id or f"sub_{img.metadata.map_id}"
        # Имя из MPS уже в metadata.name (после патча)
        name = img.metadata.name or sid
        folder_name = safe_name(name, sid)

        # Уникализируем имя, если есть коллизия
        base = folder_name
        k = 1
        while os.path.exists(os.path.join(out_dir, folder_name)) \
                and os.path.exists(os.path.join(out_dir, folder_name, ".done")):
            folder_name = f"{base}_{k}"
            k += 1

        try:
            res = extract_one(img, out_dir, folder_name)
            # Маркер завершения
            with open(os.path.join(out_dir, folder_name, ".done"), "w") as f:
                f.write(f"submap_id={sid}\nname={name}\n")

            n_p = res.get('points', 0) if isinstance(res.get('points'), int) else 0
            n_l = res.get('lines', 0) if isinstance(res.get('lines'), int) else 0
            n_g = res.get('polygons', 0) if isinstance(res.get('polygons'), int) else 0
            total['points']   += n_p
            total['lines']    += n_l
            total['polygons'] += n_g

            print(f"{i:>3}  {sid:<10} {name:<27}  "
                  f"{n_p:>8}  {n_l:>9}  {n_g:>9}  {folder_name}/")
        except Exception as e:
            errors.append((sid, name, str(e)))
            print(f"{i:>3}  {sid:<10} {name:<27}  ОШИБКА: {e}")
        finally:
            img.clear_cache()

    elapsed = time.time() - t0
    print()
    print("=" * 70)
    print(f"Готово за {elapsed:.1f} сек ({elapsed/60:.1f} мин)")
    print(f"Всего точек:    {total['points']:,}")
    print(f"Всего линий:    {total['lines']:,}")
    print(f"Всего полигонов: {total['polygons']:,}")
    print(f"Ошибок:          {len(errors)}")
    if errors:
        for sid, name, err in errors:
            print(f"  {sid} ({name}): {err}")


if __name__ == "__main__":
    main()