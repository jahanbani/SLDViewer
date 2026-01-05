"""
Performance timing and logging utilities.

Provides consistent timing/logging for tracking where time is spent
during file parsing and processing.
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator

# Configure logger
logger = logging.getLogger("sld_viewer")

# Default format includes timestamp, level, and message
_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter(
    "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
))

# Only add handler if not already configured
if not logger.handlers:
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


@dataclass
class TimingReport:
    """Container for timing information."""
    operation: str
    total_seconds: float
    phases: dict[str, float] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        """Generate a summary string."""
        lines = [f"=== {self.operation} completed in {self.total_seconds:.3f}s ==="]

        if self.phases:
            lines.append("Phases:")
            for phase, duration in sorted(self.phases.items(), key=lambda x: -x[1]):
                pct = (duration / self.total_seconds * 100) if self.total_seconds > 0 else 0
                lines.append(f"  {phase}: {duration:.3f}s ({pct:.1f}%)")

        if self.counts:
            lines.append("Counts:")
            for name, count in sorted(self.counts.items()):
                lines.append(f"  {name}: {count:,}")

        return "\n".join(lines)


class OperationTimer:
    """
    Timer for tracking multi-phase operations.

    Usage:
        timer = OperationTimer("File Parsing")

        timer.start_phase("read_file")
        # ... do work ...
        timer.end_phase("read_file")

        timer.start_phase("parse_buses")
        # ... do work ...
        timer.end_phase("parse_buses")

        timer.set_count("buses", 10000)

        report = timer.finish()
        print(report.summary())
    """

    def __init__(self, operation: str, log_phases: bool = True):
        """
        Initialize timer.

        Args:
            operation: Name of the overall operation
            log_phases: Whether to log each phase as it completes
        """
        self.operation = operation
        self.log_phases = log_phases
        self.start_time = time.perf_counter()
        self._phase_starts: dict[str, float] = {}
        self._phase_durations: dict[str, float] = {}
        self._counts: dict[str, int] = {}

        logger.info(f"[START] {operation}")

    def start_phase(self, phase: str) -> None:
        """Start timing a phase."""
        self._phase_starts[phase] = time.perf_counter()
        logger.debug(f"  [PHASE START] {phase}")

    def end_phase(self, phase: str, count: int | None = None) -> float:
        """
        End timing a phase.

        Args:
            phase: Phase name (must match start_phase)
            count: Optional count of items processed in this phase

        Returns:
            Duration of the phase in seconds
        """
        if phase not in self._phase_starts:
            logger.warning(f"  [PHASE END] {phase} - no matching start!")
            return 0.0

        duration = time.perf_counter() - self._phase_starts[phase]
        self._phase_durations[phase] = duration

        if count is not None:
            self._counts[phase] = count
            rate = count / duration if duration > 0 else 0
            if self.log_phases:
                logger.info(f"  [PHASE] {phase}: {duration:.3f}s ({count:,} items, {rate:.0f}/s)")
        elif self.log_phases:
            logger.info(f"  [PHASE] {phase}: {duration:.3f}s")

        return duration

    def set_count(self, name: str, count: int) -> None:
        """Set a count for the report."""
        self._counts[name] = count

    def finish(self) -> TimingReport:
        """Finish the operation and return the report."""
        total = time.perf_counter() - self.start_time

        report = TimingReport(
            operation=self.operation,
            total_seconds=total,
            phases=self._phase_durations.copy(),
            counts=self._counts.copy(),
        )

        logger.info(f"[DONE] {self.operation}: {total:.3f}s total")

        return report


@contextmanager
def timed_operation(operation: str) -> Generator[OperationTimer, None, None]:
    """
    Context manager for timing an operation.

    Usage:
        with timed_operation("File Parsing") as timer:
            timer.start_phase("read")
            # ...
            timer.end_phase("read")
    """
    timer = OperationTimer(operation)
    try:
        yield timer
    finally:
        timer.finish()


@contextmanager
def timed_phase(phase: str) -> Generator[None, None, None]:
    """
    Simple context manager for timing a single phase.

    Usage:
        with timed_phase("heavy_computation"):
            # ... do work ...
    """
    start = time.perf_counter()
    logger.info(f"  [PHASE START] {phase}")
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        logger.info(f"  [PHASE END] {phase}: {duration:.3f}s")


def log_progress(current: int, total: int, phase: str, interval: int = 10000) -> None:
    """
    Log progress at regular intervals.

    Args:
        current: Current item number (0-based)
        total: Total items
        phase: Phase name
        interval: How often to log (every N items)
    """
    if current > 0 and current % interval == 0:
        pct = (current / total * 100) if total > 0 else 0
        logger.info(f"    [{phase}] {current:,}/{total:,} ({pct:.1f}%)")
