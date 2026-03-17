from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import qrcode
import os
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
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, category TEXT,
            length REAL, height REAL, width REAL, thickness REAL,
            price_per_sqft REAL, application TEXT, finish TEXT,
            description TEXT, image_path TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
            role TEXT NOT NULL, assigned_category TEXT
        )
    ''')
    admin = conn.execute('SELECT * FROM Users WHERE username = "admin"').fetchone()
    if not admin:
        conn.execute('INSERT INTO Users (username, password, role) VALUES (?, ?, ?)', 
                     ('admin', 'admin123', 'Super Admin'))
    conn.commit()
    conn.close()

setup_database()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM Users WHERE username = ? AND password = ?', (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['username'] = user['username']
            session['assigned_category'] = user['assigned_category']
            
            # --- THE NEW TRAFFIC CONTROLLER ---
            if user['role'] == 'Super Admin':
                return redirect(url_for('index'))
            elif user['role'] == 'Consultant':
                return redirect(url_for('consultant_panel'))
            elif user['role'] == 'Customer':
                return redirect(url_for('customer_panel'))
            elif user['role'] == 'Assistant Admin':
                return redirect(url_for('index')) # We will restrict their view later!
            # ----------------------------------
            
        else:
            flash("Invalid credentials! Please try again.")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user_id' not in session or session.get('role') != 'Super Admin':
        return redirect(url_for('login'))

    search_query = request.args.get('search', '')
    category_filter = request.args.get('category', '')
    query = "SELECT * FROM Products WHERE 1=1"
    params = []
    
    if search_query:
        query += " AND (name LIKE ? OR application LIKE ? OR finish LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
    if category_filter:
        query += " AND category = ?"
        params.append(category_filter)
        
    conn = get_db_connection()
    products = conn.execute(query, params).fetchall()
    users = conn.execute('SELECT * FROM Users').fetchall() # <-- FETCHES USERS FOR ADMIN!
    conn.close()
    
    return render_template('index.html', products=products, users=users)

# --- USER MANAGEMENT ROUTES ---
@app.route('/add_user', methods=['POST'])
def add_user():
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    category = request.form.get('assigned_category', '')

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO Users (username, password, role, assigned_category) VALUES (?, ?, ?, ?)',
                     (username, password, role, category))
        conn.commit()
    except sqlite3.IntegrityError:
        flash("That Username already exists!")
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_user/<int:id>')
def delete_user(id):
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM Users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))
# ------------------------------

@app.route('/add', methods=['POST'])
def add_product():
    if 'user_id' not in session: return redirect(url_for('login'))
    name = request.form['name']
    category = request.form['category']
    price = float(request.form['price'])
    l, h, w, t = request.form['l'], request.form['h'], request.form['w'], request.form['t']
    app_use = request.form['application']
    finish = request.form['finish']

    file = request.files['image']
    filename = ""
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO Products (name, category, length, height, width, thickness, price_per_sqft, application, finish, image_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, category, l, h, w, t, price, app_use, finish, filename))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()

    qr_data = f"ID: {product_id} | Name: {name} | Cat: {category}"
    qr_img = qrcode.make(qr_data).convert('RGB')
    qr_w, qr_h = qr_img.size
    sticker = Image.new('RGB', (qr_w, qr_h + 50), 'white')
    sticker.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(sticker)
    draw.text((10, qr_h + 5), f"Name: {name}", fill="black")
    draw.text((10, qr_h + 25), f"Lot No: {product_id}  |  {category}", fill="black")
    sticker.save(f"{QR_FOLDER}/product_{product_id}.png")

    return redirect(url_for('index'))

@app.route('/consultant')
def consultant_panel():
    # SECURITY LOCK: Only Consultants and Super Admins can enter!
    if 'user_id' not in session or session.get('role') not in ['Super Admin', 'Consultant']:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM Products').fetchall()
    conn.close()
    return render_template('consultant.html', products=products)

@app.route('/customer')
def customer_panel():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM Products').fetchall()
    conn.close()
    return render_template('customer.html', products=products)

@app.route('/delete/<int:id>')
def delete_product(id):
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    conn = get_db_connection()
    product = conn.execute('SELECT image_path FROM Products WHERE id = ?', (id,)).fetchone()
    if product and product['image_path']:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image_path'])
        if os.path.exists(image_path): os.remove(image_path)
    conn.execute('DELETE FROM Products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/bulk_update', methods=['POST'])
def bulk_update():
    if 'user_id' not in session or session.get('role') != 'Super Admin': return redirect(url_for('login'))
    percent = float(request.form['percent']) / 100
    conn = get_db_connection()
    conn.execute('UPDATE Products SET price_per_sqft = price_per_sqft * (1 + ?)', (percent,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)