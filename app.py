"""
Uren Administratie Webapp
--------------------------
Flask + SQLite (lokaal) of PostgreSQL (productie) + Rolgebaseerde rechten

Functies:
- Inloggen met wachtwoord-hashing (werkzeug)
- Uren registreren (handmatig of start/stop timer)
- Klanten en projecten beheren
- Goedkeuringsflow (manager keurt uren goed/af)
- Rapportages met CSV en PDF export
- Overzicht per medewerker en per project

Starten:
    pip install -r requirements.txt
    python app.py

Default login:
    admin@local / admin123
"""

import os
import sqlite3
import csv
import io
import re
from datetime import datetime, date, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort, g
)
from werkzeug.security import generate_password_hash, check_password_hash

# PostgreSQL ondersteuning (alleen als DATABASE_URL gezet is)
try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

# ============================================================
#  CONFIG
# ============================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "instance", "uren.db")
DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL and PSYCOPG_AVAILABLE)

app = Flask(__name__)

# SECRET_KEY MOET een omgevingsvariabele zijn in productie.
# Genereer een veilige sleutel met: python -c "import secrets; print(secrets.token_hex(32))"
app.secret_key = os.environ.get("SECRET_KEY") or "ALLEEN-VOOR-LOKALE-ONTWIKKELING-niet-in-prod"

# Sessie cookies veilig maken
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,       # JS kan cookie niet lezen
    SESSION_COOKIE_SAMESITE="Lax",      # CSRF mitigatie
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",  # alleen via HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)


# ============================================================
#  DATABASE ABSTRACTIE — werkt met SQLite EN PostgreSQL
# ============================================================
class DBConnection:
    """Wrapper die SQLite en PostgreSQL achter één interface zet."""

    def __init__(self):
        if USE_POSTGRES:
            self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=False)
            self.kind = "postgres"
        else:
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            self.conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.kind = "sqlite"

    def _translate(self, sql):
        """Vervang ? door %s voor PostgreSQL."""
        if self.kind == "postgres":
            return sql.replace("?", "%s")
        return sql

    def execute(self, sql, params=()):
        sql = self._translate(sql)
        if self.kind == "postgres":
            cur = self.conn.cursor()
            cur.execute(sql, params)
            return cur
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    """Open één verbinding per request."""
    if "db" not in g:
        g.db = DBConnection()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Schema — PostgreSQL gebruikt SERIAL i.p.v. INTEGER AUTOINCREMENT
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'medewerker',
    manager_id INTEGER REFERENCES users(id),
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    contact TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    hourly_rate REAL DEFAULT 0,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    work_date DATE NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    hours REAL NOT NULL DEFAULT 0,
    description TEXT,
    status TEXT DEFAULT 'ingediend',
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_note TEXT,
    is_running INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_user_date ON time_entries(user_id, work_date);
CREATE INDEX IF NOT EXISTS idx_time_status ON time_entries(status);
"""

SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'medewerker',
    manager_id INTEGER REFERENCES users(id),
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    contact TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    hourly_rate REAL DEFAULT 0,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS time_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    project_id INTEGER NOT NULL REFERENCES projects(id),
    work_date DATE NOT NULL,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    hours REAL NOT NULL DEFAULT 0,
    description TEXT,
    status TEXT DEFAULT 'ingediend',
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_note TEXT,
    is_running INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time_user_date ON time_entries(user_id, work_date);
CREATE INDEX IF NOT EXISTS idx_time_status ON time_entries(status);
"""


# ============================================================
#  HELPERS
# ============================================================
def query_one(sql, params=()):
    cur = get_db().execute(sql, params)
    return cur.fetchone()


def query_all(sql, params=()):
    cur = get_db().execute(sql, params)
    return cur.fetchall()


def execute(sql, params=()):
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return query_one("SELECT * FROM users WHERE id=?", (uid,))


@app.context_processor
def inject_user():
    return dict(current_user=current_user())


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login"))
            if user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# Hulpquery: time_entries joinen met user/project/client
ENTRY_JOIN_SQL = """
    SELECT te.*,
           u.name   AS user_name,
           u.manager_id AS user_manager_id,
           p.name   AS project_name,
           c.name   AS client_name
    FROM time_entries te
    JOIN users u    ON u.id = te.user_id
    JOIN projects p ON p.id = te.project_id
    JOIN clients c  ON c.id = p.client_id
"""


