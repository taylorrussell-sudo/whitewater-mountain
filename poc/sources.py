"""Source contracts for the isolated weather proof of concept."""

import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

UTC = timezone.utc
HOUR = timedelta(hours=1)
NELSON = {"latitude": 49.491389, "longitude": -117.305278, "elevation": 534.9}
# Approximate forecast target. The resort does not publish sensor coordinates.
LODGE = {"latitude": 49.443, "longitude": -117.146, "elevation": 1630}
MODEL = "gem_global"
FORECAST_UNITS = {
    "temperature_2m": "°C", "snowfall": "cm", "wind_speed_10m": "km/h",
    "freezing_level_height": "m",
}
FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
VALLEY_ENDPOINT = "https://api.weather.gc.ca/collections/swob-realtime/items"
WHITEWATER_CONDITIONS = "https://whitewatermountainresort.com/conditions/"
WHITEWATER_ADVANCED = "https://whitewatermountainresort.com/advanced-weather/"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc(value):
    require(isinstance(value, str), "Expected an ISO 8601 timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    require(parsed.utcoffset() is not None, "An explicit UTC offset is required")
    return parsed.astimezone(UTC)


def number(value, minimum=None, maximum=None):
    require(type(value) in (int, float) and math.isfinite(value),
            "Expected a finite number")
    require(minimum is None or value >= minimum, "Value below allowed range")
    require(maximum is None or value <= maximum, "Value above allowed range")
    return value


def hour_floor(value):
    return value.replace(minute=0, second=0, microsecond=0)


def forecast_url(point):
    return FORECAST_ENDPOINT + "?" + urlencode({
        **point, "models": MODEL, "hourly": ",".join(FORECAST_UNITS),
        "timezone": "GMT", "timeformat": "unixtime", "forecast_hours": 169,
        "temperature_unit": "celsius", "wind_speed_unit": "kmh",
    })


def valley_url(now):
    return VALLEY_ENDPOINT + "?" + urlencode({
        "f": "json", "msc_id-value": "1145M29", "limit": 6,
        "datetime": f"{(now - 6 * HOUR).isoformat()}/{now.isoformat()}",
        "sortby": "-date_tm-value",
    })


def normalize_forecast(payload, point):
    require(type(payload["utc_offset_seconds"]) is int
            and payload["utc_offset_seconds"] == 0, "Expected GMT")
    units = payload["hourly_units"]
    require(units["time"] == "unixtime", "Expected Unix seconds")
    require(all(units.get(k) == unit for k, unit in FORECAST_UNITS.items()),
            "Unexpected forecast units")
    hourly = payload["hourly"]
    times = hourly["time"]
    require(isinstance(times, list) and times, "No forecast times")
    for i, value in enumerate(times):
        require(type(value) is int and value % 3600 == 0, "Invalid UTC hour")
        require(i == 0 or value > times[i - 1], "Unordered or duplicate forecast hours")
    for key in FORECAST_UNITS:
        values = hourly[key]
        require(isinstance(values, list) and len(values) == len(times),
                f"Forecast array length differs for {key}")
        for value in values:
            if value is not None:
                number(value, 0 if key in ("snowfall", "wind_speed_10m") else None)
    grid = {
        "latitude": number(payload["latitude"], -90, 90),
        "longitude": number(payload["longitude"], -180, 180),
        "elevation": number(payload["elevation"]),
    }
    require(grid["elevation"] == point["elevation"], "Unexpected target elevation")
    return {
        "kind": "forecast", "model": MODEL, "model_issued_at": None,
        "endpoint": FORECAST_ENDPOINT, "requested_point": point, "returned_point": grid,
        "units": FORECAST_UNITS, "times": times,
        "values": {key: hourly[key] for key in FORECAST_UNITS},
    }


def snowfall_windows(forecast, now):
    """Sum preceding-hour snowfall bins from the next whole UTC hour boundary."""
    boundary = hour_floor(now)
    if now != boundary:
        boundary += HOUR
    start = int(boundary.timestamp())
    snow = dict(zip(forecast["times"], forecast["values"]["snowfall"]))

    def total(start_hour, length):
        values = [snow.get(start + i * 3600)
                  for i in range(start_hour + 1, start_hour + length + 1)]
        return None if None in values else math.fsum(values)

    windows = [total(offset, 24) for offset in range(49)]
    # An unknown candidate can exceed any known candidate, so suppress the maximum.
    peak = None
    if None not in windows:
        index = windows.index(max(windows))
        peak = {"cm": windows[index], "start": start + index * 3600,
                "end": start + (index + 24) * 3600}
    return {"start": start, "totals_cm": {hours: total(0, hours) for hours in (24, 48, 72)},
            "max_rolling_24h": peak}


def normalize_valley(payload):
    require(payload["type"] == "FeatureCollection", "Expected a GeoJSON FeatureCollection")
    features = payload["features"]
    require(isinstance(features, list), "Expected a feature list")
    readings = []
    for feature in features:
        p = feature["properties"]
        require(p["msc_id-value"] == "1145M29" and str(p["wmo_synop_id-value"]) == "71776",
                "Unexpected SWOB station")
        require(feature["geometry"]["type"] == "Point", "Expected SWOB point")
        lon, lat, *height = feature["geometry"]["coordinates"]
        require(len(height) <= 1, "Unexpected SWOB coordinate dimensions")
        require(abs(number(lon) - NELSON["longitude"]) < 0.01
                and abs(number(lat) - NELSON["latitude"]) < 0.01,
                "Unexpected Nelson station position")
        elevation = number(height[0]) if height else None
        require(elevation is None or abs(elevation - NELSON["elevation"]) <= 5,
                "Unexpected Nelson station elevation")
        if p.get("air_temp") is None or p.get("air_temp-qa") != 100:
            continue
        require(p["air_temp-uom"] == "°C", "Unexpected SWOB air temperature unit")
        readings.append({
            "valid_at": utc(p["obs_date_tm"]).isoformat(),
            "temperature_c": number(p["air_temp"], -90, 60),
            "source_id": feature["id"],
            "processed_at": (utc(p["processed_date_tm"]).isoformat()
                             if p.get("processed_date_tm") else None),
            "latitude": lat, "longitude": lon, "elevation": elevation,
            "provider": p.get("data_pvdr-value"),
            "attribution": p.get("data_attrib_not-value"),
        })
    return {
        "kind": "measured", "station": "Nelson CS", "station_reference": NELSON,
        "endpoint": VALLEY_ENDPOINT,
        "readings": sorted(readings, key=lambda row: (row["valid_at"], row["source_id"])),
    }


def normalize_resort_report(report):
    """Synthetic contract only, with explicit offset supplied by the fixture."""
    fields = ("overnight", "24h", "48h", "3d", "7d", "season", "base_depth")
    require(report["unit"] == "cm", "Unexpected resort snow unit")
    return {
        "kind": "reported", "endpoint": WHITEWATER_CONDITIONS,
        "station": "Summit snow plot", "elevation": 1950,
        "report_updated_at": utc(report["updated_at"]).isoformat(),
        "observed_at": None, "unit": "cm",
        "values": {key: number(report[key], 0) if report.get(key) is not None else None
                   for key in fields},
    }


def normalize_resort_weather(row):
    """Synthetic hourly row only. Page clock and sensor metadata need confirmation."""
    elevations = {"Whitewater Base": 1630, "Summit Top": 2002}
    require(row["temperature_unit"] == "°C" and row["wind_unit"] == "km/h",
            "Unexpected resort weather units")
    return {
        "kind": "measured", "endpoint": WHITEWATER_ADVANCED,
        "station": row["station"], "elevation": elevations[row["station"]],
        "valid_at": utc(row["valid_at"]).isoformat(),
        "temperature_c": number(row["temperature"], -90, 60),
        "wind_kmh": number(row["wind_speed"], 0),
        "wind_from_degrees": number(row["wind_direction"], 0, 360) % 360,
    }
