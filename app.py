from flask import Flask, render_template, request, redirect, session, Response
import sqlite3
from datetime import datetime, timedelta
import os
import csv
import io

app = Flask(__name__)
app.secret_key = "cloudkitchen123"

DB_PATH = "cloud_kitchen.db"

@app.before_request
def before_request_checks():
    if request.endpoint == 'static':
        return
        
    # Check if user is banned
    if session.get("user_id") and request.endpoint != 'logout':
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT is_banned FROM users WHERE id=?", (session["user_id"],))
            user_banned = cursor.fetchone()
            conn.close()
            
            if user_banned and user_banned[0] == 1:
                session.clear()
                return render_template("login.html", error="Access Denied: Your account has been temporarily suspended.")
        except:
            pass

    if 'visited' not in session:
        session['visited'] = True
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("UPDATE site_stats SET visits = visits + 1 WHERE id = 1")
            
            # Log the visit
            ip_address = request.remote_addr
            visit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            username = session.get('user', 'Guest')
            cursor.execute("INSERT INTO visit_logs (ip_address, visit_time, username) VALUES (?, ?, ?)", (ip_address, visit_time, username))
            
            conn.commit()
            conn.close()
        except:
            pass


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        kitchen_name TEXT DEFAULT 'Cloud Kitchen Billing System',
        kitchen_address TEXT DEFAULT 'Bangalore, India',
        is_owner INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        price REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        customer_name TEXT,
        customer_number TEXT,
        item_name TEXT,
        quantity INTEGER,
        total REAL,
        date TEXT,
        daily_order_number INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS site_stats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        visits INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS visit_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip_address TEXT,
        visit_time TEXT,
        username TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('announcement', '')")

    cursor.execute("SELECT COUNT(*) FROM site_stats")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO site_stats (visits) VALUES (0)")

    conn.commit()

    cursor.execute("PRAGMA table_info(orders)")
    column_names = [row[1] for row in cursor.fetchall()]
    if "daily_order_number" not in column_names:
        cursor.execute("ALTER TABLE orders ADD COLUMN daily_order_number INTEGER DEFAULT 0")
        conn.commit()

    migrate_daily_order_numbers(conn)
    conn.close()


def migrate_daily_order_numbers(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, date FROM orders ORDER BY user_id, date ASC")
    orders = cursor.fetchall()

    last_user_id = None
    last_date = None
    current_sequence = 0

    for order in orders:
        order_id = order[0]
        user_id = order[1]
        order_date = order[2].split(" ")[0] if order[2] else ""

        if user_id != last_user_id or order_date != last_date:
            current_sequence = 1
            last_user_id = user_id
            last_date = order_date
        else:
            current_sequence += 1

        cursor.execute(
            "UPDATE orders SET daily_order_number=? WHERE id=?",
            (current_sequence, order_id)
        )

    conn.commit()

    # Migrate users table to add kitchen_name and kitchen_address
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [row[1] for row in cursor.fetchall()]
    if "kitchen_name" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN kitchen_name TEXT DEFAULT 'Cloud Kitchen Billing System'")
        conn.commit()
    if "kitchen_address" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN kitchen_address TEXT DEFAULT 'Bangalore, India'")
        conn.commit()
    if "is_owner" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_owner INTEGER DEFAULT 0")
        conn.commit()
    if "is_banned" not in user_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")
        conn.commit()

    conn.close()


# Owner registration code (change this to your secret code)
OWNER_REGISTRATION_CODE = "admin123"

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        kitchen_name = request.form.get("kitchen_name", "Cloud Kitchen Billing System")
        kitchen_address = request.form.get("kitchen_address", "Bangalore, India")
        owner_code = request.form.get("owner_code", "")

        # Check if owner code is correct
        is_owner = 1 if owner_code == OWNER_REGISTRATION_CODE else 0

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, password, kitchen_name, kitchen_address, is_owner) VALUES (?, ?, ?, ?, ?)",
                (username, password, kitchen_name, kitchen_address, is_owner)
            )
            conn.commit()
            conn.close()
            return redirect("/login")

        except:
            conn.close()
            return render_template("register.html", error="User already exists")

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username,password)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["user"] = user[1]
            session["user_id"] = user[0]
            return redirect("/")
        else:
            return render_template("login.html", error="Invalid Login")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin")
