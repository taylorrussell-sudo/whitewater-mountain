"""Fixed upstream contracts and normalization for each weather product."""

from dataclasses import dataclass
from urllib.parse import urlencode

from poc.sources import (
    FORECAST_ENDPOINT, LODGE, NELSON, VALLEY_ENDPOINT, WHITEWATER_ADVANCED, WHITEWATER_CONDITIONS,
    normalize_valley, number, require, utc, valley_url,
)

from . import whitewater

FORECAST_FIELDS = {"temperature_2m": "°C", "snowfall": "cm", "wind_speed_10m": "km/h"}
# Fixed adjacent GFS pressure levels. Skipping a level would bridge an unknown layer.
LEVELS = (*range(1000, 699, -25), 650, 600, 550, 500)
PROFILE_FIELDS = {
    f"{field}_{level}hPa": unit
    for level in LEVELS
    for field, unit in (("temperature", "°C"), ("geopotential_height", "m"))
}
POINTS = {"lodge": LODGE, "nelson": NELSON}
OPEN_METEO_LICENCE = "https://open-meteo.com/en/licence"
MSC_LICENCE = "https://eccc-msc.github.io/open-data/licence/readme_en/"


def hourly_url(model, fields, hours, points, elevation, **options):
    return FORECAST_ENDPOINT + "?" + urlencode({
        "models": model, "hourly": ",".join(fields), "forecast_hours": hours,
        "latitude": ",".join(str(p["latitude"]) for p in points),
        "longitude": ",".join(str(p["longitude"]) for p in points),
        "elevation": elevation, "timezone": "GMT", "timeformat": "unixtime",
        "temperature_unit": "celsius", "wind_speed_unit": "kmh", **options,
    })


def hourly(payload, fields, limit, now):
    require(type(payload["utc_offset_seconds"]) is int and payload["utc_offset_seconds"] == 0,
            "Expected UTC")
    units = payload["hourly_units"]
    columns = payload["hourly"]
    times = columns["time"]
    require(units.get("time") == "unixtime" and isinstance(times, list)
            and 0 < len(times) <= limit, "Invalid hourly time axis")
    anchor = int(now.timestamp()) // 3600 * 3600
    require(all(type(t) is int and t % 3600 == 0 for t in times)
            and all(b > a for a, b in zip(times, times[1:]))
            and anchor - 3600 <= times[0] <= anchor + 3600
            and times[-1] <= anchor + limit * 3600, "Unexpected UTC forecast window")
    values = {}
    for name, unit in fields.items():
        if name not in columns and name not in units:
            values[name] = [None] * len(times)
            continue
        # Open-Meteo documents geopotential metres as 'meter' and serves 'm'.
        allowed = ("m", "meter") if unit == "m" else (unit,)
        data = columns[name]
        require(units.get(name) in allowed and isinstance(data, list) and len(data) == len(times),
                "Unexpected hourly units or column length")
        minimum, maximum = {"°C": (-150, 70), "cm": (0, 500), "km/h": (0, 600),
                            "m": (-1000, 10000)}[unit]
        values[name] = [None if value is None else number(value, minimum, maximum) for value in data]
    return times, values


def returned_point(payload, point, tolerance, downscaled):
    lat = number(payload["latitude"], -90, 90)
    lon = number(payload["longitude"], -180, 180)
    elevation = number(payload["elevation"], -500, 9000)
    require(abs(lat - point["latitude"]) <= tolerance
            and abs(lon - point["longitude"]) <= tolerance, "Unexpected forecast location")
    if downscaled:
        require(abs(elevation - point["elevation"]) <= 0.2, "Unexpected downscaling elevation")
    return {"latitude": lat, "longitude": lon, "elevation": elevation}


@dataclass(frozen=True)
class Source:
    key: str
    label: str
    kind: str
    role: str
    provider: str
    credit: str
    link: str
    licence: str | None
    interval: int
    fresh_for: int

    def metadata(self):
        return {key: getattr(self, key) for key in ("label", "kind", "role", "credit", "link", "licence")}


@dataclass(frozen=True)
class Forecast(Source):
    model: str
    grid_km: float
    hours: int

    def url(self, now):
        elevation = ",".join(str(point["elevation"]) for point in POINTS.values())
        return hourly_url(self.model, FORECAST_FIELDS, self.hours, POINTS.values(), elevation)

    def normalize(self, payload, now):
        require(isinstance(payload, list) and len(payload) == len(POINTS), "Expected two forecast points")
        points = {}
        for (name, point), row in zip(POINTS.items(), payload):
            returned = returned_point(row, point, 0.25, downscaled=True)
            times, values = hourly(row, FORECAST_FIELDS, self.hours, now)
            points[name] = {"requested_point": point, "returned_point": returned,
                            "times": times, "values": values}
        current_hour = int(now.timestamp()) // 3600 * 3600
        if not any(t >= current_hour and value is not None for point in points.values()
                   for series in point["values"].values() for t, value in zip(point["times"], series)):
            return None
        return {"model": self.model, "model_grid_km": self.grid_km, "model_issued_at": None,
                "units": FORECAST_FIELDS, "points": points}


