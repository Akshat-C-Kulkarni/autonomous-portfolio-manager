"""Signal generation module."""

from __future__ import annotations


def generate_signal(current_price: float, predicted_high: float, predicted_low: float) -> dict:
    """Generate BUY/SELL/HOLD signal with confidence score.

    Rules:
    - BUY  when current_price <= predicted_low
    - SELL when current_price >= predicted_high
    - HOLD otherwise
    """
    current_price = float(current_price)
    predicted_high = float(predicted_high)
    predicted_low = float(predicted_low)

    # Ensure boundaries are ordered even if upstream predictions are flipped.
    lower = min(predicted_low, predicted_high)
    upper = max(predicted_low, predicted_high)
    band_width = max(upper - lower, 1e-8)

    if current_price <= lower:
        signal = "BUY"
        distance = lower - current_price
        confidence = min(100.0, 50.0 + (distance / band_width) * 50.0)
    elif current_price >= upper:
        signal = "SELL"
        distance = current_price - upper
        confidence = min(100.0, 50.0 + (distance / band_width) * 50.0)
    else:
        signal = "HOLD"
        dist_to_lower = current_price - lower
        dist_to_upper = upper - current_price
        nearest_boundary = min(dist_to_lower, dist_to_upper)
        confidence = max(0.0, min(100.0, (nearest_boundary / (band_width / 2.0)) * 100.0))

    return {
        "signal": signal,
        "confidence": int(round(confidence)),
        "predicted_high": round(float(upper), 4),
        "predicted_low": round(float(lower), 4),
        "current_price": round(float(current_price), 4),
    }


class SignalEngine:
    """Generate buy/sell/hold signals from model outputs."""

    def generate_signal(
        self, current_price: float, predicted_high: float, predicted_low: float
    ) -> dict:
        """Class wrapper around module-level generate_signal."""
        return generate_signal(
            current_price=current_price,
            predicted_high=predicted_high,
            predicted_low=predicted_low,
        )
