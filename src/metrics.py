"""Performance and processing metrics collection."""
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Tracks timing and counts across pipeline phases."""
    run_id: str = ""
    total_rows: int = 0
    valid_count: int = 0
    warning_count: int = 0
    rejected_count: int = 0
    duplicate_count: int = 0
    phase_timings: dict[str, float] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    def record_phase(self, phase: str, duration_seconds: float) -> None:
        self.phase_timings[phase] = duration_seconds
        logger.debug("Phase '%s' completed in %.3fs", phase, duration_seconds)

    def finish(self) -> None:
        self.end_time = time.time()

    @property
    def total_duration_seconds(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time

    @property
    def rows_per_second(self) -> float:
        duration = self.total_duration_seconds
        if duration > 0 and self.total_rows > 0:
            return self.total_rows / duration
        return 0.0

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "total_rows": self.total_rows,
            "valid_count": self.valid_count,
            "warning_count": self.warning_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "rows_per_second": round(self.rows_per_second, 1),
            "phase_timings": {k: round(v, 3) for k, v in self.phase_timings.items()},
        }
