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
    conn.execute('''CREATE TABLE IF NOT EXISTS Orders (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT NOT NULL, consultant_username TEXT NOT NULL, items_summary TEXT NOT NULL, total_amount REAL NOT NULL, order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
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
            if user['role'] in ['Super Admin', 'Assistant Admin']: return redirect(url_for('index'))
            elif user['role'] == 'Consultant': return redirect(url_for('consultant_panel'))
            elif user['role'] == 'Customer': return redirect(url_for('customer_panel'))
        else: flash("Invalid credentials! Please try again.")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- UPGRADED SECURITY ROUTE ---
@app.route('/')
def index():
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Assistant Admin']: return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    # SECURITY LOCK: Force the category filter if they are an Assistant Admin
    category_filter = session.get('assigned_category') if session.get('role') == 'Assistant Admin' else request.args.get('category', '')
    
    query, params = "SELECT * FROM Products WHERE 1=1", []
    if search_query:
        query += " AND (name LIKE ? OR application LIKE ? OR finish LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    if category_filter: 
        query += " AND category = ?"
        params.append(category_filter)
        
    conn = get_db_connection()
    products = conn.execute(query, params).fetchall()
    
    users, orders, total_revenue, total_orders = [], [], 0, 0
    # SECURITY LOCK: Only fetch financial and user data if Super Admin
    if session.get('role') == 'Super Admin':
        users = conn.execute('SELECT * FROM Users').fetchall()
        orders = conn.execute('SELECT * FROM Orders ORDER BY order_date DESC').fetchall()
        total_revenue = conn.execute('SELECT SUM(total_amount) FROM Orders').fetchone()[0] or 0
        total_orders = len(orders)
        
    conn.close()
    return render_template('index.html', products=products, users=users, orders=orders, total_revenue=total_revenue, total_orders=total_orders)
# -------------------------------

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
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Assistant Admin']: return redirect(url_for('login'))
    
    # SECURITY LOCK: Override the form category with the assigned one if Assistant Admin
    category = session.get('assigned_category') if session.get('role') == 'Assistant Admin' else request.form['category']
    
    f = request.files['image']
    filename = secure_filename(f.filename) if f else ""
    if f: f.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO Products (name, category, length, height, width, thickness, price_per_sqft, application, finish, image_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
                   (request.form['name'], category, float(request.form['price']), request.form['l'], request.form['h'], request.form['w'], request.form['t'], request.form['application'], request.form['finish'], filename))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    qr_img = qrcode.make(f"ID: {product_id} | Name: {request.form['name']} | Cat: {category}").convert('RGB')
    sticker = Image.new('RGB', (qr_img.size[0], qr_img.size[1] + 50), 'white')
    sticker.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(sticker)
    draw.text((10, qr_img.size[1] + 5), f"Name: {request.form['name']}", fill="black")
    draw.text((10, qr_img.size[1] + 25), f"Lot No: {product_id}", fill="black")
    sticker.save(f"{QR_FOLDER}/product_{product_id}.png")
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_product(id):
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Assistant Admin']: return redirect(url_for('login'))
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM Products WHERE id = ?', (id,)).fetchone()
    
    if product:
        # SECURITY LOCK: Prevent Assistant Admins from deleting other categories
        if session.get('role') == 'Assistant Admin' and product['category'] != session.get('assigned_category'):
            flash("Security Alert: You do not have permission to delete products in this category.")
            conn.close()
            return redirect(url_for('index'))
            
        if product['image_path'] and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], product['image_path'])): 
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], product['image_path']))
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

# ... (Consultant, Customer, Followup, and Checkout routes remain the same, I am keeping them out for brevity, but they are fully functional in your setup!)

if __name__ == '__main__':
    app.run(debug=True)