from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import qrcode
import os
from werkzeug.utils import secure_filename
from PIL import Image, ImageDraw  # We added these tools to draw the text!

app = Flask(__name__, static_folder='static')
app.secret_key = "ashu_secret_key"

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
    conn.close()
    
    return render_template('index.html', products=products)

@app.route('/add', methods=['POST'])
def add_product():
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

    # SECTION 6: ADVANCED PHYSICAL STICKER QR GENERATION
    qr_data = f"ID: {product_id} | Name: {name} | Cat: {category}"
    qr_img = qrcode.make(qr_data).convert('RGB')
    
    # Create a white canvas that is taller than the QR code
    qr_w, qr_h = qr_img.size
    sticker = Image.new('RGB', (qr_w, qr_h + 50), 'white')
    
    # Paste the QR code onto the top of the canvas
    sticker.paste(qr_img, (0, 0))
    
    # Use the digital pen to write the text at the bottom
    draw = ImageDraw.Draw(sticker)
    draw.text((10, qr_h + 5), f"Name: {name}", fill="black")
    draw.text((10, qr_h + 25), f"Lot No: {product_id}  |  {category}", fill="black")
    
    # Save the final sticker
    sticker.save(f"{QR_FOLDER}/product_{product_id}.png")

    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
def delete_product(id):
    conn = get_db_connection()
    product = conn.execute('SELECT image_path FROM Products WHERE id = ?', (id,)).fetchone()
    if product and product['image_path']:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], product['image_path'])
        if os.path.exists(image_path):
            os.remove(image_path)
            
    conn.execute('DELETE FROM Products WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/bulk_update', methods=['POST'])
def bulk_update():
    percent = float(request.form['percent']) / 100
    conn = get_db_connection()
    conn.execute('UPDATE Products SET price_per_sqft = price_per_sqft * (1 + ?)', (percent,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)