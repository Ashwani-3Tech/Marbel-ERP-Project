from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import qrcode
import os
import urllib.parse
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw

app = Flask(__name__, static_folder='static')
app.secret_key = "ashu_super_secret_master_key"

UPLOAD_FOLDER = 'static/uploads'
QR_FOLDER = 'qr_codes'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('marble_inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS Products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT, length REAL, height REAL, width REAL, thickness REAL, price_per_sqft REAL, application TEXT, finish TEXT, description TEXT, image_path TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL, assigned_category TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, mobile TEXT NOT NULL, email TEXT, purpose TEXT, ref_name TEXT, ref_mobile TEXT, commission_rate TEXT, birthday TEXT, anniversary TEXT, notes TEXT, consultant_username TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS Wishlist (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, product_id INTEGER NOT NULL, quantity INTEGER DEFAULT 1, purpose TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS FollowUps (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, consultant_username TEXT NOT NULL, reminder_type TEXT NOT NULL, specific_date TEXT, status TEXT DEFAULT 'Pending')''')
    
    # NEW: Orders & Analytics Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            consultant_username TEXT NOT NULL,
            items_summary TEXT NOT NULL,
            total_amount REAL NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    admin = conn.execute('SELECT * FROM Users WHERE username = "admin"').fetchone()
    if not admin: conn.execute('INSERT INTO Users (username, password, role) VALUES (?, ?, ?)', ('admin', 'admin123', 'Super Admin'))
    conn.commit()
    conn.close()