# ============================================================
#  AUTH
# ============================================================
@app.route("/")
def index():
    return redirect(url_for("dashboard" if current_user() else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = query_one(
            "SELECT * FROM users WHERE email=? AND active=1", (email,)
        )
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash(f"Welkom terug, {user['name']}.", "success")
            return redirect(url_for("dashboard"))
        flash("Ongeldige inloggegevens.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Je bent uitgelogd.", "info")
    return redirect(url_for("login"))


# ============================================================
#  DASHBOARD
# ============================================================
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    week_hours = query_one(
        "SELECT COALESCE(SUM(hours),0) AS h FROM time_entries "
        "WHERE user_id=? AND work_date>=?",
        (user["id"], week_start),
    )["h"]

    pending_own = query_one(
        "SELECT COUNT(*) AS c FROM time_entries WHERE user_id=? AND status='ingediend'",
        (user["id"],),
    )["c"]

    running = query_one(
        ENTRY_JOIN_SQL + " WHERE te.user_id=? AND te.is_running=1",
        (user["id"],),
    )

    pending_review = 0
    if user["role"] in ("admin", "manager"):
        if user["role"] == "manager":
            pending_review = query_one(
                "SELECT COUNT(*) AS c FROM time_entries te "
                "JOIN users u ON u.id=te.user_id "
                "WHERE te.status='ingediend' AND u.manager_id=?",
                (user["id"],),
            )["c"]
        else:
            pending_review = query_one(
                "SELECT COUNT(*) AS c FROM time_entries WHERE status='ingediend'"
            )["c"]

    recent = query_all(
        ENTRY_JOIN_SQL + " WHERE te.user_id=? "
        "ORDER BY te.work_date DESC, te.id DESC LIMIT 5",
        (user["id"],),
    )

    return render_template(
        "dashboard.html",
        week_hours=week_hours,
        pending_own=pending_own,
        pending_review=pending_review,
        running=running,
        recent=recent,
    )


# ============================================================
#  TIME ENTRIES
# ============================================================
@app.route("/uren")
@login_required
def time_entries():
    user = current_user()
    entries = query_all(
        ENTRY_JOIN_SQL + " WHERE te.user_id=? "
        "ORDER BY te.work_date DESC, te.id DESC",
        (user["id"],),
    )
    projects = query_all(
        "SELECT p.*, c.name AS client_name FROM projects p "
        "JOIN clients c ON c.id=p.client_id "
        "WHERE p.active=1 ORDER BY c.name, p.name"
    )
    return render_template("time_entries.html", entries=entries, projects=projects)


@app.route("/uren/nieuw", methods=["POST"])
@login_required
def time_entry_create():
    user = current_user()
    try:
        project_id = int(request.form["project_id"])
        work_date = parse_date(request.form["work_date"])
        hours = float(request.form["hours"].replace(",", "."))
        description = request.form.get("description", "").strip()

        if hours <= 0 or hours > 24:
            flash("Aantal uren moet tussen 0 en 24 zijn.", "error")
            return redirect(url_for("time_entries"))

        execute(
            "INSERT INTO time_entries (user_id, project_id, work_date, hours, "
            "description, status) VALUES (?, ?, ?, ?, ?, 'ingediend')",
            (user["id"], project_id, work_date, hours, description),
        )
        flash("Uren geregistreerd.", "success")
    except (ValueError, KeyError):
        flash("Ongeldige invoer.", "error")
    return redirect(url_for("time_entries"))


@app.route("/uren/<int:entry_id>/verwijder", methods=["POST"])
@login_required
def time_entry_delete(entry_id):
    user = current_user()
    entry = query_one("SELECT * FROM time_entries WHERE id=?", (entry_id,))
    if not entry:
        abort(404)
    if entry["user_id"] != user["id"] and user["role"] != "admin":
        abort(403)
    if entry["status"] == "goedgekeurd" and user["role"] != "admin":
        flash("Goedgekeurde uren kunnen niet verwijderd worden.", "error")
        return redirect(url_for("time_entries"))
    execute("DELETE FROM time_entries WHERE id=?", (entry_id,))
    flash("Urenregel verwijderd.", "info")
    return redirect(url_for("time_entries"))


# --- Timer ---
@app.route("/timer/start", methods=["POST"])
@login_required
def timer_start():
    user = current_user()
    running = query_one(
        "SELECT id FROM time_entries WHERE user_id=? AND is_running=1",
        (user["id"],),
    )
    if running:
        flash("Er loopt al een timer. Stop deze eerst.", "error")
        return redirect(url_for("time_entries"))

    project_id = int(request.form["project_id"])
    description = request.form.get("description", "").strip()
    now = datetime.now()
    execute(
        "INSERT INTO time_entries (user_id, project_id, work_date, start_time, "
        "hours, description, is_running, status) "
        "VALUES (?, ?, ?, ?, 0, ?, 1, 'ingediend')",
        (user["id"], project_id, now.date(), now, description),
    )
    flash("Timer gestart.", "success")
    return redirect(url_for("time_entries"))


@app.route("/timer/stop", methods=["POST"])
@login_required
def timer_stop():
    user = current_user()
    running = query_one(
        "SELECT * FROM time_entries WHERE user_id=? AND is_running=1",
        (user["id"],),
    )
    if not running:
        flash("Geen lopende timer.", "error")
        return redirect(url_for("time_entries"))

    now = datetime.now()
    start = running["start_time"]
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    delta = now - start
    hours = round(delta.total_seconds() / 3600, 2)
    execute(
        "UPDATE time_entries SET end_time=?, hours=?, is_running=0 WHERE id=?",
        (now, hours, running["id"]),
    )
    flash(f"Timer gestopt: {hours} uur geregistreerd.", "success")
    return redirect(url_for("time_entries"))


# ============================================================
#  GOEDKEURING
# ============================================================
@app.route("/goedkeuring")
@role_required("admin", "manager")
def approvals():
    user = current_user()
    if user["role"] == "manager":
        entries = query_all(
            ENTRY_JOIN_SQL + " WHERE te.status='ingediend' AND u.manager_id=? "
            "ORDER BY te.work_date DESC",
            (user["id"],),
        )
    else:
        entries = query_all(
            ENTRY_JOIN_SQL + " WHERE te.status='ingediend' "
            "ORDER BY te.work_date DESC"
        )
    return render_template("approvals.html", entries=entries)


@app.route("/goedkeuring/<int:entry_id>/<string:action>", methods=["POST"])
@role_required("admin", "manager")
def approval_action(entry_id, action):
    user = current_user()
    entry = query_one(
        "SELECT te.*, u.manager_id AS user_manager_id "
        "FROM time_entries te JOIN users u ON u.id=te.user_id WHERE te.id=?",
        (entry_id,),
    )
    if not entry:
        abort(404)
    if user["role"] == "manager" and entry["user_manager_id"] != user["id"]:
        abort(403)

    if action == "goedkeuren":
        new_status = "goedgekeurd"
    elif action == "afwijzen":
        new_status = "afgewezen"
    else:
        abort(400)

    execute(
        "UPDATE time_entries SET status=?, reviewed_by=?, reviewed_at=?, "
        "review_note=? WHERE id=?",
        (
            new_status,
            user["id"],
            datetime.utcnow(),
            request.form.get("note", "").strip() or None,
            entry_id,
        ),
    )
    flash(f"Urenregel {action}.", "success")
    return redirect(url_for("approvals"))


# ============================================================
#  RAPPORTAGES
# ============================================================
def report_filter_clause(user, args):
    """Bouw WHERE-clause + parameters op basis van filters en rol."""
    where = ["te.work_date >= ?", "te.work_date <= ?"]
    params = [args["start_d"], args["end_d"]]

    if user["role"] == "medewerker":
        where.append("te.user_id = ?")
        params.append(user["id"])
    elif user["role"] == "manager":
        where.append("(u.manager_id = ? OR te.user_id = ?)")
        params.extend([user["id"], user["id"]])

    if args.get("project_id"):
        where.append("te.project_id = ?")
        params.append(args["project_id"])

    if args.get("user_id") and user["role"] in ("admin", "manager"):
        where.append("te.user_id = ?")
        params.append(args["user_id"])

    return " AND ".join(where), params


def collect_filters():
    start = request.args.get("start") or (date.today() - timedelta(days=30)).isoformat()
    end = request.args.get("end") or date.today().isoformat()
    return {
        "start": start,
        "end": end,
        "start_d": parse_date(start),
        "end_d": parse_date(end),
        "project_id": request.args.get("project_id", type=int),
        "user_id": request.args.get("user_id", type=int),
    }


@app.route("/rapportage")
@login_required
def reports():
    user = current_user()
    f = collect_filters()
    where, params = report_filter_clause(user, f)

    entries = query_all(ENTRY_JOIN_SQL + f" WHERE {where} ORDER BY te.work_date DESC", params)
    total_hours = sum(e["hours"] for e in entries)

    by_project, by_user = {}, {}
    for e in entries:
        by_project[e["project_name"]] = by_project.get(e["project_name"], 0) + e["hours"]
        by_user[e["user_name"]] = by_user.get(e["user_name"], 0) + e["hours"]

    projects = query_all(
        "SELECT p.*, c.name AS client_name FROM projects p "
        "JOIN clients c ON c.id=p.client_id WHERE p.active=1 ORDER BY c.name, p.name"
    )
    users = []
    if user["role"] == "admin":
        users = query_all("SELECT * FROM users WHERE active=1 ORDER BY name")
    elif user["role"] == "manager":
        users = query_all(
            "SELECT * FROM users WHERE active=1 AND (manager_id=? OR id=?) ORDER BY name",
            (user["id"], user["id"]),
        )

    return render_template(
        "reports.html",
        entries=entries,
        total_hours=total_hours,
        by_project=by_project,
        by_user=by_user,
        projects=projects,
        users=users,
        filters={"start": f["start"], "end": f["end"],
                 "project_id": f["project_id"], "user_id": f["user_id"]},
    )


@app.route("/rapportage/export.csv")
@login_required
def export_csv():
    user = current_user()
    f = collect_filters()
    where, params = report_filter_clause(user, f)
    entries = query_all(ENTRY_JOIN_SQL + f" WHERE {where} ORDER BY te.work_date DESC", params)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Datum", "Medewerker", "Klant", "Project",
                     "Uren", "Status", "Omschrijving"])
    for e in entries:
        writer.writerow([
            e["work_date"],
            e["user_name"],
            e["client_name"],
            e["project_name"],
            f"{e['hours']:.2f}".replace(".", ","),
            e["status"],
            (e["description"] or "").replace("\n", " "),
        ])

    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name=f"uren_{f['start']}_{f['end']}.csv")


