from typing import Optional


def compute_urgency(lag: Optional[int]) -> float:
    """
    Shorter lag → higher urgency.
    Unknown lag → medium urgency.
    """

    if lag is None:
        return 0.5

    if lag <= 1:
        return 1.0
    if lag <= 3:
        return 0.8
    if lag <= 7:
        return 0.6
    if lag <= 14:
        return 0.4
    return 0.2
