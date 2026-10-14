# Garmin IMG Parser

Python-библиотека для чтения файлов Garmin IMG — формата карт,
используемых GPS-навигаторами Garmin и программой BaseCamp/MapSource.

[English version](README.md)

## Возможности

- Чтение одиночных `.img` и контейнеров `gmapsupp.img` с несколькими картами
- Автоматическая расшифровка XOR; пропуск NT-карт
- Извлечение точек, линий, полигонов с координатами WGS84 и метками
- Полные словари типов Garmin (~500 записей)
- Экспорт в 5 форматов: MP (Polish Format), GeoJSON, GPX, CSV (только точки), Shapefile
- Полигонизация замкнутых boundary-линий в полигоны
- Дедупликация объектов по уровням детализации
- Пакетный экспорт всех карт контейнера в отдельные папки
- Опциональная разбивка шейпфайлов по типам (`export_by_types_shapefiles`)

## Установка

Обязательных зависимостей нет — просто скопируйте `garmin_img.py` в свой проект.

Для экспорта в Shapefile установите `pyshp`:

    pip install pyshp

Проверка:

    python -c "from garmin_img import open_img; print('OK')"

## Быстрый старт

### Одиночная карта

    from garmin_img import open_img

    img = open_img("map.img")
    print(img.summary())

    # Экспорт всех линий на самом детальном уровне
    img.export_shapefile("out/lines", kinds=('lines',), filter_level=0)

### Контейнер (gmapsupp.img)

    from garmin_img import open_img

    cont = open_img("gmapsupp.img")
    print(f"Карт: {len(cont)}")

    for r in cont.list_light():
        print(r['id'], r['name'])

    img = cont.find("38000035")
    img.export_mp("out.mp")

### Пакетный экспорт

    python extract_all_maps.py gmapsupp.img выходная_папка

## Открытие карт

`open_img(path)` сам определяет тип файла и возвращает:

- `GarminIMG` — для одиночной карты
- `GarminIMGContainer` — для контейнера с несколькими картами

    obj = open_img("file.img")
    if hasattr(obj, "submaps"):
        print("контейнер")
    else:
        print("одиночная карта")

Можно открыть явно:

    from garmin_img import GarminIMG, GarminIMGContainer

    img  = GarminIMG("file.img")
    cont = GarminIMGContainer("gmapsupp.img")

## Метаданные карты

Всё в `img.metadata`:

| Поле | Что |
|---|---|
| `name` | имя из шапки IMG |
| `submap_name` | имя из MPS (для подкарт контейнера) |
| `submap_id` | ID подкарты (например, `"38000035"`) |
| `map_id` | числовой ID карты |
| `codepage` | кодовая страница LBL (1251, 1252, 65001, ...) |
| `encoding` | кодировка LBL (6, 9, 10) |
| `north`, `east`, `south`, `west` | границы карты |
| `locked` | карта зашифрована? |
| `size_bytes` | размер файла |

    print(img.get_display_name())   # MPS → шапка IMG → имя файла
    print(img.summary())            # полный текстовый отчёт

## Чтение объектов

Три способа получить объекты:

| Способ | Когда использовать |
|---|---|
| `img.points / img.polylines / img.polygons` | кэшируется, читается один раз |
| `img.iter_points() / iter_polylines() / iter_polygons()` | ленивый, экономит память |
| `img.iter_all(kinds)` | сразу несколько видов |

Для больших карт (>10 000 объектов) — только `iter_*`:

    for p in img.iter_points():
        process(p)

Для повторного доступа — свойства `points`, `polylines`, `polygons`,
и очистка через `clear_cache()`:

    for p in img.points:
        process(p)
    img.clear_cache()

### Точка (Point)

    p.kind        # 'point'
    p.type        # int, 16-битный код типа (0x1500, 0x1E00, ...)
    p.subtype     # int или None
    p.label       # str, метка из LBL
    p.lat, p.lon  # координаты WGS84
    p.level       # уровень детализации
    p.type_name   # имя типа из словаря Garmin (свойство)

### Линия (Polyline)

    pl.type         # int, 8-битный код типа (0x05, 0x06, ...)
    pl.label        # str
    pl.level        # int
    pl.points       # список (lon, lat)
    pl.direction    # bool — односторонняя
    pl.in_net       # bool — есть данные в NET
    pl.type_name    # str
    pl.type_group   # 'road', 'water', 'boundary', ...

