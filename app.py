import os
import json
import datetime
import pytz
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling

# ---------- APP INITIALISIEREN ----------
app = Flask(__name__, static_url_path="/")

# 1) Secret-Keys laden **nach** App-Instanziierung
with open('/etc/secrets/hwm-session-secret', encoding='utf-8') as f:
    app.secret_key = f.read().strip()

with open('/etc/secrets/hwm-pw', encoding='utf-8') as f:
    ADMIN_PASSWORD = f.read().strip()

# 2) CORS so konfigurieren, dass Cookies mitgesendet werden
CORS(app, supports_credentials=True)

# ---------- DATENBANK-KONFIG ----------
DB_CONFIG = {
    "host":     "mc-mysql01.mc-host24.de",
    "user":     "u4203_Mtc42FNhxN",
    "password": "nA6U=8ecQBe@vli@SKXN9rK9",
    "database": "s4203_reports",
    "port":     3306
}

# ---------- CONNECTION POOL ----------
pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=5,
    pool_reset_session=True,
    **DB_CONFIG
)

def get_connection():
    return pool.get_connection()

# ---------- ROUTEN ----------

@app.route("/")
def root():
    return send_from_directory(app.static_folder, "login.html")

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    pw = data.get('password', '')
    if pw == ADMIN_PASSWORD:
        session['role'] = 'admin'
        return jsonify(status='ok')
    return jsonify(status='error', message='Ungültiges Passwort'), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify(status='ok')

@app.route('/api/secure-data')
def secure_data():
    if session.get('role') != 'admin':
        return jsonify(status='error', message='Unauthorized'), 403
    return jsonify(status='ok', data='Hier sind geheime Daten!')

@app.route('/stundenplan')
def stundenplan():
    pfad = os.path.join(os.path.dirname(__file__), "stundenplan.json")
    with open(pfad, encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route('/aktuelles_fach')
def aktuelles_fach():
    tz = pytz.timezone('Europe/Berlin')
    now = datetime.datetime.now(tz)
    tag = now.strftime('%A')
    pfad = os.path.join(os.path.dirname(__file__), "stundenplan.json")
    with open(pfad, encoding='utf-8') as f:
        plan = json.load(f).get(tag, [])

    current  = {"fach": "Frei", "verbleibend": "-", "raum": "-"}
    next_cls = {"start": None, "fach": "-", "raum": "-"}

    def parse_time(t):
        h, m = map(int, t.split(':'))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    for slot in plan:
        start = parse_time(slot["start"])
        ende  = parse_time(slot["end"])
        if start <= now <= ende:
            delta_s = int((ende - now).total_seconds())
            minutes, seconds = divmod(delta_s, 60)
            verbleibend = f"{minutes:02d}:{seconds:02d}"
            current = {
                "fach":        slot["fach"],
                "verbleibend": verbleibend,
                "raum":        slot.get("raum", "-")
            }
        elif start > now and slot.get("raum", "-") != "-":
            if next_cls["start"] is None or start < next_cls["start"]:
                next_cls = {"start": start, "fach": slot["fach"], "raum": slot["raum"]}

    next_start = (
        f"{next_cls['start'].hour:02d}:{next_cls['start'].minute:02d}"
        if next_cls["start"] else "-"
    )

    return jsonify({
        **current,
        "naechste_start": next_start,
        "naechster_raum": next_cls["raum"],
        "naechstes_fach": next_cls["fach"]
    })

@app.route('/hausaufgaben')
def hausaufgaben():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT fachkuerzel AS fach, beschreibung, DATE(faellig_am) AS faellig_am "
            "FROM hausaufgaben"
        )
        result = cursor.fetchall()
        for item in result:
            item['faellig_am'] = item['faellig_am'].strftime('%Y-%m-%d')
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Fehler /hausaufgaben: {e}")
        return jsonify([]), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/pruefungen')
def pruefungen():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT fachkuerzel AS fach, beschreibung, DATE(pruefungsdatum) AS pruefungsdatum "
            "FROM pruefungen"
        )
        result = cursor.fetchall()
        for item in result:
            item['pruefungsdatum'] = item['pruefungsdatum'].strftime('%Y-%m-%d')
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Fehler /pruefungen: {e}")
        return jsonify([]), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/add_entry', methods=['POST'])
def add_entry():
    data = request.json or {}
    typ = data.get("typ")
    fach = data.get("fach")
    beschreibung = data.get("beschreibung")
    datum = data.get("datum")

    try:
        conn = get_connection()
        cursor = conn.cursor()
        if typ == "hausaufgabe":
            cursor.execute(
                "INSERT INTO hausaufgaben (fachkuerzel, beschreibung, faellig_am) VALUES (%s,%s,%s)",
                (fach, beschreibung, datum)
            )
        elif typ == "pruefung":
            cursor.execute(
                "INSERT INTO pruefungen (fachkuerzel, beschreibung, pruefungsdatum) VALUES (%s,%s,%s)",
                (fach, beschreibung, datum)
            )
        else:
            return jsonify(status="error", message="Ungültiger Typ"), 400

        conn.commit()
        return jsonify(status="ok")
    except Exception as e:
        app.logger.error(f"Fehler /add_entry: {e}")
        return jsonify(status="error", message=str(e)), 500
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
