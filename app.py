from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "nexgenops-owner-secret"

POWER_DB_PATH = "power.db"

# =========================================================
# DATABASE
# =========================================================
def db():
    return sqlite3.connect("owner.db", check_same_thread=False)


def power_db():
    return sqlite3.connect(POWER_DB_PATH, check_same_thread=False)


# =========================================================
# INIT DATABASE
# =========================================================
def init_db():
    with db() as d:
        cur = d.cursor()

        # ---------- OWNER ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS owner (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
        """)

        cur.execute("SELECT COUNT(*) FROM owner")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO owner (username, password) VALUES (?, ?)",
                ("owner", generate_password_hash("owner123"))
            )

        # ---------- COMPANIES ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_code TEXT UNIQUE,
            company_name TEXT,
            email TEXT,
            status TEXT,
            created_at TEXT,
            industry TEXT,
            company_size TEXT,
            admin_name TEXT,
            admin_mobile TEXT,
            country TEXT,
            state TEXT,
            city TEXT,
            timezone TEXT,
            requested_plan TEXT,
            expected_users INTEGER,
            expected_meters INTEGER
        )
        """)

        # ---------- PLANS ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price INTEGER,
            meter_limit INTEGER,
            user_limit INTEGER
        )
        """)

        cur.execute("""
        INSERT OR IGNORE INTO plans (id, name, price, meter_limit, user_limit)
        VALUES
            (1, 'Free', 0, 3, 2),
            (2, 'Professional', 7999, 50, 25),
            (3, 'Enterprise', 24999, -1, -1)
        """)

        # ---------- SUBSCRIPTIONS ----------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            plan_id INTEGER,
            status TEXT,
            start_date TEXT
        )
        """)

        d.commit()


def init_power_db():
    with power_db() as d:
        d.execute("""
        CREATE TABLE IF NOT EXISTS pd_companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_code TEXT UNIQUE,
            company_name TEXT,
            status TEXT
        )
        """)

        d.execute("""
        CREATE TABLE IF NOT EXISTS pd_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            username TEXT,
            password TEXT,
            role TEXT
        )
        """)
        d.commit()


# =========================================================
# INIT ON START
# =========================================================
init_db()
init_power_db()

# =========================================================
# LOGIN
# =========================================================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        with db() as d:
            cur = d.cursor()
            cur.execute("SELECT password FROM owner WHERE username=?", (username,))
            row = cur.fetchone()

        if row and check_password_hash(row[0], password):
            session["owner"] = True
            return redirect("/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/dashboard")
def dashboard():
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        cur = d.cursor()

        cur.execute("SELECT COUNT(*) FROM companies")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='ACTIVE'")
        active = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='PENDING'")
        pending = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='SUSPENDED'")
        suspended = cur.fetchone()[0]

        cur.execute("SELECT * FROM companies")
        companies = cur.fetchall()

        cur.execute("""
            SELECT c.id, c.company_name, p.id, p.name, p.price, s.status
            FROM subscriptions s
            JOIN companies c ON s.company_id = c.id
            JOIN plans p ON s.plan_id = p.id
        """)
        subscriptions = cur.fetchall()

        cur.execute("SELECT id, name, price FROM plans")
        plans = cur.fetchall()

        cur.execute("""
            SELECT IFNULL(SUM(p.price),0)
            FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.status='ACTIVE'
        """)
        mrr = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status='ACTIVE'")
        active_subs = cur.fetchone()[0]

    hour = datetime.now().hour
    greeting = "Good Morning" if hour < 12 else "Good Afternoon" if hour < 17 else "Good Evening"

    return render_template(
        "owner_dashboard.html",
        greeting=greeting,
        total=total,
        active=active,
        pending=pending,
        suspended=suspended,
        companies=companies,
        subscriptions=subscriptions,
        plans=plans,
        mrr=mrr,
        active_subs=active_subs,
        trials=0,
        churned=0
    )


