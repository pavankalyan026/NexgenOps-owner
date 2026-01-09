from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "nexgenops-owner-secret"

# =========================================================
# DATABASE
# =========================================================
def db():
    return sqlite3.connect("owner.db", check_same_thread=False)


# =========================================================
# INIT PLANS
# =========================================================
def upgrade_companies_table():
    with db() as d:
        cur = d.cursor()
        cur.execute("PRAGMA table_info(companies)")
        cols = [c[1] for c in cur.fetchall()]

        def add(col, typ):
            if col not in cols:
                cur.execute(f"ALTER TABLE companies ADD COLUMN {col} {typ}")

        add("industry", "TEXT")
        add("company_size", "TEXT")
        add("admin_name", "TEXT")
        add("admin_mobile", "TEXT")
        add("country", "TEXT")
        add("state", "TEXT")
        add("city", "TEXT")
        add("timezone", "TEXT")
        add("requested_plan", "TEXT")
        add("expected_users", "INTEGER")
        add("expected_meters", "INTEGER")

        d.commit()
def init_plans():
    with db() as d:
        d.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                price INTEGER,
                meter_limit INTEGER,
                user_limit INTEGER
            )
        """)
        d.execute("""
            INSERT OR IGNORE INTO plans (id, name, price, meter_limit, user_limit)
            VALUES
                (1, 'Free', 0, 3, 2),
                (2, 'Professional', 7999, 50, 25),
                (3, 'Enterprise', 24999, -1, -1)
        """)
        d.commit()


# =========================================================
# INIT SUBSCRIPTIONS
# =========================================================
def init_subscriptions():
    with db() as d:
        d.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER,
                plan_id INTEGER,
                status TEXT,
                start_date TEXT
            )
        """)
        d.commit()


# =========================================================
# INIT CORE TABLES
# =========================================================
def init_db():
    with db() as d:
        d.execute("""
            CREATE TABLE IF NOT EXISTS owner (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        d.execute("""
            INSERT OR IGNORE INTO owner (id, username, password)
            VALUES (1, 'owner', 'owner123')
        """)
        d.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT,
                email TEXT,
                status TEXT,
                created_at TEXT
            )
        """)
        d.commit()


# =========================================================
# INITIALIZE DATABASE
# =========================================================
init_plans()
init_subscriptions()
init_db()


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
            cur.execute(
                "SELECT * FROM owner WHERE username=? AND password=?",
                (username, password)
            )
            user = cur.fetchone()

        if user:
            session["owner"] = True
            return redirect("/dashboard")

    return render_template("login.html")


# =========================================================
# OWNER DASHBOARD
# =========================================================
@app.route("/dashboard")
def dashboard():
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        cur = d.cursor()

        # ---- KPIs ----
        cur.execute("SELECT COUNT(*) FROM companies")
        total = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='ACTIVE'")
        active = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='PENDING'")
        pending = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM companies WHERE status='SUSPENDED'")
        suspended = cur.fetchone()[0]

        # ---- Companies ----
        cur.execute("SELECT * FROM companies")
        companies = cur.fetchall()

        # ---- Subscriptions ----
        cur.execute("""
            SELECT 
                c.id,
                c.company_name,
                p.id,
                p.name,
                p.price,
                s.status
            FROM subscriptions s
            JOIN companies c ON s.company_id = c.id
            JOIN plans p ON s.plan_id = p.id
        """)
        subscriptions = cur.fetchall()

        # ---- Plans ----
        cur.execute("SELECT id, name, price FROM plans")
        plans = cur.fetchall()

        # ---- Revenue ----
        cur.execute("""
            SELECT IFNULL(SUM(p.price),0)
            FROM subscriptions s
            JOIN plans p ON s.plan_id = p.id
            WHERE s.status='ACTIVE'
        """)
        mrr = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status='ACTIVE'")
        active_subs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status='TRIAL'")
        trials = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM subscriptions WHERE status='CANCELLED'")
        churned = cur.fetchone()[0]

    # ---- Greeting Logic ----
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good Morning"
    elif hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

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
        trials=trials,
        churned=churned
    )


# =========================================================
# APPROVE COMPANY
# =========================================================
@app.route("/approve/<int:company_id>")
def approve(company_id):
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        cur = d.cursor()

        cur.execute(
            "UPDATE companies SET status='ACTIVE' WHERE id=?",
            (company_id,)
        )

        cur.execute(
            "SELECT * FROM subscriptions WHERE company_id=?",
            (company_id,)
        )
        exists = cur.fetchone()

        if not exists:
            cur.execute("""
                INSERT INTO subscriptions (company_id, plan_id, status, start_date)
                VALUES (?, 1, 'ACTIVE', ?)
            """, (company_id, datetime.now().strftime("%Y-%m-%d")))

        d.commit()

    return redirect("/dashboard")


# =========================================================
# SUSPEND COMPANY
# =========================================================
@app.route("/suspend/<int:company_id>")
def suspend(company_id):
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        d.execute(
            "UPDATE companies SET status='SUSPENDED' WHERE id=?",
            (company_id,)
        )
        d.commit()

    return redirect("/dashboard")


# =========================================================
# CHANGE PLAN
# =========================================================
@app.route("/change-plan/<int:company_id>/<int:plan_id>")
def change_plan(company_id, plan_id):
    if not session.get("owner"):
        return redirect("/")

    with db() as d:
        d.execute("""
            UPDATE subscriptions
            SET plan_id=?
            WHERE company_id=?
        """, (plan_id, company_id))
        d.commit()

    return redirect("/dashboard")


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