"""Human-readable progress text for long device transfers (Qt-free, unit-testable).

A full "Send All to LF+" can be 2,000+ records and take many minutes; a static "busy" label is
indistinguishable from a hang. `progress_text` turns (done, total, elapsed) into one status-bar line:

    Sending 123 of 2,346 (5%) · Song #5 · 1:23 elapsed · ~18:40 left
"""
from __future__ import annotations


def format_duration(seconds: float) -> str:
    """``m:ss`` under an hour, ``h:mm:ss`` above; never negative."""
    s = max(0, int(round(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def eta_seconds(done: int, total: int, elapsed: float) -> float | None:
    """Estimated seconds left, or None while there isn't enough data for a useful estimate."""
    if done < 2 or elapsed < 2.0 or total <= done:
        return 0.0 if total and done >= total else None
    return elapsed / done * (total - done)


def percent(done: int, total: int) -> int:
    return 0 if total <= 0 else min(100, int(done * 100 / total))


def progress_text(verb: str, done: int, total: int, elapsed: float, current: str = "") -> str:
    parts = [f"{verb} {done:,} of {total:,} ({percent(done, total)}%)"]
    if current:
        parts.append(current)
    parts.append(f"{format_duration(elapsed)} elapsed")
    eta = eta_seconds(done, total, elapsed)
    if done >= total:
        parts.append("finishing…")
    elif eta is None:
        parts.append("estimating time left…")
    else:
        parts.append(f"~{format_duration(eta)} left")
    return " · ".join(parts)