@app.route("/rapportage/export.pdf")
@login_required
def export_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    user = current_user()
    f = collect_filters()
    where, params = report_filter_clause(user, f)
    entries = query_all(ENTRY_JOIN_SQL + f" WHERE {where} ORDER BY te.work_date DESC", params)
    total = sum(e["hours"] for e in entries)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=40, rightMargin=40,
                            topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 fontName="Helvetica-Bold", fontSize=18,
                                 textColor=colors.HexColor("#1a1a1a"))
    meta_style = ParagraphStyle("meta", parent=styles["Normal"],
                                fontSize=9, textColor=colors.HexColor("#666"))

    story = [
        Paragraph("Urenrapportage", title_style),
        Paragraph(f"Periode: {f['start']} t/m {f['end']}", meta_style),
        Paragraph(f"Gegenereerd door: {user['name']}", meta_style),
        Paragraph(f"Totaal uren: <b>{total:.2f}</b>", meta_style),
        Spacer(1, 18),
    ]

    data = [["Datum", "Medewerker", "Project", "Uren", "Status"]]
    for e in entries:
        wd = e["work_date"]
        wd_str = wd.isoformat() if hasattr(wd, "isoformat") else str(wd)
        data.append([
            wd_str,
            e["user_name"],
            f"{e['client_name']} – {e['project_name']}",
            f"{e['hours']:.2f}",
            e["status"],
        ])

    table = Table(data, repeatRows=1, colWidths=[70, 100, 200, 50, 70])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f5f3ee")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    doc.build(story)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=f"uren_{f['start']}_{f['end']}.pdf")