def admin():
    if not session.get("user_id"):
        return redirect("/login")
    
    user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if current user is owner
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied: Only website owners can access this page", 403
    
    # Get all registered users
    cursor.execute("SELECT id, username, password, kitchen_name, kitchen_address, is_owner, is_banned FROM users ORDER BY id DESC")
    all_users = cursor.fetchall()
    
    # Global Stats
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*), COALESCE(SUM(total), 0) FROM orders")
    stats = cursor.fetchone()
    global_orders = stats[0] if stats else 0
    global_revenue = stats[1] if stats else 0

    try:
        cursor.execute("SELECT visits FROM site_stats WHERE id = 1")
        site_visits_row = cursor.fetchone()
        site_visits = site_visits_row[0] if site_visits_row else 0
    except:
        site_visits = 0

    try:
        cursor.execute("SELECT ip_address, visit_time, username FROM visit_logs ORDER BY id DESC LIMIT 50")
        recent_visits = cursor.fetchall()
    except:
        recent_visits = []

    try:
        cursor.execute("SELECT value FROM settings WHERE key='announcement'")
        announcement_row = cursor.fetchone()
        announcement = announcement_row[0] if announcement_row else ""
    except:
        announcement = ""

    conn.close()
    
    return render_template("admin.html", users=all_users, total_users=total_users, global_orders=global_orders, global_revenue=global_revenue, site_visits=site_visits, recent_visits=recent_visits, announcement=announcement)


# ---------------- IMPERSONATE USER (ADMIN) ----------------
@app.route("/admin/impersonate/<int:target_user_id>")
def admin_impersonate(target_user_id):
    if not session.get("user_id"):
        return redirect("/login")
    
    user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if current user is owner
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
        
    # Get target user info
    cursor.execute("SELECT username FROM users WHERE id=?", (target_user_id,))
    target_user = cursor.fetchone()
    
    conn.close()
    
    if target_user:
        session["user_id"] = target_user_id
        session["user"] = target_user[0]
        
    return redirect("/")



# ---------------- DELETE USER (ADMIN) ----------------
@app.route("/admin/delete/<int:user_id>")
def admin_delete_user(user_id):
    if not session.get("user_id"):
        return redirect("/login")
    
    current_user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if current user is owner
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
    
    # Prevent owner from deleting themselves
    if user_id == current_user_id:
        conn.close()
        return redirect("/admin?error=Cannot%20delete%20your%20own%20account")
    
    # Delete user items
    cursor.execute("DELETE FROM items WHERE user_id=?", (user_id,))
    
    # Delete user orders
    cursor.execute("DELETE FROM orders WHERE user_id=?", (user_id,))
    
    # Delete user
    cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
    
    conn.commit()
    conn.close()
    
    return redirect("/admin")


# ---------------- TOGGLE BAN USER (ADMIN) ----------------
@app.route("/admin/toggle_ban/<int:user_id>")
def admin_toggle_ban(user_id):
    if not session.get("user_id"):
        return redirect("/login")
    
    current_user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if current user is owner
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
    
    # Prevent owner from banning themselves
    if user_id == current_user_id:
        conn.close()
        return redirect("/admin?error=Cannot%20ban%20your%20own%20account")
        
    cursor.execute("SELECT is_banned FROM users WHERE id=?", (user_id,))
    target_user = cursor.fetchone()
    
    if target_user:
        new_status = 0 if target_user[0] == 1 else 1
        cursor.execute("UPDATE users SET is_banned=? WHERE id=?", (new_status, user_id))
        conn.commit()
        
    conn.close()
    return redirect("/admin")


