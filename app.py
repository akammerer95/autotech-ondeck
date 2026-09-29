import hashlib
import os
import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = "auto-tech-admin-secret"

DB_PATH = os.path.join(app.root_path, "site.db")

STATIC_SERVICES = [
    {
        "name": "Full Auto Service & Repair",
        "description": "Complete mobile vehicle inspection and repair for drivability, safety, and long-term reliability at your location.",
        "featured": True,
    },
    {
        "name": "Brake Inspection & Repair",
        "description": "Mobile brake system diagnostics, pad and rotor checks, and repairs to keep your vehicle stopping safely.",
        "featured": True,
    },
    {
        "name": "Diagnostics & Electrical Repair",
        "description": "On-site computerized system scanning and repair for warning lights, sensors, and electrical issues.",
        "featured": True,
    },
    {
        "name": "Engine Tune-Up & Performance",
        "description": "Mobile inspection and repair of ignition, fuel, and engine performance concerns with tune-up service.",
        "featured": False,
    },
    {
        "name": "A/C Inspection & Recharge",
        "description": "Cooling system inspection, recharge, and mobile repair for reliable cabin comfort and system performance.",
        "featured": False,
    },
    {
        "name": "Vehicle Safety Inspection & Repair",
        "description": "Road-ready mobile inspection and repair for tires, suspension, steering, and overall vehicle safety.",
        "featured": False,
    },
]


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def prune_expired_entries(conn: sqlite3.Connection):
    today = date.today()
    expiration_date = (today - timedelta(days=365)).isoformat()
    warning_date = (today - timedelta(days=335)).isoformat()

    conn.execute(
        "DELETE FROM account_entries WHERE created_at <= ?",
        (expiration_date,),
    )
    conn.commit()

    return conn.execute(
        "SELECT * FROM account_entries WHERE created_at <= ? AND created_at > ? ORDER BY created_at DESC",
        (warning_date, expiration_date),
    ).fetchall()


def init_db() -> None:
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """
    )

    entries_columns = [row[1] for row in conn.execute("PRAGMA table_info(account_entries)").fetchall()]
    if not entries_columns:
        conn.execute(
            """
            CREATE TABLE account_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                service_name TEXT NOT NULL,
                amount TEXT NOT NULL,
                service_date TEXT NOT NULL,
                month TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (date('now'))
            )
            """
        )

    admin_user = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        ("autoadmin",),
    ).fetchone()
    if admin_user is None:
        conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("autoadmin", hash_password("autotechpass")),
        )

    conn.commit()
    conn.close()


@app.before_request
def ensure_db() -> None:
    init_db()


@app.route("/")
def home() -> str:
    return render_template("index.html", services=STATIC_SERVICES)


@app.route("/login", methods=["POST"])
def login() -> Any:
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password_hash = ?",
        (username, hash_password(password)),
    ).fetchone()
    conn.close()

    if user:
        session["admin_logged_in"] = True
        session["admin_user"] = user["username"]
        flash("Admin login successful.", "success")
        return redirect(url_for("admin_dashboard"))

    flash("Invalid username or password.", "error")
    return redirect(url_for("home"))


@app.route("/logout")
def logout() -> Any:
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/admin")
def admin_dashboard() -> Any:
    if not session.get("admin_logged_in"):
        flash("Please log in to access the admin area.", "error")
        return redirect(url_for("home"))

    conn = get_db_connection()
    warning_entries = prune_expired_entries(conn)
    entries = conn.execute(
        "SELECT * FROM account_entries ORDER BY month DESC, service_date DESC"
    ).fetchall()
    conn.close()

    grouped_entries = defaultdict(list)
    for entry in entries:
        grouped_entries[entry["month"]].append(dict(entry))

    ordered_months = sorted(grouped_entries.keys(), reverse=True)
    return render_template(
        "admin.html",
        grouped_entries={month: grouped_entries[month] for month in ordered_months},
        warning_entries=[dict(item) for item in warning_entries],
    )


@app.route("/admin/add_entry", methods=["POST"])
def add_entry() -> Any:
    if not session.get("admin_logged_in"):
        flash("Please log in to add account entries.", "error")
        return redirect(url_for("home"))

    customer_name = request.form.get("customer_name", "").strip()
    service_name = request.form.get("service_name", "").strip()
    amount = request.form.get("amount", "").strip()
    service_date = request.form.get("service_date", "").strip()
    month = request.form.get("month", "").strip() or (service_date[:7] if service_date else date.today().strftime("%Y-%m"))
    notes = request.form.get("notes", "").strip()

    if not customer_name or not service_name or not amount or not service_date:
        flash("Customer, service, amount, and date are required.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO account_entries (customer_name, service_name, amount, service_date, month, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (customer_name, service_name, amount, service_date, month, notes, date.today().isoformat()),
    )
    conn.commit()
    conn.close()

    flash("Account entry added successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/update_entry", methods=["POST"])
def update_entry() -> Any:
    if not session.get("admin_logged_in"):
        flash("Please log in to edit account entries.", "error")
        return redirect(url_for("home"))

    entry_id = request.form.get("entry_id")
    customer_name = request.form.get("customer_name", "").strip()
    service_name = request.form.get("service_name", "").strip()
    amount = request.form.get("amount", "").strip()
    service_date = request.form.get("service_date", "").strip()
    month = request.form.get("month", "").strip() or (service_date[:7] if service_date else date.today().strftime("%Y-%m"))
    notes = request.form.get("notes", "").strip()

    if not entry_id or not customer_name or not service_name or not amount or not service_date:
        flash("All entry fields are required.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    conn.execute(
        "UPDATE account_entries SET customer_name = ?, service_name = ?, amount = ?, service_date = ?, month = ?, notes = ? WHERE id = ?",
        (customer_name, service_name, amount, service_date, month, notes, entry_id),
    )
    conn.commit()
    conn.close()

    flash("Entry updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_entry/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id: int) -> Any:
    if not session.get("admin_logged_in"):
        flash("Please log in to delete account entries.", "error")
        return redirect(url_for("home"))

    conn = get_db_connection()
    conn.execute("DELETE FROM account_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

    flash("Entry deleted.", "success")
    return redirect(url_for("admin_dashboard"))


init_db()


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