# ============================================================
#  GEBRUIKERSBEHEER (Admin)
# ============================================================
@app.route("/beheer/gebruikers")
@role_required("admin")
def users_admin():
    users = query_all("SELECT * FROM users ORDER BY name")
    managers = query_all("SELECT * FROM users WHERE role='manager' AND active=1 ORDER BY name")
    return render_template("users.html", users=users, managers=managers)


@app.route("/beheer/gebruikers/nieuw", methods=["POST"])
@role_required("admin")
def user_create():
    email = request.form["email"].strip().lower()
    name = request.form["name"].strip()
    role = request.form["role"]
    password = request.form["password"]
    manager_id = request.form.get("manager_id") or None

    if query_one("SELECT id FROM users WHERE email=?", (email,)):
        flash("Dit e-mailadres bestaat al.", "error")
        return redirect(url_for("users_admin"))

    execute(
        "INSERT INTO users (email, name, role, manager_id, password_hash, active) "
        "VALUES (?, ?, ?, ?, ?, 1)",
        (email, name, role,
         int(manager_id) if manager_id else None,
         generate_password_hash(password)),
    )
    flash(f"Gebruiker '{name}' aangemaakt.", "success")
    return redirect(url_for("users_admin"))


@app.route("/beheer/gebruikers/<int:user_id>/wijzig", methods=["POST"])
@role_required("admin")
def user_update(user_id):
    user = query_one("SELECT * FROM users WHERE id=?", (user_id,))
    if not user:
        abort(404)

    name = request.form.get("name", user["name"]).strip()
    role = request.form.get("role", user["role"])
    active = 1 if request.form.get("active") == "on" else 0
    manager_id = request.form.get("manager_id") or None
    new_password = request.form.get("password", "").strip()

    if new_password:
        execute(
            "UPDATE users SET name=?, role=?, active=?, manager_id=?, password_hash=? "
            "WHERE id=?",
            (name, role, active,
             int(manager_id) if manager_id else None,
             generate_password_hash(new_password), user_id),
        )
    else:
        execute(
            "UPDATE users SET name=?, role=?, active=?, manager_id=? WHERE id=?",
            (name, role, active,
             int(manager_id) if manager_id else None, user_id),
        )
    flash("Gebruiker bijgewerkt.", "success")
    return redirect(url_for("users_admin"))


