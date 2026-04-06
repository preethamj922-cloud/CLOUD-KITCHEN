from flask import Flask, render_template, request, redirect, session, flash
import sqlite3
from datetime import datetime
import os
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-in-production")

DB_PATH = os.environ.get("DB_PATH", "cloud_kitchen.db")


# ---------------- HELPERS ----------------
def hash_password(password):
    return generate_password_hash(password)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


# ---------------- DATABASE ----------------
def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        customer_name TEXT,
        customer_number TEXT,
        item_name TEXT,
        quantity INTEGER,
        total REAL,
        date TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    conn.commit()
    conn.close()


# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("register.html")

        if len(password) < 4:
            flash("Password must be at least 4 characters.", "error")
            return render_template("register.html")

        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hash_password(password))
            )
            conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect("/login")
        except sqlite3.IntegrityError:
            flash("Username already taken.", "error")
            return render_template("register.html")
        finally:
            conn.close()

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Please enter both fields.", "error")
            return render_template("login.html")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user"] = user["username"]
            session["user_id"] = user["id"]
            return redirect("/")
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- HOME ----------------
@app.route("/")
@login_required
def index():
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM items WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    # Stats
    cursor.execute("""
        SELECT COUNT(*) as cnt, COALESCE(SUM(total),0) as rev 
        FROM orders WHERE user_id=?
    """, (user_id,))
    stats = cursor.fetchone()

    # Today's orders FIXED
    cursor.execute("""
        SELECT COUNT(*) as cnt 
        FROM orders 
        WHERE user_id=? AND DATE(date)=DATE('now')
    """, (user_id,))
    today_orders = cursor.fetchone()

    conn.close()

    now = datetime.now()
    return render_template(
        "index.html",
        items=items,
        current_date=now.strftime("%d %B %Y"),
        current_time=now.strftime("%I:%M %p"),
        username=session["user"],
        total_orders=stats["cnt"],
        total_revenue=round(stats["rev"], 2),
        today_orders=today_orders["cnt"]
    )


# ---------------- ADD ITEM ----------------
@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price_raw = request.form.get("price", "").strip()

        if not name:
            flash("Item name is required.", "error")
            return render_template("add_item.html")

        try:
            price = float(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid price.", "error")
            return render_template("add_item.html")

        conn = get_db()
        conn.execute(
            "INSERT INTO items (user_id, name, price) VALUES (?,?,?)",
            (session["user_id"], name, price)
        )
        conn.commit()
        conn.close()
        flash(f"{name} added to menu!", "success")
        return redirect("/")

    return render_template("add_item.html")


# ---------------- DELETE ITEM ----------------
@app.route("/delete/<int:id>")
@login_required
def delete(id):
    conn = get_db()
    conn.execute(
        "DELETE FROM items WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )
    conn.commit()
    conn.close()
    flash("Item removed.", "success")
    return redirect("/")


# ---------------- EDIT ITEM ----------------
@app.route("/edit_price/<int:id>", methods=["GET", "POST"])
@login_required
def edit_price(id):
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM items WHERE id=? AND user_id=?", (id, user_id))
    item = cursor.fetchone()

    if not item:
        conn.close()
        flash("Item not found.", "error")
        return redirect("/")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price_raw = request.form.get("price", "").strip()

        if not name:
            flash("Item name required.", "error")
            return render_template("edit_price.html", item=item)

        try:
            price = float(price_raw)
            if price < 0:
                raise ValueError
        except ValueError:
            flash("Invalid price.", "error")
            return render_template("edit_price.html", item=item)

        conn.execute(
            "UPDATE items SET name=?, price=? WHERE id=? AND user_id=?",
            (name, price, id, user_id)
        )
        conn.commit()
        conn.close()
        flash("Item updated!", "success")
        return redirect("/")

    conn.close()
    return render_template("edit_price.html", item=item)


# ---------------- PLACE ORDER ----------------
@app.route("/order", methods=["GET", "POST"])
@login_required
def place_order():
    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM items WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    if not items:
        conn.close()
        flash("Add menu items first.", "error")
        return redirect("/add")

    if request.method == "POST":
        customer_name = request.form.get("customer_name", "").strip()
        customer_number = request.form.get("customer_number", "").strip()

        if not customer_name:
            flash("Customer name required.", "error")
            return render_template("place_order.html", items=items)

        item_ids = request.form.getlist("item_id")
        quantities = request.form.getlist("quantity")

        total_amount = 0
        total_quantity = 0
        order_items = []

        for item_id, qty in zip(item_ids or [], quantities or []):
            try:
                qty = int(qty)
            except:
                qty = 0

            if qty > 0:
                cursor.execute(
                    "SELECT name, price FROM items WHERE id=? AND user_id=?",
                    (item_id, user_id)
                )
                item = cursor.fetchone()
                if item:
                    subtotal = item["price"] * qty
                    total_amount += subtotal
                    total_quantity += qty
                    order_items.append(f"{item['name']} x{qty}")

        if total_quantity == 0:
            flash("Select at least one item.", "error")
            return render_template("place_order.html", items=items)

        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO orders
            (user_id, customer_name, customer_number, item_name, quantity, total, date)
            VALUES (?,?,?,?,?,?,?)
        """, (
            user_id,
            customer_name,
            customer_number,
            ", ".join(order_items),
            total_quantity,
            total_amount,
            date
        ))

        conn.commit()
        order_id = cursor.lastrowid
        conn.close()

        return redirect(f"/bill/{order_id}")

    conn.close()
    return render_template("place_order.html", items=items)


# ---------------- BILL ----------------
@app.route("/bill/<int:order_id>")
@login_required
def bill(order_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE id=? AND user_id=?",
        (order_id, session["user_id"])
    )
    order = cursor.fetchone()
    conn.close()

    if not order:
        flash("Order not found.", "error")
        return redirect("/orders")

    subtotal = order["total"]
    gst = round(subtotal * 0.05, 2)
    total = round(subtotal + gst, 2)

    return render_template(
        "bill.html",
        order=order,
        subtotal=subtotal,
        gst=gst,
        total=total,
        kitchen_name="Cloud Kitchen",
        kitchen_address="Bangalore, India"
    )


# ---------------- ORDER DETAILS ----------------
@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE id=? AND user_id=?",
        (order_id, session["user_id"])
    )
    order = cursor.fetchone()
    conn.close()

    if not order:
        flash("Order not found.", "error")
        return redirect("/orders")

    subtotal = order["total"]
    gst = round(subtotal * 0.05, 2)
    total = round(subtotal + gst, 2)

    return render_template(
        "order_detail.html",
        order=order,
        subtotal=subtotal,
        gst=gst,
        total=total
    )


# ---------------- VIEW ORDERS ----------------
@app.route("/orders")
@login_required
def view_orders():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",
        (session["user_id"],)
    )
    orders = cursor.fetchall()
    conn.close()

    return render_template("orders.html", orders=orders)


# ---------------- DELETE ORDER ----------------
@app.route("/delete_order/<int:id>")
@login_required
def delete_order(id):
    conn = get_db()
    conn.execute(
        "DELETE FROM orders WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )
    conn.commit()
    conn.close()
    flash("Order deleted.", "success")
    return redirect("/orders")


# ---------------- RUN ----------------
init_db()  # ✅ RUNS ALWAYS

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)