import json
import logging
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.audit_event import AuditEvent
from app.models.project import Project
from app.models.project_pricing import ProjectPricing

logger = logging.getLogger("uvicorn.error")

PRICING_MODES = {"HOURLY", "FIXED_TOTAL", "PER_M2", "PER_ROOM", "PIECEWORK"}


class PricingValidationError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Pricing validation failed")
        self.errors = errors


def get_or_create_project_pricing(db: Session, project_id: int) -> ProjectPricing:
    pricing = db.query(ProjectPricing).filter(ProjectPricing.project_id == project_id).first()
    if pricing:
        return pricing

    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    pricing = ProjectPricing(project_id=project_id, mode="HOURLY")
    db.add(pricing)
    db.commit()
    db.refresh(pricing)
    return pricing


def _parse_decimal(value: str | None, *, field: str, errors: dict[str, str], allow_empty: bool = True):
    if value is None or value == "":
        if allow_empty:
            return None
        errors[field] = "Обязательное поле"
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        errors[field] = "Некорректное число"
        return None
    if amount <= 0:
        errors[field] = "Значение должно быть больше 0"
        return None
    return amount.quantize(Decimal("0.01"))


def update_project_pricing(
    db: Session,
    *,
    pricing: ProjectPricing,
    payload: dict,
    user_id: str | None,
) -> ProjectPricing:
    errors: dict[str, str] = {}
    mode = (payload.get("mode") or "").strip().upper()
    if mode not in PRICING_MODES:
        errors["mode"] = "Выберите корректный режим"

    hourly_rate_override = _parse_decimal(payload.get("hourly_rate_override"), field="hourly_rate_override", errors=errors)
    fixed_total_price = _parse_decimal(payload.get("fixed_total_price"), field="fixed_total_price", errors=errors)
    rate_per_m2 = _parse_decimal(payload.get("rate_per_m2"), field="rate_per_m2", errors=errors)
    rate_per_room = _parse_decimal(payload.get("rate_per_room"), field="rate_per_room", errors=errors)
    rate_per_piece = _parse_decimal(payload.get("rate_per_piece"), field="rate_per_piece", errors=errors)

    target_margin_pct = None
    target_margin_raw = payload.get("target_margin_pct")
    if target_margin_raw not in (None, ""):
        try:
            target_margin_pct = Decimal(target_margin_raw).quantize(Decimal("0.01"))
            if target_margin_pct < 0 or target_margin_pct > 80:
                errors["target_margin_pct"] = "Маржа должна быть в диапазоне 0–80%"
        except (InvalidOperation, TypeError):
            errors["target_margin_pct"] = "Некорректное число"

    if mode == "FIXED_TOTAL" and fixed_total_price is None:
        errors.setdefault("fixed_total_price", "Для Fixed total укажите общую цену")
    if mode == "PER_M2" and rate_per_m2 is None:
        errors.setdefault("rate_per_m2", "Для Per m² укажите ставку")
    if mode == "PER_ROOM" and rate_per_room is None:
        errors.setdefault("rate_per_room", "Для Per room укажите ставку")
    if mode == "PIECEWORK" and rate_per_piece is None:
        errors.setdefault("rate_per_piece", "Для Piecework укажите ставку")

    if errors:
        raise PricingValidationError(errors)

    changed_fields: list[str] = []

    def _set(field: str, value):
        nonlocal changed_fields
        if getattr(pricing, field) != value:
            changed_fields.append(field)
            setattr(pricing, field, value)

    _set("mode", mode)
    _set("hourly_rate_override", hourly_rate_override)
    _set("fixed_total_price", fixed_total_price)
    _set("rate_per_m2", rate_per_m2)
    _set("rate_per_room", rate_per_room)
    _set("rate_per_piece", rate_per_piece)
    _set("target_margin_pct", target_margin_pct)
    _set("include_materials", payload.get("include_materials") in ("on", "true", True, "1", 1))
    _set(
        "include_travel_setup_buffers",
        payload.get("include_travel_setup_buffers") in ("on", "true", True, "1", 1),
    )
    _set("currency", (payload.get("currency") or "SEK").upper())

    db.add(pricing)
    db.add(
        AuditEvent(
            event_type="pricing_updated",
            user_id=user_id,
            entity_type="project",
            entity_id=pricing.project_id,
            details=json.dumps(
                {
                    "project_id": pricing.project_id,
                    "mode": pricing.mode,
                    "changed_fields": changed_fields,
                },
                ensure_ascii=False,
            ),
        )
    )
    logger.info(
        "event=pricing_updated project_id=%s mode=%s changed_fields=%s user_id=%s",
        pricing.project_id,
        pricing.mode,
        ",".join(changed_fields),
        user_id,
    )
    db.commit()
    db.refresh(pricing)
    return pricing
