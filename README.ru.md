# Garmin IMG Parser

Python-библиотека для чтения файлов Garmin IMG — формата карт, 
используемых GPS-навигаторами Garmin и программой BaseCamp/MapSource.

[English version](README.md)

## Возможности

- Чтение одиночных `.img` и контейнеров `gmapsupp.img` с несколькими картами
- Автоматическая расшифровка XOR; пропуск NT-карт
- Извлечение точек, линий, полигонов с координатами WGS84 и метками
- Полные словари типов Garmin (~500 записей)
- Экспорт в 5 форматов: MP (Polish Format), GeoJSON, GPX, CSV, Shapefile
- Полигонизация замкнутых boundary-линий в полигоны
- Дедупликация объектов по уровням детализации
- Пакетный экспорт всех карт контейнера в отдельные папки

## Установка

Обязательных зависимостей нет — просто скопируйте `garmin_img.py` в свой проект.

Для экспорта в Shapefile установите `pyshp`:

    pip install pyshp

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

## Что можно извлечь

Для каждого объекта — точки, линии, полигона — доступно:

    p.type          # 0x1500 (числовой код типа)
    p.type_name     # "Minor country name" (из словаря Garmin)
    p.label         # текст метки из субфайла LBL
    p.lat, p.lon    # координаты WGS84
    p.level         # уровень детализации

Для линий и полигонов:

    pl.points       # [(lon, lat), (lon, lat), ...]
    pl.type_group   # "road", "water", "boundary", ...

## Пакетный экспорт

    python extract_all_maps.py gmapsupp.img выходная_папка

Создаёт одну папку на карту (имя из таблицы MPS) с шейпфайлами, 
разделёнными по типам объектов — например:

    выходная_папка/
      Balaganskoe/
        points_Major_country_name.shp
        points_State_province_region_name.shp
        lines_Residential_street.shp
        lines_Collector_road.shp

## Свои имена типов

Можно зарегистрировать свои имена для типов до открытия карты:

    from garmin_img import register_line_type, register_point_type

    register_point_type(0x1E00, "Номер выдела")
    register_line_type(0x06, "Граница выдела", group="boundary")

Или загрузить из текстового файла:

    from garmin_img import load_types_from_file
    load_types_from_file("my_types.txt")

## Что НЕ поддерживается

- **NT-формат** (City Navigator, современные Topo-карты)
- Роутинг (NET/NOD) — флаги читаются, граф не строится
- Высоты (DEM-субфайл)
- Запись IMG — библиотека только для чтения
- Бинарные TYP-файлы (только текстовые через `load_types_from_file`)
- Extended-секции RGN (типы 0x100+)

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
- **Константин Галицкий** — GPSMapEdit
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
