"""Reading progress of a saved text."""

# Reading progress at which a saved text counts as read through.
READ_THROUGH = 0.99


def progress_fraction(raw) -> float:
    """reading_progress as 0..1; older rows hold 0..100."""
    try:
        value = float(raw or 0)
    except (TypeError, ValueError):
        return 0.0
    return value / 100 if value > 1 else value
