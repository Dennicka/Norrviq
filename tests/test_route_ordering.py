from app.main import app


def _route_index(path: str) -> int:
    for idx, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == path:
            return idx
    raise AssertionError(f"route not found: {path}")


def test_static_routes_declared_before_dynamic_routes():
    assert _route_index("/clients/new") < _route_index("/clients/{client_id}")
    assert _route_index("/projects/new") < _route_index("/projects/{project_id}")
    assert _route_index("/projects/{project_id}/invoices/create") < _route_index("/projects/{project_id}/invoices/{invoice_id}")
    assert _route_index("/materials/create") < _route_index("/materials/{material_id}/edit")
    assert _route_index("/projects/{project_id}/rooms/create") < _route_index("/projects/{project_id}/rooms/{room_id}/edit")