setup_database()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_db_connection().execute('SELECT * FROM Users WHERE username = ? AND password = ?', (request.form['username'], request.form['password'])).fetchone()
        if user:
            session['user_id'], session['role'], session['username'], session['assigned_category'] = user['id'], user['role'], user['username'], user['assigned_category']
            if user['role'] == 'Super Admin': return redirect(url_for('index'))
            elif user['role'] == 'Consultant': return redirect(url_for('consultant_panel'))
            elif user['role'] == 'Customer': return redirect(url_for('customer_panel'))
            elif user['role'] == 'Assistant Admin': return redirect(url_for('index'))
        else: flash("Invalid credentials! Please try again.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    search_query, category_filter = request.args.get('search', ''), request.args.get('category', '')
    query, params = "SELECT * FROM Products WHERE 1=1", []
    if search_query:
        query += " AND (name LIKE ? OR application LIKE ? OR finish LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    if category_filter: query += " AND category = ?"; params.append(category_filter)
        
    conn = get_db_connection()
    products = conn.execute(query, params).fetchall()
    users = conn.execute('SELECT * FROM Users').fetchall()
    
    # NEW: Fetch Analytics Data for Super Admin
    orders = conn.execute('SELECT * FROM Orders ORDER BY order_date DESC').fetchall()
    total_revenue = conn.execute('SELECT SUM(total_amount) FROM Orders').fetchone()[0] or 0
    total_orders = len(orders)
    conn.close()
    
    return render_template('index.html', products=products, users=users, orders=orders, total_revenue=total_revenue, total_orders=total_orders)

@app.route('/add_user', methods=['POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        conn.execute('INSERT INTO Users (username, password, role, assigned_category) VALUES (?, ?, ?, ?)', (request.form['username'], request.form['password'], request.form['role'], request.form.get('assigned_category', '')))
        conn.commit()
    except sqlite3.IntegrityError: flash("That Username already exists!")
    finally: conn.close()
    return redirect(url_for('index'))

@app.route('/delete_user/<int:id>')
def delete_user(id):
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM Users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add_product():
    if 'user_id' not in session: return redirect(url_for('login'))
    f = request.files['image']
    filename = secure_filename(f.filename) if f else ""
    if f: f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO Products (name, category, length, height, width, thickness, price_per_sqft, application, finish, image_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                   (request.form['name'], request.form['category'], float(request.form['price']), request.form['l'], request.form['h'], request.form['w'], request.form['t'], request.form['application'], request.form['finish'], filename))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    qr_img = qrcode.make(f"ID: {product_id} | Name: {request.form['name']} | Cat: {request.form['category']}").convert('RGB')
    sticker = Image.new('RGB', (qr_img.size[0], qr_img.size[1] + 50), 'white')
    sticker.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(sticker)
    draw.text((10, qr_img.size[1] + 5), f"Name: {request.form['name']}", fill="black")
    draw.text((10, qr_img.size[1] + 25), f"Lot No: {product_id}", fill="black")
    sticker.save(f"{QR_FOLDER}/product_{product_id}.png")
    return redirect(url_for('index'))

@app.route('/register_customer', methods=['POST'])
def register_customer():
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('INSERT INTO Customers (name, mobile, email, purpose, ref_name, ref_mobile, commission_rate, birthday, anniversary, notes, consultant_username) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                 (request.form['name'], request.form['mobile'], request.form['email'], request.form['purpose'], request.form['ref_name'], request.form['ref_mobile'], request.form['commission_rate'], request.form['birthday'], request.form['anniversary'], request.form['notes'], session['username']))
    conn.commit()
    conn.close()
    flash(f"Customer {request.form['name']} Registered Successfully!")
    return redirect(url_for('consultant_panel'))

@app.route('/select_customer/<int:customer_id>')
def select_customer(customer_id):
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    session['active_customer_id'] = customer_id
    return redirect(url_for('consultant_panel'))

@app.route('/clear_customer')
def clear_customer():
    session.pop('active_customer_id', None)
    return redirect(url_for('consultant_panel'))

@app.route('/add_to_wishlist/<int:product_id>')
def add_to_wishlist(product_id):
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    if 'active_customer_id' not in session: return redirect(url_for('consultant_panel'))
    conn = get_db_connection()
    conn.execute('INSERT INTO Wishlist (customer_id, product_id, quantity) VALUES (?, ?, 1)', (session['active_customer_id'], product_id))
    conn.commit()
    conn.close()
    flash("Product added to Customer Wishlist!")
    return redirect(url_for('consultant_panel'))

@app.route('/remove_from_wishlist/<int:wishlist_id>')
def remove_from_wishlist(wishlist_id):
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM Wishlist WHERE id = ?', (wishlist_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('consultant_panel'))

@app.route('/checkout')
def checkout():
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    if 'active_customer_id' not in session: return redirect(url_for('consultant_panel'))
    conn = get_db_connection()
    customer = conn.execute('SELECT * FROM Customers WHERE id = ?', (session['active_customer_id'],)).fetchone()
    wishlist = conn.execute('SELECT p.name, p.price_per_sqft FROM Wishlist w JOIN Products p ON w.product_id = p.id WHERE w.customer_id = ?', (session['active_customer_id'],)).fetchall()
    
    if not wishlist:
        conn.close()
        flash("Cannot checkout an empty cart!")
        return redirect(url_for('consultant_panel'))
        
    msg = f"Hello {customer['name']},\n\nHere is your requested quotation from our Premium Marble Collection:\n\n"
    items_summary = ""
    total_amount = 0
    
    for i, item in enumerate(wishlist, 1):
        price = item['price_per_sqft']
        if 'Green' in customer['commission_rate']: price = round(price * 0.9, 2)
        elif 'Red' in customer['commission_rate']: price = round(price * 0.95, 2)
        elif 'Yellow' in customer['commission_rate']: price = round(price * 0.8, 2)
        
        msg += f"🔸 {item['name']}: ₹{price} / SqFt\n"
        items_summary += f"{item['name']} (₹{price}), "
        total_amount += price

    msg += "\nPlease let us know if you would like to proceed with this order!\n\nBest Regards,\nYour Consultant Team"
    
    # NEW: Save official receipt to Orders table before clearing cart!
    conn.execute('INSERT INTO Orders (customer_name, consultant_username, items_summary, total_amount) VALUES (?, ?, ?, ?)',
                 (customer['name'], session['username'], items_summary.strip(', '), total_amount))

    conn.execute('DELETE FROM Wishlist WHERE customer_id = ?', (session['active_customer_id'],))
    conn.commit()
    conn.close()
    return redirect(f"https://wa.me/91{customer['mobile']}?text={urllib.parse.quote(msg)}")

@app.route('/set_followup', methods=['POST'])
def set_followup():
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('INSERT INTO FollowUps (customer_id, consultant_username, reminder_type, specific_date) VALUES (?, ?, ?, ?)', (request.form['customer_id'], session['username'], request.form['reminder_type'], request.form.get('specific_date', '')))
    conn.commit()
    conn.close()
    flash("Reminder set successfully!")
    return redirect(url_for('consultant_panel'))

@app.route('/complete_followup/<int:f_id>')
def complete_followup(f_id):
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute("UPDATE FollowUps SET status = 'Completed' WHERE id = ?", (f_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('consultant_panel'))

@app.route('/consultant')
def consultant_panel():
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']: return redirect(url_for('login'))
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM Products').fetchall()
    customers = conn.execute('SELECT * FROM Customers WHERE consultant_username = ?', (session['username'],)).fetchall()
    followups = conn.execute("SELECT f.id, f.reminder_type, f.specific_date, c.name, c.mobile FROM FollowUps f JOIN Customers c ON f.customer_id = c.id WHERE f.consultant_username = ? AND f.status = 'Pending'", (session['username'],)).fetchall()
    
    active_customer = None
    wishlist_items = []
    if 'active_customer_id' in session:
        active_customer = conn.execute('SELECT * FROM Customers WHERE id = ?', (session['active_customer_id'],)).fetchone()
        wishlist_items = conn.execute('SELECT w.id as wishlist_id, p.name, p.price_per_sqft, p.image_path, p.category FROM Wishlist w JOIN Products p ON w.product_id = p.id WHERE w.customer_id = ?', (session['active_customer_id'],)).fetchall()
        
    conn.close()
    return render_template('consultant.html', products=products, customers=customers, active_customer=active_customer, wishlist_items=wishlist_items, followups=followups)

@app.route('/customer')
def customer_panel():
    return render_template('customer.html', products=get_db_connection().execute('SELECT * FROM Products').fetchall())

@app.route('/delete/<int:id>')
def delete_product(id):
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    conn = get_db_connection()
    product = conn.execute('SELECT image_path FROM Products WHERE id = ?', (id,)).fetchone()
    if product and product['image_path'] and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], product['image_path'])): os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product['image_path']))
    conn.execute('DELETE FROM Products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/bulk_update', methods=['POST'])
def bulk_update():
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE Products SET price_per_sqft = price_per_sqft * (1 + ?)', (float(request.form['percent']) / 100,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)