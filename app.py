from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'kintai.db')

# Ensure DB exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    type TEXT CHECK(type IN ('in','out')) NOT NULL,
    description TEXT
)''')
conn.commit()
conn.close()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/punch', methods=['POST'])
def punch():
    name = request.form['name']  # Placeholder until auth is implemented
    punch_type = request.form['type']  # 'in' or 'out'
    timestamp = request.form['timestamp']  # Manual input of timestamp
    description = request.form.get('description', '')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO attendance (name, timestamp, type, description) VALUES (?, ?, ?, ?)", (name, timestamp, punch_type, description))
    conn.commit()
    conn.close()

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