# =========================================================
# OWNERS
# =========================================================
@app.route("/owners")
def owners():
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        cur = d.cursor()
        cur.execute("SELECT id, username FROM owner")
        owners = cur.fetchall()

    return render_template("owners.html", owners=owners)


@app.route("/owner/add", methods=["GET", "POST"])
def add_owner():
    if not session.get("owner"):
        return redirect("/")

    if request.method == "POST":
        with db() as d:
            d.execute(
                "INSERT INTO owner (username, password) VALUES (?, ?)",
                (request.form["username"], generate_password_hash(request.form["password"]))
            )
            d.commit()

        return redirect("/dashboard")

    return render_template("add_owner.html")


# =========================================================
# COMPANY REGISTRATION
# =========================================================
@app.route("/company/register")
def company_register_page():
    return render_template("company_register.html")


@app.route("/company/register/submit", methods=["POST"])
def company_register_submit():
    with db() as d:
        d.execute("""
            INSERT INTO companies (
                company_name, email, status, created_at,
                industry, company_size, admin_name, admin_mobile,
                country, state, city, timezone,
                requested_plan, expected_users, expected_meters
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            request.form["company_name"],
            request.form["email"],
            "PENDING",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            request.form["industry"],
            request.form["company_size"],
            request.form["admin_name"],
            request.form["admin_mobile"],
            request.form["country"],
            request.form["state"],
            request.form["city"],
            request.form["timezone"],
            request.form["requested_plan"],
            request.form.get("expected_users"),
            request.form.get("expected_meters")
        ))
        d.commit()

    return redirect("/dashboard")


# =========================================================
# APPROVE / SUSPEND / PLAN (POWER SYNC)
# =========================================================
@app.route("/approve/<int:company_id>")
def approve(company_id):
    if not session.get("owner"):
        return redirect("/")

    company_code = "NG-" + uuid.uuid4().hex[:8].upper()

    with db() as d:
        cur = d.cursor()

        cur.execute("""
            UPDATE companies
            SET status='ACTIVE', company_code=?
            WHERE id=?
        """, (company_code, company_id))

        cur.execute("SELECT company_name, email FROM companies WHERE id=?", (company_id,))
        company_name, email = cur.fetchone()

        cur.execute("""
            INSERT OR IGNORE INTO subscriptions (company_id, plan_id, status, start_date)
            VALUES (?, 1, 'ACTIVE', ?)
        """, (company_id, datetime.now().strftime("%Y-%m-%d")))

        d.commit()

    with power_db() as pd:
        cur = pd.cursor()

        cur.execute("""
            INSERT OR IGNORE INTO pd_companies (company_code, company_name, status)
            VALUES (?, ?, 'ACTIVE')
        """, (company_code, company_name))

        cur.execute("SELECT id FROM pd_companies WHERE company_code=?", (company_code,))
        pd_company_id = cur.fetchone()[0]

        cur.execute("""
            INSERT OR IGNORE INTO pd_users (company_id, username, password, role)
            VALUES (?, ?, ?, 'ADMIN')
        """, (pd_company_id, email, generate_password_hash("admin123")))

        pd.commit()

    return redirect("/dashboard")


@app.route("/suspend/<int:company_id>")
def suspend(company_id):
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        cur = d.cursor()
        cur.execute("SELECT company_code FROM companies WHERE id=?", (company_id,))
        code = cur.fetchone()[0]

        cur.execute("UPDATE companies SET status='SUSPENDED' WHERE id=?", (company_id,))
        d.commit()

    with power_db() as pd:
        pd.execute("UPDATE pd_companies SET status='SUSPENDED' WHERE company_code=?", (code,))
        pd.commit()

    return redirect("/dashboard")


@app.route("/change-plan/<int:company_id>/<int:plan_id>")
def change_plan(company_id, plan_id):
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        d.execute("UPDATE subscriptions SET plan_id=? WHERE company_id=?", (plan_id, company_id))
        d.commit()

    return redirect("/dashboard")


# =========================================================
# LOGOUT
# =========================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