def crossings(levels, ground):
    """Keep every bracketed zero crossing and exact zero layer in height order."""
    above = [sample if sample[0] is not None and sample[0] > ground and sample[1] is not None
             else None for sample in levels]
    present = [sample for sample in above if sample is not None]
    if any(b[0] <= a[0] for a, b in zip(present, present[1:])):
        return None
    pairs = list(zip(above, above[1:]))
    if not any(a is not None and b is not None for a, b in pairs):
        return None
    result = []
    previous = None
    for sample in above:
        if sample is not None:
            z, t = sample
            if t == 0:
                if previous is not None and previous[1] == 0:
                    result[-1]["upper_m"] = z
                else:
                    result.append({"lower_m": z, "upper_m": z, "method": "sampled_zero"})
            elif previous is not None and previous[1] * t < 0:
                z0, t0 = previous
                root = z0 + (z - z0) * (-t0) / (t - t0)
                result.append({"lower_m": root, "upper_m": root, "method": "linear_bracket"})
        previous = sample
    return result


class FreezingProfile(Source):
    model = "gfs025"
    hours = 72

    def url(self, now):
        return hourly_url(self.model, PROFILE_FIELDS, self.hours, (LODGE,), "nan",
                          cell_selection="nearest")

    def normalize(self, payload, now):
        point = returned_point(payload, LODGE, 0.3, downscaled=False)
        times, columns = hourly(payload, PROFILE_FIELDS, self.hours, now)
        records = []
        for i in range(len(times)):
            levels = [(columns[f"geopotential_height_{p}hPa"][i],
                       columns[f"temperature_{p}hPa"][i]) for p in LEVELS]
            records.append(crossings(levels, point["elevation"]))
        current_hour = int(now.timestamp()) // 3600 * 3600
        if not any(t >= current_hour and record is not None for t, record in zip(times, records)):
            return None
        return {"model": self.model, "model_grid_km": 25, "model_issued_at": None,
                "requested_coordinates": {k: LODGE[k] for k in ("longitude", "latitude")},
                "returned_grid_point": point, "height_reference": "geopotential metres above sea level",
                "pressure_levels_hpa": LEVELS, "times": times, "crossings": records}


class Valley(Source):
    def metadata(self):
        return {**super().metadata(), "station": {"name": "Nelson CS", "climate_id": "1145M29",
                "wmo_id": "71776", "transport_canada_id": "WNM", "reference_point": NELSON},
                "units": {"temperature_c": "°C"}}

    def url(self, now):
        return valley_url(now.replace(microsecond=0))

    def normalize(self, payload, now):
        require(isinstance(payload["features"], list) and len(payload["features"]) <= 6,
                "Expected bounded SWOB response")
        normalized = normalize_valley(payload)
        for row in normalized["readings"]:
            require(isinstance(row["source_id"], str) and row["source_id"], "Missing feature ID")
            for field in ("provider", "attribution"):
                require(row[field] is None or isinstance(row[field], str), "Invalid attribution")
        return [row for row in normalized["readings"]
                if 0 <= (now - utc(row["valid_at"])).total_seconds() <= 6 * 3600] or None


class ResortSnow(Source):
    def url(self, now):
        return self.link

    def normalize(self, payload, now):
        return whitewater.parse_report(payload, now)


class ResortWeather(Source):
    def url(self, now):
        return self.link

    def normalize(self, payload, now):
        return whitewater.parse_weather(payload, now)


IFS = Forecast("ifs", "ECMWF IFS HRES 9 km", "forecast", "primary_extended", "open-meteo",
               "Open-Meteo / ECMWF", "https://open-meteo.com/en/docs/ecmwf-api",
               OPEN_METEO_LICENCE, 3 * 3600, 9 * 3600, "ecmwf_ifs", 9, 170)
HRDPS = Forecast("hrdps", "Canadian HRDPS Continental 2.5 km", "forecast", "short_range_guidance",
                 "open-meteo", "Open-Meteo / Environment and Climate Change Canada",
                 "https://open-meteo.com/en/docs/gem-api", OPEN_METEO_LICENCE,
                 3 * 3600, 9 * 3600, "gem_hrdps_continental", 2.5, 48)
NELSON_CS = Valley("nelson_cs", "Environment Canada Nelson CS", "measured", "valley_temperature",
                   "eccc", "Environment and Climate Change Canada", VALLEY_ENDPOINT,
                   MSC_LICENCE, 3600, 2 * 3600)
FREEZING = FreezingProfile("freezing_profile", "NOAA GFS 0.25° pressure profile", "derived",
                           "freezing_level_guidance", "open-meteo", "Open-Meteo / NOAA NCEP",
                           "https://open-meteo.com/en/docs/gfs-api", OPEN_METEO_LICENCE,
                           6 * 3600, 12 * 3600)
RESORT_SNOW = ResortSnow("whitewater", "Whitewater snow report", "reported", "resort_snow",
                         whitewater.PROVIDER, "Whitewater Mountain Resort",
                         WHITEWATER_CONDITIONS, None, 2 * 3600, 30 * 3600)
RESORT_WEATHER = ResortWeather("whitewater_weather", "Whitewater mountain observations", "measured",
                               "mountain_weather", whitewater.PROVIDER, "Whitewater Mountain Resort",
                               WHITEWATER_ADVANCED, None, 3600, 2 * 3600)
RESORT_SOURCES = (RESORT_SNOW, RESORT_WEATHER)
SOURCES = {source.key: source for source in (IFS, HRDPS, NELSON_CS, FREEZING, *RESORT_SOURCES)}
DISABLED = {
    "southridge": {"label": "Southridge RAWS", "kind": "measured", "status": "disabled",
                   "reason": "recurring_use_permission_pending",
                   "link": "https://avalanche.ca/weather/stations/22", "data": None},
}
