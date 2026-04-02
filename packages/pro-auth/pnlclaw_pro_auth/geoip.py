"""GeoIP resolution from IP addresses.

Uses the MaxMind GeoLite2 City database (optional dependency ``geoip2``).
Gracefully degrades when the database file or library is unavailable.
"""

from __future__ import annotations

import ipaddress
import logging
from pathlib import Path

from pnlclaw_pro_auth.models import GeoLocation

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".pnlclaw" / "data" / "GeoLite2-City.mmdb"


def _is_private_ip(ip: str) -> bool:
    """Return True for loopback, private, or link-local addresses."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return True


class GeoIPResolver:
    """Resolve IP addresses to geographic locations.

    Args:
        db_path: Path to a MaxMind GeoLite2-City MMDB file.
            Defaults to ``~/.pnlclaw/data/GeoLite2-City.mmdb``.
    """

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self._reader: object | None = None
        self._init_reader()

    def _init_reader(self) -> None:
        """Attempt to open the MMDB reader. Fail silently."""
        if not self._db_path.is_file():
            logger.debug("GeoIP database not found at %s", self._db_path)
            return
        try:
            import geoip2.database  # type: ignore[import-untyped]

            self._reader = geoip2.database.Reader(str(self._db_path))
            logger.info("GeoIP database loaded from %s", self._db_path)
        except ImportError:
            logger.debug("geoip2 package not installed — GeoIP resolution disabled")
        except Exception:
            logger.warning("Failed to open GeoIP database at %s", self._db_path, exc_info=True)

    def resolve(self, ip: str) -> GeoLocation | None:
        """Resolve *ip* to a :class:`GeoLocation`, or return ``None``.

        Returns ``None`` when:
        - the GeoIP database or library is unavailable
        - the IP is private / loopback / link-local
        - the IP is not found in the database
        """
        if self._reader is None:
            return None
        if _is_private_ip(ip):
            return None

        try:
            import geoip2.database  # type: ignore[import-untyped]

            reader: geoip2.database.Reader = self._reader  # type: ignore[assignment]
            response = reader.city(ip)
            return GeoLocation(
                country=response.country.name,
                city=response.city.name,
                latitude=response.location.latitude,
                longitude=response.location.longitude,
            )
        except Exception:
            logger.debug("GeoIP lookup failed for %s", ip, exc_info=True)
            return None

    def close(self) -> None:
        """Close the underlying MMDB reader."""
        if self._reader is not None:
            try:
                self._reader.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._reader = None