# ============================================================
#  KLANTEN & PROJECTEN
# ============================================================
@app.route("/beheer/projecten")
@role_required("admin", "manager")
def projects_admin():
    clients = query_all("SELECT * FROM clients ORDER BY name")
    projects = query_all(
        "SELECT p.*, c.name AS client_name FROM projects p "
        "JOIN clients c ON c.id=p.client_id ORDER BY c.name, p.name"
    )
    return render_template("projects.html", clients=clients, projects=projects)


@app.route("/beheer/klanten/nieuw", methods=["POST"])
@role_required("admin", "manager")
def client_create():
    name = request.form["name"].strip()
    contact = request.form.get("contact", "").strip()
    if not name:
        flash("Naam is verplicht.", "error")
        return redirect(url_for("projects_admin"))
    try:
        execute("INSERT INTO clients (name, contact) VALUES (?, ?)", (name, contact))
        flash("Klant aangemaakt.", "success")
    except Exception:
        flash("Deze klantnaam bestaat al.", "error")
    return redirect(url_for("projects_admin"))


@app.route("/beheer/projecten/nieuw", methods=["POST"])
@role_required("admin", "manager")
def project_create():
    name = request.form["name"].strip()
    client_id = int(request.form["client_id"])
    rate = float(request.form.get("hourly_rate") or 0)
    execute(
        "INSERT INTO projects (name, client_id, hourly_rate) VALUES (?, ?, ?)",
        (name, client_id, rate),
    )
    flash("Project aangemaakt.", "success")
    return redirect(url_for("projects_admin"))


@app.route("/beheer/projecten/<int:project_id>/toggle", methods=["POST"])
@role_required("admin", "manager")
def project_toggle(project_id):
    p = query_one("SELECT * FROM projects WHERE id=?", (project_id,))
    if not p:
        abort(404)
    execute("UPDATE projects SET active=? WHERE id=?",
            (0 if p["active"] else 1, project_id))
    return redirect(url_for("projects_admin"))


# ============================================================
#  ERROR HANDLERS
# ============================================================
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="Geen toegang tot deze pagina."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="Pagina niet gevonden."), 404