# ---------------- RESET PASSWORD (ADMIN) ----------------
@app.route("/admin/reset_password", methods=["POST"])
def admin_reset_password():
    if not session.get("user_id"):
        return redirect("/login")
    
    current_user_id = session.get("user_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if current user is owner
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
    
    # Get the form data
    user_id = request.form.get("user_id")
    new_password = request.form.get("new_password")
    confirm_password = request.form.get("confirm_password")
    
    # Validate passwords match
    if new_password != confirm_password:
        conn.close()
        return redirect("/admin?error=Passwords%20do%20not%20match")
    
    # Validate password length
    if len(new_password) < 4:
        conn.close()
        return redirect("/admin?error=Password%20must%20be%20at%20least%204%20characters")
    
    # Update password
    cursor.execute("UPDATE users SET password=? WHERE id=?", (new_password, user_id))
    conn.commit()
    conn.close()
    
    return redirect("/admin?success=Password%20reset%20successfully")

# ---------------- BROADCAST ANNOUNCEMENT (ADMIN) ----------------
@app.route("/admin/announcement", methods=["POST"])
def admin_announcement():
    if not session.get("user_id"):
        return redirect("/login")
    
    current_user_id = session.get("user_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
        
    announcement = request.form.get("announcement", "")
    
    cursor.execute("UPDATE settings SET value=? WHERE key='announcement'", (announcement,))
    conn.commit()
    conn.close()
    
    return redirect("/admin?success=Announcement%20updated")

# ---------------- EXPORT USERS (ADMIN) ----------------
@app.route("/admin/export/users")
def export_users():
    if not session.get("user_id"):
        return redirect("/login")
        
    current_user_id = session.get("user_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
        
    cursor.execute("SELECT id, username, kitchen_name, kitchen_address, is_owner FROM users ORDER BY id DESC")
    users = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Username", "Kitchen Name", "Kitchen Address", "Role"])
    for user in users:
        role = "Owner" if user[4] == 1 else "User"
        writer.writerow([user[0], user[1], user[2], user[3], role])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=users_export.csv"}
    )

# ---------------- EXPORT VISITS (ADMIN) ----------------
@app.route("/admin/export/visits")
def export_visits():
    if not session.get("user_id"):
        return redirect("/login")
        
    current_user_id = session.get("user_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_owner FROM users WHERE id=?", (current_user_id,))
    user_info = cursor.fetchone()
    
    if not user_info or user_info[0] != 1:
        conn.close()
        return "Access Denied", 403
        
    cursor.execute("SELECT id, ip_address, visit_time, username FROM visit_logs ORDER BY id DESC")
    visits = cursor.fetchall()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "IP Address", "Timestamp", "Username"])
    for visit in visits:
        writer.writerow([visit[0], visit[1], visit[2], visit[3]])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=visits_export.csv"}
    )

# ---------------- HOME ----------------
@app.route("/")
def index():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, price FROM items WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (user_id,))
    total_orders = cursor.fetchone()[0] or 0

    today_date = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM orders WHERE user_id=? AND date(date)=?",
        (user_id, today_date)
    )
    today_orders, today_revenue = cursor.fetchone()

    # Get user's kitchen info
    cursor.execute(
        "SELECT kitchen_name, kitchen_address, is_owner FROM users WHERE id=?",
        (user_id,)
    )
    user_info = cursor.fetchone()
    kitchen_name = user_info[0] if user_info else "Cloud Kitchen Billing System"
    kitchen_address = user_info[1] if user_info else "Bangalore, India"
    is_owner = user_info[2] if user_info else 0

    # 7-Day Revenue Data
    chart_labels = []
    chart_data = []
    now = datetime.now()
    
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        chart_labels.append(day.strftime("%b %d"))
        
        cursor.execute("SELECT COALESCE(SUM(total), 0) FROM orders WHERE user_id=? AND date(date)=?", (user_id, day_str))
        chart_data.append(cursor.fetchone()[0])

    try:
        cursor.execute("SELECT value FROM settings WHERE key='announcement'")
        announcement_row = cursor.fetchone()
        announcement = announcement_row[0] if announcement_row else ""
    except:
        announcement = ""

    conn.close()

    return render_template(
        "index.html",
        items=items,
        current_date=now.strftime("%d %B %Y"),
        current_time=now.strftime("%I:%M %p"),
        username=session.get("user"),
        total_orders=total_orders,
        today_orders=today_orders,
        today_revenue=today_revenue,
        kitchen_name=kitchen_name,
        kitchen_address=kitchen_address,
        is_owner=is_owner,
        chart_labels=chart_labels,
        chart_data=chart_data,
        announcement=announcement
    )


# ---------------- ADD ITEM ----------------
@app.route("/add", methods=["GET","POST"])
def add_item():
    if not session.get("user_id"):
        return redirect("/login")

    if request.method == "POST":

        name = request.form.get("name")
        price = request.form.get("price")
        user_id = session.get("user_id")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO items (user_id,name,price) VALUES (?,?,?)",
            (user_id,name,price)
        )

        conn.commit()
        conn.close()

        return redirect("/")

    return render_template("add_item.html")


