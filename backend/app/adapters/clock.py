from datetime import datetime, timezone


class SystemClock:
    """ClockPort real: hora del sistema en UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
