from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import qrcode
import os
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='static')
app.secret_key = "ashu_secret_key" # Needed for feedback messages

# Configuration
UPLOAD_FOLDER = 'static/uploads'
QR_FOLDER = 'qr_codes'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('marble_inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

# UPDATED DATABASE SCHEMA (Matching Section 7)
def setup_database():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            length REAL, height REAL, width REAL, thickness REAL,
            price_per_sqft REAL,
            application TEXT,
            finish TEXT,
            description TEXT,
            image_path TEXT
        )
    ''')
    conn.commit()
    conn.close()

setup_database()

@app.route('/')
def index():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM Products').fetchall()
    conn.close()
    return render_template('index.html', products=products)

@app.route('/add', methods=['POST'])
def add_product():
    # Get text data
    name = request.form['name']
    category = request.form['category']
    price = float(request.form['price'])
    # Get measurements (Section 7)
    l, h, w, t = request.form['l'], request.form['h'], request.form['w'], request.form['t']
    app_use = request.form['application']
    finish = request.form['finish']

    # Handle Image Upload (Section 1)
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

    # Generate Advanced QR (Section 6: Name and ID on QR)
    qr_data = f"ID: {product_id} | Name: {name} | Cat: {category}"
    img = qrcode.make(qr_data)
    img.save(f"{QR_FOLDER}/product_{product_id}.png")

    return redirect(url_for('index'))

# BULK PRICE UPDATE (Section 2)
@app.route('/bulk_update', methods=['POST'])
def bulk_update():
    percent = float(request.form['percent']) / 100
    conn = get_db_connection()
    # Increases or decreases ALL prices by the given percentage
    conn.execute('UPDATE Products SET price_per_sqft = price_per_sqft * (1 + ?)', (percent,))
    conn.commit()
    conn.close()
    flash(f"Prices updated by {int(percent*100)}%")
    return redirect(url_for('index'))
@app.route('/delete/<int:id>')
def delete_product(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM Products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))
if __name__ == '__main__':
    app.run(debug=True)