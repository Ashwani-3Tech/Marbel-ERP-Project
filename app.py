from flask import Flask, render_template, request, redirect, url_for
import sqlite3
import qrcode
import os

app = Flask(__name__)

# Ensure QR code directory exists
os.makedirs('qr_codes', exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect('marble_inventory.db')
    conn.row_factory = sqlite3.Row
    return conn

# Create the database table
def setup_database():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS Products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            size TEXT,
            price_per_sqft REAL,
            application TEXT,
            finish TEXT
        )
    ''')
    conn.commit()
    conn.close()

setup_database()

# Home Route: Show the Inventory List
@app.route('/')
def inventory():
    conn = get_db_connection()
    products = conn.execute('SELECT * FROM Products').fetchall()
    conn.close()
    return render_template('index.html', products=products)

# Add Product Route: Save data and generate QR
@app.route('/add', methods=('GET', 'POST'))
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        size = request.form['size']
        price = request.form['price']
        application = request.form['application']
        finish = request.form['finish']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO Products (name, category, size, price_per_sqft, application, finish)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, category, size, price, application, finish))
        
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Generate the QR Code image
        qr_data = f"ID: {product_id} | Name: {name} | Category: {category}"
        img = qrcode.make(qr_data)
        img.save(f"qr_codes/product_{product_id}.png")

        return redirect(url_for('inventory'))
    
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)