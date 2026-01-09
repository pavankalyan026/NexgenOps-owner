from flask import Flask, render_template, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import uuid

app = Flask(__name__)
app.secret_key = "nexgenops-secret-key"

OWNER_DB = "owner.db"
POWER_DB = "power.db"

# =========================================================
# DATABASE CONNECTIONS
# =========================================================
def owner_db():
    return sqlite3.connect(OWNER_DB, check_same_thread=False)

def power_db():
    return sqlite3.connect(POWER_DB, check_same_thread=False)

# =========================================================
# INIT DATABASES
# =========================================================
def init_owner_db():
    with owner_db() as d:
        cur = d.cursor()

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
        INSERT OR IGNORE INTO plans VALUES
            (1,'Free',0,3,2),
            (2,'Professional',7999,50,25),
            (3,'Enterprise',24999,-1,-1)
        """)

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

init_owner_db()
init_power_db()

# =========================================================
# OWNER LOGIN
# =========================================================
@app.route("/", methods=["GET", "POST"])
def owner_login():
    if request.method == "POST":
        with owner_db() as d:
            cur = d.cursor()
            cur.execute(
                "SELECT password FROM owner WHERE username=?",
                (request.form["username"],)
            )
            row = cur.fetchone()

        if row and check_password_hash(row[0], request.form["password"]):
            session["owner"] = True
            return redirect("/owner/dashboard")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

# =========================================================
# OWNER DASHBOARD
# =========================================================
@app.route("/owner/dashboard")
def owner_dashboard():
    if not session.get("owner"):
        return redirect("/")

    with owner_db() as d:
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

    greeting = (
        "Good Morning" if datetime.now().hour < 12 else
        "Good Afternoon" if datetime.now().hour < 17 else
        "Good Evening"
    )

    return render_template(
        "owner_dashboard.html",
        greeting=greeting,
        total=total,
        active=active,
        pending=pending,
        suspended=suspended,
        companies=companies
    )

# =========================================================
# COMPANY REGISTRATION
# =========================================================
@app.route("/company/register", methods=["GET","POST"])
def company_register():
    if request.method == "POST":
        with owner_db() as d:
            d.execute("""
            INSERT INTO companies (
                company_name,email,status,created_at,
                industry,company_size,admin_name,admin_mobile,
                country,state,city,timezone,
                requested_plan,expected_users,expected_meters
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
                request.form["expected_users"],
                request.form["expected_meters"]
            ))
            d.commit()
        return redirect("/owner/dashboard")

    return render_template("company_register.html")

# =========================================================
# APPROVE COMPANY (SYNC TO POWER DASHBOARD)
# =========================================================
@app.route("/approve/<int:company_id>")
def approve(company_id):
    if not session.get("owner"):
        return redirect("/")

    company_code = "NG-" + uuid.uuid4().hex[:8].upper()

    with owner_db() as d:
        cur = d.cursor()
        cur.execute("""
            UPDATE companies SET status='ACTIVE', company_code=?
            WHERE id=?
        """, (company_code, company_id))

        cur.execute("SELECT company_name,email FROM companies WHERE id=?", (company_id,))
        name, email = cur.fetchone()

        cur.execute("""
            INSERT OR IGNORE INTO subscriptions
            (company_id,plan_id,status,start_date)
            VALUES (?,1,'ACTIVE',?)
        """, (company_id, datetime.now().strftime("%Y-%m-%d")))

        d.commit()

    with power_db() as pd:
        cur = pd.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO pd_companies
            (company_code,company_name,status)
            VALUES (?,?, 'ACTIVE')
        """, (company_code, name))

        cur.execute("SELECT id FROM pd_companies WHERE company_code=?", (company_code,))
        pd_company_id = cur.fetchone()[0]

        cur.execute("""
            INSERT OR IGNORE INTO pd_users
            (company_id,username,password,role)
            VALUES (?,?,?, 'ADMIN')
        """, (pd_company_id, email, generate_password_hash("admin123")))

        pd.commit()

    return redirect("/owner/dashboard")

# =========================================================
# POWER DASHBOARD LOGIN
# =========================================================
@app.route("/power/login", methods=["GET","POST"])
def power_login():
    if request.method == "POST":
        with power_db() as d:
            cur = d.cursor()
            cur.execute("""
                SELECT u.id,u.password,u.role,c.id,c.status,c.company_name
                FROM pd_users u
                JOIN pd_companies c ON u.company_id=c.id
                WHERE u.username=?
            """, (request.form["username"],))
            row = cur.fetchone()

        if not row:
            return render_template("power_login.html", error="Invalid login")

        uid, hashed, role, cid, status, cname = row

        if status != "ACTIVE":
            return render_template("power_login.html", error="Company suspended")

        if not check_password_hash(hashed, request.form["password"]):
            return render_template("power_login.html", error="Invalid login")

        session["pd_user"] = uid
        session["pd_role"] = role
        session["pd_company"] = cname

        return redirect("/power/dashboard")

    return render_template("power_login.html")

# =========================================================
# POWER DASHBOARD
# =========================================================
@app.route("/power/dashboard")
def power_dashboard():
    if not session.get("pd_user"):
        return redirect("/power/login")

    return render_template(
        "power_dashboard.html",
        company=session["pd_company"],
        role=session["pd_role"]
    )

# =========================================================
# LOGOUTS
# =========================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/power/logout")
def power_logout():
    session.clear()
    return redirect("/power/login")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
