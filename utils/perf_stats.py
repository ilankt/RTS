"""Lightweight runtime performance counters."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import statistics
import time

from core.config import PERF_STATS_ENABLED


class PerfStats:
    """Small frame/counter collector used by debug overlay and benchmarks."""

    def __init__(self, enabled: bool = PERF_STATS_ENABLED, max_frames: int = 600):
        self.enabled = enabled
        self.max_frames = max_frames
        self.frame_times = deque(maxlen=max_frames)
        self.ai_tick_times = deque(maxlen=max_frames)
        self.current_frame_start = None
        self.counters = self._empty_counters()

    def reset(self, max_frames=None):
        if max_frames is not None and max_frames != self.max_frames:
            self.max_frames = max_frames
            self.frame_times = deque(maxlen=max_frames)
            self.ai_tick_times = deque(maxlen=max_frames)
        else:
            self.frame_times.clear()
            self.ai_tick_times.clear()
        self.current_frame_start = None
        self.counters = self._empty_counters()

    @staticmethod
    def _empty_counters():
        return {
            "path_requests": 0,
            "astar_calls": 0,
            "astar_expanded_cells": 0,
            "astar_capped": 0,
            "path_cache_hits": 0,
            "path_cache_misses": 0,
            "path_cache_evictions": 0,
            "path_mark_dirty": 0,
            "path_full_rebuilds": 0,
            "path_incremental_updates": 0,
            "path_rebuild_ms": 0.0,
            "collision_checks": 0,
            "debug_log_writes": 0,
            "ai_ticks": 0,
            "watchdog_recoveries": 0,
            "watchdog_teleports": 0,
        }

    def begin_frame(self):
        if self.enabled:
            self.current_frame_start = time.perf_counter()

    def end_frame(self):
        if self.enabled and self.current_frame_start is not None:
            self.frame_times.append((time.perf_counter() - self.current_frame_start) * 1000.0)
            self.current_frame_start = None

    @contextmanager
    def time_ai_tick(self):
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            self.ai_tick_times.append((time.perf_counter() - start) * 1000.0)
            self.increment("ai_ticks")

    def increment(self, name: str, amount=1):
        if self.enabled:
            self.counters[name] = self.counters.get(name, 0) + amount

    def add_time(self, name: str, milliseconds: float):
        if self.enabled:
            self.counters[name] = self.counters.get(name, 0.0) + milliseconds

    def summary(self) -> dict:
        frame_times = list(self.frame_times)
        ai_times = list(self.ai_tick_times)
        return {
            "frames": len(frame_times),
            "frame_avg_ms": statistics.fmean(frame_times) if frame_times else 0.0,
            "frame_p95_ms": self._percentile(frame_times, 95),
            "frame_max_ms": max(frame_times) if frame_times else 0.0,
            "ai_avg_ms": statistics.fmean(ai_times) if ai_times else 0.0,
            "ai_max_ms": max(ai_times) if ai_times else 0.0,
            **self.counters,
        }

    @staticmethod
    def _percentile(values, percentile):
        if not values:
            return 0.0
        ordered = sorted(values)
        index = int(round((percentile / 100.0) * (len(ordered) - 1)))
        return ordered[index]


perf_stats = PerfStats()
