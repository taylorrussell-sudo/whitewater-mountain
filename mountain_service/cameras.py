"""A single licensed DriveBC still, held in memory and never archived."""

from dataclasses import dataclass, replace
from hashlib import sha256

from poc.sources import utc

from .sources import Source

DRIVEBC = Source("drivebc_whitewater", "Whitewater junction", "camera", "highway_6_north",
                 "drivebc", "DriveBC", "https://www.drivebc.ca/cameras/759",
                 "https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc",
                 20 * 60, 45 * 60)
MANUAL_SPACING = 15 * 60
METADATA_URL = "https://www.drivebc.ca/api/webcams/759/"
IMAGE_URL = "https://www.drivebc.ca/images/759.jpg"
MAX_IMAGE = 256 * 1024
MAX_AGE = 6 * 3600


class InvalidCamera(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    modified: int
    delayed: bool
    revision: str
    jpeg: bytes


def jpeg_dimensions(data):
    """Read bounded SOF dimensions without decoding a provider image on the Pi."""
    if not (4 <= len(data) <= MAX_IMAGE and data.startswith(b"\xff\xd8")
            and data.endswith(b"\xff\xd9")):
        raise InvalidCamera("invalid_camera_jpeg")
    offset = 2
    while offset + 4 <= len(data) and data[offset] == 255:
        marker = data[offset + 1]
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        end = offset + 2 + length
        if length < 2 or end > len(data) or marker == 0xda:
            break
        if marker in (0xc0, 0xc1, 0xc2) and length >= 8:
            height = int.from_bytes(data[offset + 5:offset + 7], "big")
            width = int.from_bytes(data[offset + 7:offset + 9], "big")
            if 320 <= width <= 1920 and 180 <= height <= 1080:
                return width, height
            break
        offset = end
    raise InvalidCamera("invalid_camera_dimensions")


def update(payload, previous, now, fetch_image):
    try:
        if (payload["id"] != 759 or payload["credit"] != ""
                or payload["orientation"] != "N" or payload["highway"] != "6"
                or payload["is_on_demand"] is not False):
            raise InvalidCamera("unexpected_camera_source")
        if not all(type(payload[key]) is bool
                   for key in ("is_on", "should_appear", "marked_delayed", "marked_stale")):
            raise InvalidCamera("invalid_camera_metadata")
        if not payload["is_on"] or not payload["should_appear"]:
            raise InvalidCamera("camera_offline")
        modified = int(utc(payload["last_update_modified"]).timestamp())
        delayed = payload["marked_delayed"] or payload["marked_stale"]
    except InvalidCamera:
        raise
    except (KeyError, TypeError, AttributeError, OverflowError, OSError, ValueError) as exc:
        raise InvalidCamera("invalid_camera_metadata") from exc
    if not 0 <= now - modified <= MAX_AGE:
        raise InvalidCamera("camera_timestamp_out_of_range")
    if previous and modified <= previous.modified:
        return replace(previous, delayed=delayed or modified < previous.modified)
    # The official still URL is fixed, and redirects are rejected by the transport.
    jpeg = fetch_image(IMAGE_URL)
    jpeg_dimensions(jpeg)
    revision = sha256(jpeg).hexdigest()
    if previous and revision == previous.revision:
        return replace(previous, delayed=delayed)
    return Frame(modified, delayed, revision, jpeg)
