"""Invented values with source-shaped schemas. No upstream records."""

from .sources import FORECAST_UNITS, LODGE, NELSON, utc

NOW = utc("2026-01-15T18:00:00Z")


def forecast_fixture(point=LODGE):
    anchor = int(NOW.timestamp())
    return {
        **point, "utc_offset_seconds": 0, "generationtime_ms": 1.2,
        "hourly_units": {"time": "unixtime", **FORECAST_UNITS},
        "hourly": {
            "time": [anchor + hour * 3600 for hour in range(169)],
            "temperature_2m": [-4.5] * 169,
            "snowfall": [0.0] * 31 + [0.9] * 24 + [0.0] * 114,
            "wind_speed_10m": [12.0] * 169,
            "freezing_level_height": [1200] * 169,
        },
    }


def valley_fixture():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "id": "synthetic-nelson-001",
            "geometry": {"type": "Point", "coordinates": [NELSON["longitude"], NELSON["latitude"]]},
            "properties": {
                "msc_id-value": "1145M29", "wmo_synop_id-value": "71776",
                "obs_date_tm": "2026-01-15T17:00:00Z",
                "air_temp": -6.1, "air_temp-uom": "°C", "air_temp-qa": 100,
            },
        }],
    }


def report_fixture():
    return {
        "updated_at": "2026-01-15T08:30:00-08:00", "unit": "cm",
        "overnight": 6, "24h": 9, "48h": 12, "3d": 16, "7d": 27,
        "season": 123, "base_depth": 77,
    }


def mountain_fixture(station):
    return {
        "station": station, "valid_at": "2026-01-15T09:00:00-08:00",
        "temperature": -3.1, "temperature_unit": "°C",
        "wind_speed": 9, "wind_unit": "km/h", "wind_direction": 240,
    }
