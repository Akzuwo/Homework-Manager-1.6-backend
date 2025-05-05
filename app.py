from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import datetime
import json
import os
import pytz
import mysql.connector
from mysql.connector import pooling


app = Flask(__name__, static_url_path="/")
CORS(app)

# ---------- KONFIGURATION ----------
DB_CONFIG = {
    "host": "mc-mysql01.mc-host24.de",
    "user": "u4203_Mtc42FNhxN",             # ← hier anpassen
    "password": "nA6U=8ecQBe@vli@SKXN9rK9",     # ← hier anpassen
    "database": "s4203_reports",   # ← hier anpassen
    "port": 3306
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

#------------APP START ----------

@app.route("/")
def root():
    return send_from_directory(app.static_folder, "login.html")
# ---------- STUNDENPLAN ----------
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
    uhrzeit = now.time()

    pfad = os.path.join(os.path.dirname(__file__), "stundenplan.json")
    with open(pfad, encoding='utf-8') as f:
        plan = json.load(f).get(tag, [])

    current = {"fach": "Frei", "verbleibend": "-", "raum": "-"}
    next_cls = {"start": None, "fach": "-", "raum": "-"}

    def parse_time(t):
        h, m = map(int, t.split(':'))
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    for slot in plan:
        start = parse_time(slot["start"])
        ende  = parse_time(slot["end"])
        # laufende Stunde?
        if start <= now <= ende:
            remain = ende - now
            h, m = divmod(int(remain.total_seconds()//60), 60)
            current = {
                "fach":        slot["fach"],
                "verbleibend": f"{h:02d}:{m:02d}",
                "raum":        slot.get("raum", "-")
            }
        # nächste Stunde (Raum ≠ "-")
        elif start > now and slot.get("raum", "-") != "-":
            if next_cls["start"] is None or start < next_cls["start"]:
                next_cls = {
                    "start": start,
                    "fach":  slot["fach"],
                    "raum":  slot["raum"]
                }

    # Formatierung
    if next_cls["start"]:
        ns = next_cls["start"]
        next_start = f"{ns.hour:02d}:{ns.minute:02d}"
    else:
        next_start = "-"

    return jsonify({
        **current,
        "naechste_start":  next_start,
        "naechster_raum":  next_cls["raum"],
        "naechstes_fach":  next_cls["fach"]
    })



# ---------- HAUSAUFGABEN ----------
@app.route('/hausaufgaben')
def hausaufgaben():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT fachkuerzel AS fach, beschreibung, DATE(faellig_am) AS faellig_am FROM hausaufgaben")
        result = cursor.fetchall()
        for item in result:
            item['faellig_am'] = item['faellig_am'].strftime('%Y-%m-%d')
        return jsonify(result)
    except Exception as e:
        print(f"Fehler /hausaufgaben: {e}")
        return jsonify([]), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# ---------- PRÜFUNGEN ----------
@app.route('/pruefungen')
def pruefungen():
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT fachkuerzel AS fach, beschreibung, DATE(pruefungsdatum) AS pruefungsdatum FROM pruefungen")
        result = cursor.fetchall()
        for item in result:
            item['pruefungsdatum'] = item['pruefungsdatum'].strftime('%Y-%m-%d')
        return jsonify(result)
    except Exception as e:
        print(f"Fehler /pruefungen: {e}")
        return jsonify([]), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# ---------- EINTRAG HINZUFÜGEN ----------
@app.route('/add_entry', methods=['POST'])
def add_entry():
    data = request.json
    typ = data.get("typ")
    fach = data.get("fach")
    beschreibung = data.get("beschreibung")
    datum = data.get("datum")

    try:
        conn = get_connection()
        cursor = conn.cursor()

        if typ == "hausaufgabe":
            cursor.execute(
                "INSERT INTO hausaufgaben (fachkuerzel, beschreibung, faellig_am) VALUES (%s, %s, %s)",
                (fach, beschreibung, datum)
            )
        elif typ == "pruefung":
            cursor.execute(
                "INSERT INTO pruefungen (fachkuerzel, beschreibung, pruefungsdatum) VALUES (%s, %s, %s)",
                (fach, beschreibung, datum)
            )
        else:
            return jsonify({"status": "error", "message": "Ungültiger Typ"}), 400

        conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Fehler /add_entry: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass


# ---------- SERVER START ----------
if __name__ == "__main__":
    app.run(debug=False, port=5000)