# ============================================================
#  INIT
# ============================================================
def init_db():
    """Schema aanmaken en evt. demo-data invoegen, voor zowel SQLite als PostgreSQL."""
    if USE_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, autocommit=True)
        # Schema in stukken uitvoeren (psycopg ondersteunt geen executescript)
        with conn.cursor() as cur:
            # Verwijder commentaar-blokken en splits op puntkomma's
            statements = [s.strip() for s in SCHEMA_POSTGRES.split(";") if s.strip()]
            for stmt in statements:
                cur.execute(stmt)
        placeholder = "%s"
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA_SQLITE)
        conn.commit()
        placeholder = "?"

    is_production = os.environ.get("FLASK_ENV") == "production"

    def _exec(cur, sql, params=()):
        cur.execute(sql.replace("?", placeholder), params)

    def _fetchone(cur):
        return cur.fetchone()

    # Bij lege database: admin aanmaken
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    row = cur.fetchone()
    count = row[0] if isinstance(row, tuple) or hasattr(row, '__getitem__') else 0
    if hasattr(row, 'keys'):  # dict_row of sqlite3.Row
        count = list(row)[0] if isinstance(row, sqlite3.Row) else list(row.values())[0]

    if count == 0:
        if is_production:
            # Productie: alleen één admin met wachtwoord uit env-var
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@local")
            admin_password = os.environ.get("ADMIN_PASSWORD")
            if not admin_password:
                # Genereer een willekeurig wachtwoord en log het één keer
                import secrets
                admin_password = secrets.token_urlsafe(12)
                print("=" * 60)
                print(" EERSTE START — admin account aangemaakt")
                print(f" E-mail:     {admin_email}")
                print(f" Wachtwoord: {admin_password}")
                print(" Log in en wijzig dit wachtwoord direct!")
                print("=" * 60)
            _exec(cur,
                "INSERT INTO users (email, name, role, password_hash) VALUES "
                "(?, ?, 'admin', ?)",
                (admin_email, "Beheerder", generate_password_hash(admin_password)),
            )
            if not USE_POSTGRES:
                conn.commit()
        else:
            # Lokaal: drie demo-accounts en wat testdata
            admin_hash = generate_password_hash("admin123")
            manager_hash = generate_password_hash("manager123")
            emp_hash = generate_password_hash("medewerker123")

            _exec(cur,
                "INSERT INTO users (email, name, role, password_hash) VALUES "
                "(?, ?, 'admin', ?)", ("admin@local", "Beheerder", admin_hash))
            _exec(cur,
                "INSERT INTO users (email, name, role, password_hash) VALUES "
                "(?, ?, 'manager', ?)", ("manager@local", "Marieke Manager", manager_hash))

            cur.execute("SELECT id FROM users WHERE email='manager@local'")
            row = cur.fetchone()
            manager_id = row[0] if isinstance(row, (tuple, sqlite3.Row)) else row['id']

            _exec(cur,
                "INSERT INTO users (email, name, role, manager_id, password_hash) VALUES "
                "(?, ?, 'medewerker', ?, ?)",
                ("medewerker@local", "Pieter Medewerker", manager_id, emp_hash))

            _exec(cur, "INSERT INTO clients (name, contact) VALUES (?, ?)",
                  ("Acme B.V.", "info@acme.nl"))
            cur.execute("SELECT id FROM clients WHERE name='Acme B.V.'")
            row = cur.fetchone()
            client_id = row[0] if isinstance(row, (tuple, sqlite3.Row)) else row['id']

            _exec(cur, "INSERT INTO projects (name, client_id, hourly_rate) VALUES (?, ?, ?)",
                  ("Website redesign", client_id, 85))
            _exec(cur, "INSERT INTO projects (name, client_id, hourly_rate) VALUES (?, ?, ?)",
                  ("Onderhoud", client_id, 75))
            conn.commit()
            print("✓ Database aangemaakt met demo-data")
            print("  Admin:       admin@local / admin123")
            print("  Manager:     manager@local / manager123")
            print("  Medewerker:  medewerker@local / medewerker123")
    conn.close()

    
if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=5000, debug=debug)


# Init database ook bij import (voor WSGI servers zoals Gunicorn / PythonAnywhere)
else:
    init_db()