### Полигон (Polygon)

Те же поля, что у линии (`type`, `label`, `level`, `points`, `type_name`).

## Словари типов Garmin

    from garmin_img import (POINT_TYPES, POLYLINE_TYPES,
                            POLYGON_TYPES, POLYLINE_GROUPS)

    POINT_TYPES[0x1500]     # 'Minor country name'
    POLYLINE_TYPES[0x06]    # 'Residential street'
    POLYGON_TYPES[0x50]     # 'Forest'
    POLYLINE_GROUPS[0x06]   # 'road'

Безопасный поиск с fallback:

    from garmin_img import (guess_point_type, guess_line_type,
                            guess_polygon_type)

    guess_point_type(0x1500)   # 'Minor country name'
    guess_line_type(0xAA)      # 'Unknown line (0xAA)'

Размеры словарей: `POINT_TYPES` ~500, `POLYLINE_TYPES` 36,
`POLYGON_TYPES` 56, `POLYLINE_GROUPS` ~30.

## Свои имена типов

Можно зарегистрировать свои имена до открытия карты:

    from garmin_img import (register_point_type, register_line_type,
                            register_polygon_type, register_line_group)

    register_point_type(0x1F00, "Номер выдела")
    register_line_type(0x16, "Граница выдела", group="border")
    register_polygon_type(0x50, "Хвойный лес")
    register_line_group(0x1D, "boundary")

Или загрузить из текстового файла:

    [POINT]
    0x1F00 = Номер выдела
    0x1400 = Номер квартала

    [LINE]
    0x16 = Граница выдела @border
    0x1F = Река @water

    [POLYGON]
    0x50 = Хвойный лес

    from garmin_img import load_types_from_file
    load_types_from_file("my_types.txt", verbose=True)

Сохранить текущие типы:

    from garmin_img import save_types_to_file
    save_types_to_file("types.txt")

## Предикаты

17 функций для быстрой проверки типа:

    from garmin_img import (is_city_point, is_hw_exit_point,
                            is_height_point, is_feature_point,
                            has_address_point, is_navaid_point,
                            is_road_line, is_unpaved_road, is_roundabout,
                            is_height_line, is_background_polygon,
                            is_water_line, is_rail_line, is_border_line,
                            is_water_polygon, is_land_polygon)

    is_city_point(0x0400)   # True
    is_road_line(0x06)      # True
    is_water_line(0x1F)     # True
    is_border_line(0x1D)    # True

## Фильтры и выборки

### По типу

    img.points_by_type(0x1500)
    img.polylines_by_type(0x05, 0x06)
    img.polygons_by_type(0x50)

### По уровню

    img.polylines_by_level(0)

### По группе

    img.polylines_by_group("road")
    img.polylines_by_group("water")
    img.polylines_by_group("boundary")

### Универсальный filter

    img.filter(kind='line', group='road', level=0)
    img.filter(types={0x01, 0x02, 0x03})
    img.filter(kind='point', predicate=lambda o: is_city_point(o.type))

### Проверки и подсчёты

    img.has_type(0x06, kind='line')     # bool
    img.count_type(0x1500)              # int
    img.types_present()                 # {'point': {тип: количество, ...}, ...}

## Гео-запросы

### Что рядом с точкой

    for dist, obj in img.near(lat=51.05, lon=137.74,
                              radius_km=2, kind='point', limit=10):
        print(f"{dist:.3f} км {obj.label!r}")

### Поиск по метке

    img.search_labels("Ленина")                 # подстрока
    img.search_labels("река", regex=True, kind='line')
    img.search_labels("ОЗЕРО", ignore_case=True)

### Самые длинные объекты

    for length_m, pl in img.longest(n=20, kind='line', group='road'):
        print(f"{length_m/1000:8.2f} км {pl.label or '(без имени)'}")

### Суммарная длина

    img.total_length_m(group='road')    # метров
    img.total_length_m(group='water')

### Bounding box

    img.bbox_of(type=0x50)              # (min_lon, min_lat, max_lon, max_lat)
    img.bbox_of(kind='line', group='road')

## Экспорт

Поддерживается пять форматов.

