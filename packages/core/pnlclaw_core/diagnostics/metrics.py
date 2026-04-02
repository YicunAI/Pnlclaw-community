"""Metrics collection: counter, gauge, histogram with label support."""

from __future__ import annotations

import threading
from enum import Enum
from typing import Any


class MetricType(str, Enum):
    """Supported metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


_DEFAULT_HISTOGRAM_MAX_SIZE = 10_000


class MetricsCollector:
    """In-process metrics collector with label support.

    Provides counter, gauge, and histogram metric types. Thread-safe.
    Metrics are namespaced (e.g. ``pnlclaw.market.ticks``).

    Args:
        histogram_max_size: Maximum observations kept per histogram label key.
            When exceeded, the oldest half is discarded to bound memory.
    """

    def __init__(self, histogram_max_size: int = _DEFAULT_HISTOGRAM_MAX_SIZE) -> None:
        self._metrics: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._histogram_max_size = histogram_max_size

    def register(self, name: str, metric_type: MetricType, description: str = "") -> None:
        """Register a named metric.

        Args:
            name: Metric name (e.g. 'pnlclaw.market.ws_messages').
            metric_type: COUNTER, GAUGE, or HISTOGRAM.
            description: Human-readable description.
        """
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = {
                    "type": metric_type,
                    "description": description,
                    "values": {},  # label_key → value
                }

    def increment(self, name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        key = self._label_key(labels)
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                return
            m["values"][key] = m["values"].get(key, 0.0) + value

    def set(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric to an absolute value."""
        key = self._label_key(labels)
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                return
            m["values"][key] = value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a histogram observation.

        When the observation list exceeds ``histogram_max_size``, the oldest
        half is discarded to bound memory usage in long-running processes.
        """
        key = self._label_key(labels)
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                return
            if key not in m["values"]:
                m["values"][key] = []
            bucket: list[float] = m["values"][key]
            bucket.append(value)
            if len(bucket) > self._histogram_max_size:
                m["values"][key] = bucket[len(bucket) // 2 :]

    def get_value(self, name: str, labels: dict[str, str] | None = None) -> Any:
        """Read the current value of a metric."""
        key = self._label_key(labels)
        with self._lock:
            m = self._metrics.get(name)
            if m is None:
                return None
            return m["values"].get(key)

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of all metrics."""
        with self._lock:
            return {
                name: {
                    "type": info["type"].value,
                    "description": info["description"],
                    "values": dict(info["values"]),
                }
                for name, info in self._metrics.items()
            }

    @staticmethod
    def _label_key(labels: dict[str, str] | None) -> str:
        if not labels:
            return ""
        return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
