from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.settings import get_or_create_settings
from app.services.pricing import compute_pricing_scenarios

MONEY = Decimal("0.01")


@dataclass
class OfferCommercial:
    mode: str
    segment: str
    units: dict
    rate: dict
    price_ex_vat: Decimal
    vat_amount: Decimal
    price_inc_vat: Decimal
    line_items: list[dict]
    warnings: list[str]
    math_breakdown: dict


def _q(value: Decimal) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _basis_label(lang: str, basis: str) -> str:
    labels = {
        "sv": {
            "FLOOR_AREA": "golvyta",
            "CEILING_AREA": "takyta",
            "WALL_AREA": "väggyta",
            "PAINTABLE_TOTAL": "målningsbar yta",
        },
        "ru": {
            "FLOOR_AREA": "площадь пола",
            "CEILING_AREA": "площадь потолка",
            "WALL_AREA": "площадь стен",
            "PAINTABLE_TOTAL": "окрашиваемая площадь",
        },
    }
    return labels.get(lang, labels["sv"]).get(basis, basis)


def _line_items(mode: str, selected, baseline, lang: str) -> list[dict]:
    if mode == "FIXED_TOTAL":
        return [{"description": "Fast pris för målning enligt överenskommelse" if lang == "sv" else "Фиксированная цена на малярные работы", "qty": Decimal("1.00"), "unit": "st", "unit_price": selected.price_ex_vat, "total": selected.price_ex_vat}]
    if mode == "PER_M2":
        return [{"description": f"Målning {_basis_label(lang, baseline.m2_basis)}", "qty": baseline.total_m2, "unit": "m²", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_m2') or 0))), "total": selected.price_ex_vat}]
    if mode == "PER_ROOM":
        return [{"description": "Målning per rum", "qty": Decimal(str(baseline.rooms_count)), "unit": "rum", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_room') or 0))), "total": selected.price_ex_vat}]
    if mode == "PIECEWORK":
        return [{"description": "Arbete enligt styckpris", "qty": Decimal(str(baseline.items_count)), "unit": "st", "unit_price": _q(Decimal(str(selected.input_params.get('rate_per_piece') or 0))), "total": selected.price_ex_vat}]
    return [{"description": "Arbete (löpande räkning)", "qty": baseline.labor_hours_total, "unit": "h", "unit_price": _q(Decimal(str(selected.input_params.get('hourly_rate') or 0))), "total": selected.price_ex_vat}]


def _to_payload(offer: OfferCommercial) -> dict:
    def norm(v):
        if isinstance(v, Decimal):
            return str(_q(v))
        if isinstance(v, list):
            return [norm(x) for x in v]
        if isinstance(v, dict):
            return {k: norm(val) for k, val in v.items()}
        return v

    return norm({
        "mode": offer.mode,
        "segment": offer.segment,
        "units": offer.units,
        "rate": offer.rate,
        "price_ex_vat": offer.price_ex_vat,
        "vat_amount": offer.vat_amount,
        "price_inc_vat": offer.price_inc_vat,
        "line_items": offer.line_items,
        "warnings": offer.warnings,
        "math_breakdown": offer.math_breakdown,
    })


def serialize_offer_commercial(offer: OfferCommercial) -> str:
    return json.dumps(_to_payload(offer), ensure_ascii=False, sort_keys=True)


def deserialize_offer_commercial(payload: str | None) -> dict | None:
    if not payload:
        return None
    return json.loads(payload)


def compute_offer_commercial(db: Session, project_id: int, *, lang: str = "sv") -> OfferCommercial:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")
    baseline, scenarios = compute_pricing_scenarios(db, project_id)
    mode = (project.pricing.mode if project.pricing else "HOURLY").upper()
    selected = next((s for s in scenarios if s.mode == mode), scenarios[0])
    settings = get_or_create_settings(db)
    vat_pct = Decimal(str(settings.moms_percent if settings.moms_percent is not None else 25))
    vat_amount = _q(selected.price_ex_vat * vat_pct / Decimal("100"))
    price_inc_vat = _q(selected.price_ex_vat + vat_amount)
    return OfferCommercial(
        mode=mode,
        segment=(project.client.client_segment if project.client and project.client.client_segment else "ANY"),
        units={"m2_basis": baseline.m2_basis, "total_m2": baseline.total_m2, "rooms_count": baseline.rooms_count, "items_count": baseline.items_count},
        rate={
            "hourly_rate": selected.input_params.get("hourly_rate"),
            "fixed_total": selected.input_params.get("fixed_total_price"),
            "rate_per_m2": selected.input_params.get("rate_per_m2"),
            "rate_per_room": selected.input_params.get("rate_per_room"),
            "rate_per_piece": selected.input_params.get("rate_per_piece"),
        },
        price_ex_vat=selected.price_ex_vat,
        vat_amount=vat_amount,
        price_inc_vat=price_inc_vat,
        line_items=_line_items(mode, selected, baseline, lang),
        warnings=list(selected.warnings),
        math_breakdown={
            "baseline_hours": str(baseline.labor_hours_total),
            "internal_total_cost": str(baseline.internal_total_cost),
            "buffers_hours_total": str(baseline.buffers_hours_total),
            "buffers_cost_total": str(baseline.buffers_cost_total),
            "speed_profile_code": baseline.speed_profile_code,
        },
    )


def assert_offer_matches_selected_scenario(db: Session, project_id: int, *, offer: OfferCommercial, tolerance: Decimal = Decimal("0.01")) -> None:
    _, scenarios = compute_pricing_scenarios(db, project_id)
    selected = next((s for s in scenarios if s.mode == offer.mode), None)
    if selected is None:
        raise ValueError("Offer totals mismatch pricing scenario")
    if abs(selected.price_ex_vat - offer.price_ex_vat) > tolerance:
        raise ValueError("Offer totals mismatch pricing scenario")