### Polish Format (.mp) — для GPSMapEdit, cGPSmapper

    img.export_mp("out.mp")
    img.export_mp("out.mp", levels={0})              # только level 0
    img.export_mp("out.mp", levels={0, 1, 2})        # три уровня
    img.export_mp("out.mp", snap_to_grid=True)       # притянуть к сетке Garmin

`snap_to_grid=True` округляет координаты на сетку Garmin перед записью,
чтобы GPSMapEdit не сдвигал их при загрузке. Округление — round-half-
away-from-zero, корректно работает для южного полушария и западных долгот.

### GeoJSON — для QGIS, Leaflet, Mapbox

    img.export_geojson("out.geojson")

### GPX — для Garmin GPS, Strava, OSM

    img.export_gpx("out.gpx")

### CSV — только точки

    img.export_csv("points.csv")

### Shapefile — требует `pyshp`

    # Все линии
    img.export_shapefile("lines", kinds=('lines',))

    # Только кварталы (тип 0x05) на level 0
    img.export_shapefile("quarters", kinds=('lines',),
                         filter_types={0x05}, filter_level=0)

    # Все дороги на level 0
    img.export_shapefile("roads", kinds=('lines',),
                         filter_group="road", filter_level=0)

    # Точки типа 0x1E00
    img.export_shapefile("numbers", kinds=('points',),
                         filter_types={0x1E00})

Создаёт 5 файлов: `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`.

Поля в DBF: `ID`, `TYPE_HEX`, `TYPE_NAME`, `TYPE_GROUP`, `ZOOM`,
`N_POINTS`, `LENGTH_M`, `ONEWAY`, `ROUTABLE`, `SUBTYPE`,
`MINLON`/`MINLAT`/`MAXLON`/`MAXLAT`, `LABEL`.

### Шорткаты

    img.export_roads_shapefile("roads")             # группа road
    img.export_roads_shapefile("roads", level=0)    # только level 0
    img.export_water_shapefile("rivers")            # группа water
    img.extract_shape(0x16, "boundaries", kind='line')   # один тип

### Все три слоя одной командой

    result = img.export_all_shapefiles("out_dir", level=0)
    # → out_dir/points.shp, lines.shp, polygons.shp
    # результат: {'points': N, 'lines': N, 'polygons': N}

### Разбивка по типам

    img.export_by_types_shapefiles("out_types", level=0)
    # → out_types/points_1400.shp, lines_06.shp, polygons_50.shp

Имена файлов содержат hex-код типа. Удобно для QGIS: вместо одного
гигантского `lines.shp` — много маленьких файлов, которые можно
открывать по отдельности.

## Полигонизация замкнутых линий

Полезно для лесных карт, где кварталы хранятся как замкнутые
boundary-линии, а не как полигоны.

    n_poly, n_open = img.polygonize_shapefile(
        "quarters",
        types=(0x1D,),      # какие типы линий считать полигонами
        tolerance=1e-6,     # допуск замыкания
        filter_level=None)  # уровень или None для всех
    print(f"Полигонов: {n_poly}, отброшено незамкнутых: {n_open}")

Линия считается замкнутой, если её первая и последняя точки совпадают
в пределах `tolerance`. Замкнутые превращаются в полигоны, открытые
отбрасываются.

## Дедупликация

Один объект может встречаться на нескольких уровнях. Обычный
`export_shapefile` создаст дубликаты.

    img.export_dedup_shapefile("points_unique", kind='points')
    # kind: 'points' | 'lines' | 'polygons'

Дополнительные поля в DBF: `MIN_LEVEL` (самый детальный уровень),
`N_LEVELS` (число уровней, где встречается объект).

## Контейнер (gmapsupp.img)

    cont = open_img("gmapsupp.img")

    len(cont)             # сколько карт
    for img in cont:      # перебор
        print(img.submap_id, img.get_display_name())
    cont[0]               # по индексу
    cont.submaps          # список

    # Быстрый список
    for r in cont.list_light():
        print(r['id'], r['kind'], r['name'], r['pid'], r['fid'])

    # Полный список с подсчётом объектов
    for r in cont.list_submaps():
        print(r['id'], r['name'], r['points'],
              r['polylines'], r['polygons'])

    # Найти конкретную карту
    img = cont.find("38000035")
    if img:
        print(img.summary())

    # Статистика контейнера
    print(cont.n_nt_skipped)        # пропущено NT-карт
    print(cont.n_service_skipped)   # пропущено служебных субфайлов

