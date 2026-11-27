"""Extract individual measurements from Whitewater's public report and station tables."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from poc.sources import require

PROVIDER = "whitewater"
CRAWL_DELAY = 10
TERMS = "https://whitewatermountainresort.com/terms-of-use/"
PACIFIC = ZoneInfo("America/Vancouver")
PERMANENT_PACIFIC = timezone(timedelta(hours=-7))
PACIFIC_CHANGE = datetime(2026, 3, 8, 10, tzinfo=timezone.utc)
SNOW_FIELDS = {"24hr": "24h", "48hr": "48h", "3 Days": "3d",
               "7 Days": "7d", "Total Snowfall": "season", "Current Base": "base_depth"}
STATIONS = {"Last 24 hours at Summit Top - 2002 m": ("summit", "Summit Top", 2002),
            "Last 24 hours at Whitewater Base - 1630 m": ("lodge", "Whitewater Base", 1630)}
WEATHER_HEADERS = ("Date & Time", "Air temp (°C)", "Wind speed (km/hr)", "Prevailing Wind Direction")
COMPASS = "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split()
VOID_TAGS = set("area base br col embed hr img input link meta param source track wbr".split())


@dataclass
class Element:
    tag: str
    classes: list = field(default_factory=list)
    children: list = field(default_factory=list)

    def elements(self, tag=None, css=None):
        for child in self.children:
            if isinstance(child, Element):
                if (tag is None or child.tag == tag) and (css is None or css in child.classes):
                    yield child
                yield from child.elements(tag, css)

    def text(self):
        return " ".join("".join(c if isinstance(c, str) else c.text() for c in self.children).split())


class MeasurementsHTML(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.root = Element("")
        self.stack = [self.root]
        self.feed(body.decode("utf-8") if isinstance(body, bytes) else body)
        self.close()

    def handle_starttag(self, tag, attrs):
        element = Element(tag, (dict(attrs).get("class") or "").split())
        self.stack[-1].children.append(element)
        if tag not in VOID_TAGS:
            self.stack.append(element)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def one(root, tag=None, css=None):
    matches = list(root.elements(tag, css))
    require(len(matches) <= 1, "Ambiguous resort markup")
    return matches[0] if matches else None


def decimal(text, minimum, maximum):
    if re.fullmatch(r"[+-]?[0-9]{1,4}(?:\.[0-9]{1,3})?", text):
        value = float(text)
        if minimum <= value <= maximum:
            return value
    return None


def amount(element, value_class, unit_class):
    if element is None:
        return None
    value = one(element, css=value_class)
    unit = one(element, css=unit_class)
    return decimal(value.text(), 0, 3000) if value and unit and unit.text().casefold() == "cm" else None


def resort_time(local):
    zone = PERMANENT_PACIFIC if local >= datetime(2026, 3, 8, 3) else PACIFIC
    return local.replace(tzinfo=zone).astimezone(timezone.utc)


def parse_report(body, now):
    root = MeasurementsHTML(body).root
    page = one(root, "main") or root
    date = one(page, css="report-date")
    snow = one(page, "ul", "report-snowfall__list")
    plot = one(page, css="report-snowfall__source")
    require(date and snow and plot and re.search(r"\b1950\s*m\b", plot.text(), re.I),
            "Missing Whitewater snow plot or report date")
    label = date.text().removeprefix("Updated on ")
    updated = resort_time(datetime.strptime(label, "%b %d, %Y at %H:%M"))
    require(updated <= now, "Future-dated resort snow report")
    values = dict.fromkeys(("overnight", *SNOW_FIELDS.values()))
    overnight = one(page, css="snow-summary__item--overnight")
    values["overnight"] = amount(overnight, "value", "unit")
    seen = set()
    for item in snow.elements("li"):
        node = one(item, css="condition-field__label")
        key = SNOW_FIELDS.get(node.text()) if node else None
        if key:
            require(key not in seen, "Duplicate snowfall metric")
            seen.add(key)
            values[key] = amount(item, "condition-field__value", "condition-field__unit")
    summary_24h = amount(one(page, css="snow-summary__item--twentyfourhour"), "value", "unit")
    if "24h" not in seen:
        values["24h"] = summary_24h
    elif summary_24h is not None and values["24h"] != summary_24h:
        values["24h"] = None
    if all(value is None for value in values.values()):
        return None
    return {"station": "Summit snow plot", "elevation": 1950, "unit": "cm",
            "report_updated_at": updated.isoformat(), "source_time_label": label,
            "values": values}


def observation_time(label, now):
    # Anchor the year to the request date, including tables spanning New Year's Day.
    local = now.astimezone(PERMANENT_PACIFIC if now >= PACIFIC_CHANGE else PACIFIC)
    candidates = []
    for year in (local.year, local.year - 1):
        try:
            at = resort_time(datetime.strptime(f"{year} {label}", "%Y %b %d %H:%M"))
        except ValueError:
            continue
        if timedelta(0) <= now - at <= timedelta(hours=48):
            candidates.append(at)
    return max(candidates, default=None)


def wind_direction(text):
    match = re.fullmatch(r"([0-9]{1,3}(?:\.[0-9]{1,3})?)°\s*\(([A-Z]{1,3})\)", text)
    if not match or match[2] not in COMPASS:
        return None, None
    degrees = decimal(match[1], 0, 360)
    return (degrees % 360, match[2]) if degrees is not None else (None, None)


def latest_observation(table, now):
    columns = [node.text() for node in table.elements("th")]
    require(all(columns.count(label) == 1 for label in WEATHER_HEADERS), "Unexpected station columns")
    indices = [columns.index(label) for label in WEATHER_HEADERS]
    readings = {}
    for row in table.elements("tr"):
        cells = [node.text() for node in row.elements("td")]
        if len(cells) != len(columns):
            continue
        label, air, speed, direction = [cells[i] for i in indices]
        at = observation_time(label, now)
        if at is None:
            continue
        temperature = decimal(air, -90, 60)
        wind = decimal(speed, 0, 400)
        degrees, compass = wind_direction(direction)
        if all(v is None for v in (temperature, wind, degrees)):
            continue
        require(at not in readings, "Duplicate station observation time")
        readings[at] = {"valid_at": at.isoformat(), "source_time_label": label,
                        "temperature_c": temperature, "wind_kmh": wind,
                        "wind_from_degrees": degrees, "wind_from": compass}
    return readings[max(readings)] if readings else None


def parse_weather(body, now):
    root = MeasurementsHTML(body).root
    readings = {}
    station = None
    for node in root.elements():
        if node.tag == "h2":
            station = STATIONS.get(node.text())
        if node.tag == "table" and "weather-historic-table" in node.classes and station:
            key, name, elevation = station
            require(key not in readings, "Duplicate station table")
            latest = latest_observation(node, now)
            readings[key] = {"station": name, "elevation": elevation, **latest} if latest else None
            station = None
    require(readings, "Missing Whitewater station tables")
    return {"stations": readings} if any(readings.values()) else None
