import math
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

EHR_UNDEFINED_ZERO_HOURS = "EHR_UNDEFINED_ZERO_HOURS"
MARGIN_UNDEFINED_ZERO_REVENUE = "MARGIN_UNDEFINED_ZERO_REVENUE"
NO_VALID_PRICING_SCENARIO = "NO_VALID_PRICING_SCENARIO"


@dataclass
class PricingSanityIssue:
    code: str
    severity: Literal["WARN", "FATAL"]
    message: str


@dataclass
class PricingSanityResult:
    is_valid: bool
    issues: list[PricingSanityIssue]


def _safe_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _is_finite_number(value: object) -> bool:
    if value is None:
        return True
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def safe_margin_pct(profit_ex_vat: Decimal, sell_ex_vat: Decimal) -> tuple[Decimal | None, list[PricingSanityIssue]]:
    if sell_ex_vat <= 0:
        return (
            None,
            [
                PricingSanityIssue(
                    code=MARGIN_UNDEFINED_ZERO_REVENUE,
                    severity="WARN",
                    message="Margin percentage is undefined when revenue is less than or equal to zero",
                )
            ],
        )
    return ((profit_ex_vat / sell_ex_vat * Decimal("100")).quantize(Decimal("0.01")), [])


def safe_effective_hourly_rate(sell_ex_vat: Decimal, total_hours: Decimal) -> tuple[Decimal | None, list[PricingSanityIssue]]:
    if total_hours <= 0:
        return (
            None,
            [
                PricingSanityIssue(
                    code=EHR_UNDEFINED_ZERO_HOURS,
                    severity="WARN",
                    message="Effective hourly rate is undefined when total hours are less than or equal to zero",
                )
            ],
        )
    return ((sell_ex_vat / total_hours).quantize(Decimal("0.01")), [])


def validate_pricing_scenario(s: dict) -> PricingSanityResult:
    issues: list[PricingSanityIssue] = list(s.get("sanity_issues") or [])

    def _fatal_if_negative(field: str):
        value = _safe_decimal(s.get(field))
        if value is not None and value < 0:
            issues.append(PricingSanityIssue(code=f"NEGATIVE_{field.upper()}", severity="FATAL", message=f"{field} must be non-negative"))

    _fatal_if_negative("sell_ex_vat")
    _fatal_if_negative("total_hours")
    _fatal_if_negative("labour_cost_ex_vat")
    _fatal_if_negative("materials_cost_ex_vat")

    profit_ex_vat = s.get("profit_ex_vat")
    if not _is_finite_number(profit_ex_vat):
        issues.append(PricingSanityIssue(code="NON_FINITE_PROFIT", severity="FATAL", message="profit_ex_vat must be a finite number"))

    effective_hourly_rate = s.get("effective_hourly_rate")
    if effective_hourly_rate is not None and not _is_finite_number(effective_hourly_rate):
        issues.append(PricingSanityIssue(code="NON_FINITE_EFFECTIVE_HOURLY_RATE", severity="FATAL", message="effective_hourly_rate must be a finite number"))

    is_valid = not any(issue.severity == "FATAL" for issue in issues)
    return PricingSanityResult(is_valid=is_valid, issues=issues)
