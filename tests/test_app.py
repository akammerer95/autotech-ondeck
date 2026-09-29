from datetime import date, timedelta

import pytest

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "site.db"
    monkeypatch.setattr(app_module, "DB_PATH", str(db_file))
    app_module.init_db()
    app_module.app.config.update(TESTING=True)
    with app_module.app.test_client() as client:
        yield client


def test_homepage_uses_static_service_catalog(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Full Auto Service" in html
    assert "Brake Inspection" in html
    assert "Vehicle Safety Inspection" in html
    assert "Oil Change & Filter" not in html


def test_homepage_has_services_instead_of_pricing(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Services Provided" in html
    assert "Pricing" not in html


def test_homepage_has_collapsed_footer_login_and_facebook_message_cta(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<details class="admin-login">' in html
    assert "Admin login" in html
    assert "Send us a Facebook message" in html
    assert "Book on Facebook" not in html
    assert "Facebook Booking" not in html


def test_admin_login_and_entry_creation(client):
    response = client.post(
        "/login",
        data={"username": "autoadmin", "password": "autotechpass"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    response = client.post(
        "/admin/add_entry",
        data={
            "customer_name": "Alex",
            "service_name": "Brake Repair",
            "amount": "210.00",
            "service_date": "2026-09-15",
            "month": "2026-09",
            "notes": "Front pads and rotors",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Alex" in html
    assert "Brake Repair" in html
    assert "2026-09" in html


def test_expired_entries_are_removed_and_warned(client):
    conn = app_module.get_db_connection()
    old_date = (date.today() - timedelta(days=365 + 10)).isoformat()
    conn.execute(
        "INSERT INTO account_entries (customer_name, service_name, amount, service_date, month, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "Old Customer",
            "Tune Up",
            "150.00",
            old_date,
            old_date[:7],
            "old entry",
            old_date,
        ),
    )
    conn.commit()
    conn.close()

    client.post(
        "/login",
        data={"username": "autoadmin", "password": "autotechpass"},
        follow_redirects=True,
    )
    response = client.get("/admin")
    html = response.get_data(as_text=True)
    assert "Old Customer" not in html
    assert "expires" in html.lower() or "warning" in html.lower()
