from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Client

client = TestClient(app)
settings = get_settings()


def login():
    client.post(
        "/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )


def test_clients_list_page_loads():
    login()
    response = client.get("/clients/")
    assert response.status_code == 200


def test_clients_new_form_loads():
    login()
    response = client.get("/clients/new")
    assert response.status_code == 200
    assert "<form" in response.text


def test_create_client_via_new_happy_path():
    login()
    response = client.post(
        "/clients/new",
        data={
            "name": "New Client",
            "contact_person": "Contact",
            "phone": "123456",
            "email": "client@example.com",
            "address": "Street 1",
            "is_private_person": "on",
            "is_rot_eligible": "on",
            "comment": "Important",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers.get("location", "")
    assert location.startswith("/clients/")

    created = None
    db = SessionLocal()
    try:
        created = db.query(Client).filter(Client.name == "New Client").first()
        assert created is not None
        assert created.contact_person == "Contact"
        assert created.is_rot_eligible is True

        detail_response = client.get(f"/clients/{created.id}")
        assert detail_response.status_code == 200
        assert "New Client" in detail_response.text
    finally:
        if created:
            db.delete(created)
            db.commit()
        db.close()


def test_edit_client_happy_path():
    db = SessionLocal()
    try:
        existing = Client(name="Editable Client")
        db.add(existing)
        db.commit()
        db.refresh(existing)
        client_id = existing.id
    finally:
        db.close()

    login()
    response = client.post(
        f"/clients/{client_id}/edit",
        data={
            "name": "Updated Client",
            "contact_person": "Jane",
            "phone": "987654",
            "email": "updated@example.com",
            "address": "New Street",
            "is_rot_eligible": "",
            "comment": "Edited",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        updated = db.get(Client, client_id)
        assert updated.name == "Updated Client"
        assert updated.contact_person == "Jane"
        assert updated.is_rot_eligible is False
        db.delete(updated)
        db.commit()
    finally:
        db.close()


def test_delete_client_happy_path():
    db = SessionLocal()
    try:
        removable = Client(name="Removable Client")
        db.add(removable)
        db.commit()
        db.refresh(removable)
        client_id = removable.id
    finally:
        db.close()

    login()
    response = client.post(f"/clients/{client_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        assert db.get(Client, client_id) is None
    finally:
        db.close()


def test_validation_error_does_not_crash():
    login()
    response = client.post(
        "/clients/save",
        data={"name": ""},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Укажите имя клиента" in response.text

    db = SessionLocal()
    try:
        assert db.query(Client).filter(Client.name == "").count() == 0
    finally:
        db.close()
