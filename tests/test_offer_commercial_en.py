from app.db import SessionLocal
from app.services.offer_commercial import compute_offer_commercial
from tests.utils.document_factory import create_stable_document_fixture


def test_offer_commercial_hourly_has_english_description():
    fixture = create_stable_document_fixture(enable_rot=False, issue_documents=False, pricing_mode="HOURLY")

    db = SessionLocal()
    try:
        commercial = compute_offer_commercial(db, fixture.project_id, lang="en")
    finally:
        db.close()

    assert any("Work" in item["description"] for item in commercial.line_items)