## Пакетный экспорт

### Из командной строки

    python extract_all_maps.py gmapsupp.img выходная_папка

Создаёт одну папку на карту (имя из таблицы MPS), в каждой — три
шейпфайла: точки, линии, полигоны (слой пропускается, если объектов
этого типа нет). Например:

    выходная_папка/
      Balaganskoe/
        points.shp   (+ .shx, .dbf, .prj, .cpg)
        lines.shp    (+ .shx, .dbf, .prj, .cpg)
        polygons.shp (+ .shx, .dbf, .prj, .cpg)
      Drugoe/
        points.shp
        lines.shp

### Из Python, с разбивкой по типам

    cont = open_img("gmapsupp.img")
    cont.extract_all_by_name("extracted", level=0, by_types=True)

`by_types=True` (по умолчанию) — файлы по типам внутри каждой папки:
`points_1400.shp`, `lines_06.shp`, `polygons_50.shp`.
`by_types=False` — три общих файла: `points.shp`, `lines.shp`,
`polygons.shp`.

В каждую папку пишется маркер `.done` — при перезапуске готовые
папки пропускаются.

## Командная строка

| Команда | Что делает |
|---|---|
| `python garmin_img.py info file.img` | сводка по карте |
| `python garmin_img.py list gmapsupp.img` | список карт контейнера |
| `python garmin_img.py export file.img out_prefix` | экспорт одиночной карты в MP/GeoJSON/SHP |
| `python garmin_img.py extract gmapsupp.img out_dir` | экспорт линий контейнера |
| `python garmin_img.py extract-by-name gmapsupp.img out_dir [level]` | пакетный экспорт по именам карт |

Пример:

    python garmin_img.py extract-by-name gmapsupp.img extracted 0

## Что НЕ поддерживается

- **NT-формат** (City Navigator, современные Topo-карты)
- Роутинг (NET/NOD) — флаги читаются, граф не строится
- Высоты (DEM-субфайл)
- Запись IMG — библиотека только для чтения
- Бинарные TYP-файлы (только текстовые через `load_types_from_file`)
- Extended-секции RGN (типы 0x100+)

## Сетка Garmin и MP-формат

Координаты в IMG всегда на сетке Garmin. У каждого уровня свой шаг:

    step = 360 / 2^bits_per_coord

Для 24 бит шаг равен 0.0000214577° (~2.4 м на экваторе). Все
координаты объектов в IMG кратны этому шагу.

При экспорте в MP библиотека по умолчанию пишет координаты с
округлением до 5 знаков — это грубее сетки Garmin. С
`snap_to_grid=True` координаты округляются на точную сетку Garmin,
и GPSMapEdit не будет сдвигать их при загрузке.

Остальные форматы (Shapefile / GeoJSON / GPX / CSV) сохраняют
полную точность float64, сетка не теряется.

## Зависимости

- **Обязательные:** нет
- **Опциональные:** `pyshp` — только для экспорта в Shapefile

## Лицензия

MIT — см. файл [LICENSE](LICENSE).

## Благодарности

Библиотека создана на основе работы:

- **John Mechalas** — «Garmin's IMG File Format» (2005)
- **N. Willink** — «Exploring Garmin's IMG Format» (2015)
- **Patrick Valsecchi** — JGarminImgParser (Java-библиотека)
- **Константин Галичский** — GPSMapEdit
  ◦ словари типов Garmin (POINT_TYPES, POLYLINE_TYPES, POLYGON_TYPES);
  ◦ детальная спецификация структур TRE/RGN/LBL/NET/NOD в C++-коде;
  ◦ алгоритм декодирования 6-битного LBL;
  ◦ логика парсинга extended-секций RGN.
- Проект **imgdecode**

## Обратная связь

Если нашли карту, которая не читается или читается некорректно,
или хотите внести вклад — создайте Issue или пришлите Pull Request.
Особенно интересны:

- NT-карты (для возможной будущей поддержки)
- Морские карты BlueChart
- Топографические карты с DEM
- Карты с extended-типами (0x100+)
- Любые карты, где получаются неверные координаты или пустые метки