# ---------------- UPDATE SETTINGS ----------------
@app.route("/update_settings", methods=["POST"])
def update_settings():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")
    kitchen_name = request.form.get("kitchen_name")
    kitchen_address = request.form.get("kitchen_address")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE users SET kitchen_name=?, kitchen_address=? WHERE id=?",
        (kitchen_name, kitchen_address, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- DELETE ITEM ----------------
@app.route("/delete/<int:id>")
def delete(id):
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM items WHERE id=? AND user_id=?",
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/")


# ---------------- EDIT ITEM ----------------
@app.route("/edit_price/<int:id>", methods=["GET","POST"])
def edit_price(id):
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, price FROM items WHERE id=? AND user_id=?",
        (id, user_id)
    )
    item = cursor.fetchone()

    if not item:
        conn.close()
        return redirect("/")

    if request.method == "POST":

        price = request.form.get("price")

        cursor.execute(
            "UPDATE items SET price=? WHERE id=? AND user_id=?",
            (price, id, user_id)
        )

        conn.commit()
        conn.close()

        return redirect("/")

    conn.close()
    return render_template("edit_price.html", item=item)


# ---------------- PLACE ORDER ----------------
@app.route("/order", methods=["GET","POST"])
def place_order():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, price FROM items WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    error = None

    if request.method == "POST":

        customer_name = request.form.get("customer_name", "").strip()
        customer_number = request.form.get("customer_number", "").strip()

        item_ids = request.form.getlist("item_id")
        quantities = request.form.getlist("quantity")

        total_amount = 0
        total_quantity = 0
        order_items = []

        for item_id, qty in zip(item_ids, quantities):
            try:
                qty_value = int(qty)
            except (ValueError, TypeError):
                qty_value = 0

            if qty_value > 0:
                cursor.execute(
                    "SELECT name,price FROM items WHERE id=? AND user_id=?",
                    (item_id, user_id)
                )

                item = cursor.fetchone()

                if item:
                    subtotal = item[1] * qty_value
                    total_amount += subtotal
                    total_quantity += qty_value
                    order_items.append(f"{item[0]} x {qty_value}")

        if not customer_name or not customer_number:
            error = "Customer name and phone number are required."
        elif total_quantity == 0:
            error = "Select at least one item quantity to place an order."

        if error is None:
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            items_text = ", ".join(order_items)
            today_date = datetime.now().strftime("%Y-%m-%d")

            cursor.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id=? AND date(date)=?",
                (user_id, today_date)
            )
            daily_count = cursor.fetchone()[0] or 0
            daily_order_number = daily_count + 1

            cursor.execute(
                """INSERT INTO orders
                (user_id,customer_name,customer_number,item_name,quantity,total,date,daily_order_number)
                VALUES (?,?,?,?,?,?,?,?)""",
                (user_id, customer_name, customer_number, items_text, total_quantity, total_amount, date, daily_order_number)
            )

            conn.commit()

            order_id = cursor.lastrowid
            conn.close()

            return redirect(f"/bill/{order_id}")

    conn.close()
    return render_template("place_order.html", items=items, error=error)


# ---------------- BILL ----------------
@app.route("/bill/<int:order_id>")
def bill(order_id):
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE id=? AND user_id=?",
        (order_id, user_id)
    )

    order = cursor.fetchone()

    # Get user's kitchen info
    cursor.execute(
        "SELECT kitchen_name, kitchen_address FROM users WHERE id=?",
        (user_id,)
    )
    user_info = cursor.fetchone()
    kitchen_name = user_info[0] if user_info else "Cloud Kitchen Billing System"
    kitchen_address = user_info[1] if user_info else "Bangalore, India"

    conn.close()

    if order:
        subtotal = order[6]
        gst = round(subtotal * 0.05, 2)
        total = round(subtotal + gst, 2)
    else:
        gst = 0
        total = 0

    return render_template(
        "bill.html",
        order=order,
        gst=gst,
        total=total,
        kitchen_name=kitchen_name,
        kitchen_address=kitchen_address
    )


# ---------------- VIEW ORDERS ----------------
@app.route("/orders")
def view_orders():
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY date DESC, daily_order_number DESC",
        (user_id,)
    )

    orders = cursor.fetchall()
    conn.close()

    return render_template("orders.html", orders=orders)


# ---------------- DELETE ORDER ----------------
@app.route("/delete_order/<int:id>")
def delete_order(id):
    if not session.get("user_id"):
        return redirect("/login")

    user_id = session.get("user_id")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM orders WHERE id=? AND user_id=?",
        (id, user_id)
    )

    conn.commit()
    conn.close()

    return redirect("/orders")
# ---------------- RUN APP ----------------
if __name__ == "__main__":

    init_db()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)