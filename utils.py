"""
utils.py
--------
Small, reusable helper functions that don't belong to any single domain
(database, portfolio logic, or analytics). Keeping these separate avoids
duplicating formatting code across dashboard.py, portfolio.py, and
analytics.py -- a real "don't repeat yourself" (DRY) decision worth
naming if asked about code organization choices.
"""


def format_currency(value):
    """Formats a number as currency, e.g. 15000.5 -> '$15,000.50'."""
    try:
        return f"${value:,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def format_percent(value):
    """Formats a number as a signed percentage, e.g. 5.2 -> '+5.20%'."""
    try:
        sign = "+" if value >= 0 else ""
        return f"{sign}{value:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def risk_label(risk_score):
    """
    Converts a numeric risk score (0-100) into a human-readable label.
    Simple threshold-based bucketing -- deliberately simple and
    explainable rather than a trained classifier, matching the
    "interview-friendly, not overcomplicated" scope of this project.
    """
    if risk_score < 30:
        return "Low Risk"
    elif risk_score < 60:
        return "Moderate Risk"
    else:
        return "High Risk"


def validate_positive_number(value, field_name="Value"):
    """
    Shared input-validation helper. Raises a clear, specific error
    message rather than letting a bad value silently propagate into a
    SQL INSERT or a financial calculation.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return value
