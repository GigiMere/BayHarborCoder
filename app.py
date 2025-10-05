import os, datetime, json, random, urllib.request
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, text
from flask_socketio import SocketIO, emit

# -------------------- App / Config --------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-please-change")

db_url = os.environ.get("DATABASE_URL", "sqlite:///local.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
engine = create_engine(db_url, future=True)

socketio = SocketIO(app, cors_allowed_origins="*")

# -------------------- DB helpers ----------------------
def ensure_tables():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL
        );"""))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS coins(
            name TEXT PRIMARY KEY,
            coins INTEGER NOT NULL DEFAULT 0
        );"""))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS events(
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            lat DOUBLE PRECISION NOT NULL,
            lon DOUBLE PRECISION NOT NULL,
            date DATE NOT NULL,
            temp_c DOUBLE PRECISION,
            precip_mm DOUBLE PRECISION,
            risk TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );"""))

ensure_tables()

@app.before_request
def load_user():
    g.user = None
    uid = session.get("user_id")
    if not uid: return
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id,name,email FROM users WHERE id=:i"), {"i":uid}).mappings().first()
        if row:
            g.user = type("User", (), dict(id=row["id"], name=row["name"], email=row["email"]))

# -------------------- Weather helpers --------------------
def _fetch_power(lat, lon, start_yyyymmdd, end_yyyymmdd):
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        "?parameters=T2M,PRECTOTCORR"
        "&community=AG"
        f"&longitude={lon}&latitude={lat}"
        f"&start={start_yyyymmdd}&end={end_yyyymmdd}&format=JSON"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

def _fetch_openmeteo(lat, lon, start_iso, end_iso):
    # Open-Meteo daily forecast (no API key)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=temperature_2m_max,precipitation_sum"
        "&timezone=UTC"
        f"&start_date={start_iso}&end_date={end_iso}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

def _classify(temp_c, precip_mm):
    p = precip_mm or 0.0
    if p > 10: return "rainy"
    if 1 < p <= 10: return "light_rain"
    if temp_c is not None and temp_c >= 23: return "sunny"
    return "cloudy"

def _day_list(end_iso):
    end = datetime.date.fromisoformat(end_iso)
    return [(end - datetime.timedelta(days=i)).isoformat() for i in range(6,-1,-1)]

def get_week(lat, lon, end_iso):
    """Returns last 7 days ending at end_iso using NASA POWER when available,
       otherwise falls back to Open-Meteo (works for future too)."""
    days = _day_list(end_iso)
    data = []

    # Try NASA daily (historical/near-real-time)
    j = _fetch_power(lat, lon, days[0].replace("-",""), days[-1].replace("-",""))
    if j and "properties" in j:
        T = j["properties"]["parameter"].get("T2M", {})
        P = j["properties"]["parameter"].get("PRECTOTCORR", {})
        # POWER sometimes returns -999 for missing; normalize to None
        for d in days:
            k = d.replace("-","")
            t = T.get(k); p = P.get(k)
            t = None if (t is None or float(t) <= -900) else float(t)
            p = None if (p is None or float(p) <= -900) else float(p)
            cond = _classify(t, p)
            risk = "High" if (p or 0) > 10 else ("Med" if (p or 0) > 1 else "Low")
            data.append({"date":d,"temp_c":t,"precip_mm":p,"risk":risk,"condition":cond})
        # If the last day is still None (or user chose a future date), try to fill from Open-Meteo
        need_fill = any(x["temp_c"] is None for x in data)
        if not need_fill:
            return {"data": data}

    # Open-Meteo fallback (also supports future)
    j2 = _fetch_openmeteo(lat, lon, days[0], days[-1])
    if j2 and j2.get("daily"):
        dd = j2["daily"]
        dates = dd.get("time", [])
        temps = dd.get("temperature_2m_max", [])
        precs = dd.get("precipitation_sum", [])
        m = { dates[i]: (temps[i], precs[i]) for i in range(len(dates)) }
        data = []
        for d in days:
            t, p = m.get(d, (None, None))
            t = None if t is None else float(t)
            p = None if p is None else float(p)
            cond = _classify(t, p)
            risk = "High" if (p or 0) > 10 else ("Med" if (p or 0) > 1 else "Low")
            data.append({"date":d,"temp_c":t,"precip_mm":p,"risk":risk,"condition":cond})
        return {"data": data}

    # Last resort: fake but reasonable data
    for d in days:
        t = round(random.uniform(12,30),1)
        p = random.choice([0,0.2,2.0,12.0])
        cond = _classify(t,p)
        risk = "High" if p>10 else ("Med" if p>1 else "Low")
        data.append({"date":d,"temp_c":t,"precip_mm":p,"risk":risk,"condition":cond})
    return {"data": data, "note":"fallback"}

def get_day(lat, lon, iso_date):
    w = get_week(lat, lon, iso_date).get("data",[])
    for d in w:
        if d["date"] == iso_date: return d
    return None

# -------------------- Pages --------------------
@app.route("/")
def page_weather():
    return render_template("index.html", page="weather", title="WEATHER GUESSR")

@app.route("/events")
def page_events():
    return render_template("events.html", page="events", title="Events")

@app.route("/game")
def page_game():
    return render_template("game.html", page="game", title="Game")

@app.route("/leaderboard")
def page_leader():
    return render_template("leaderboard.html", page="leaderboard", title="Coin-Top")

# Login / Register (unchanged)
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=(request.form.get("email") or "").lower().strip()
        pw=request.form.get("password") or ""
        with engine.begin() as conn:
            row=conn.execute(text("SELECT * FROM users WHERE email=:e"),{"e":email}).mappings().first()
        if row and check_password_hash(row["password_hash"], pw):
            session["user_id"]=row["id"]; flash("Welcome back!","success")
            return redirect(url_for("page_weather"))
        flash("Invalid credentials","danger")
    return render_template("login.html", page="login", title="Login")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=(request.form.get("name") or "").strip()
        email=(request.form.get("email") or "").lower().strip()
        pw=request.form.get("password") or ""
        if not name or not email or len(pw)<6:
            flash("Please fill all fields (password ≥ 6).","warning")
            return redirect(url_for("register"))
        with engine.begin() as conn:
            try:
                conn.execute(text(
                    "INSERT INTO users(name,email,password_hash) VALUES(:n,:e,:p)"
                ), {"n":name,"e":email,"p":generate_password_hash(pw)})
                row=conn.execute(text("SELECT id FROM users WHERE email=:e"),{"e":email}).mappings().first()
                session["user_id"]=row["id"]; flash("Account created!","success")
                return redirect(url_for("page_weather"))
            except:
                flash("Email already registered.","danger")
    return render_template("register.html", page="register", title="Register")

@app.route("/logout")
def logout():
    session.clear(); flash("Logged out.","info")
    return redirect(url_for("page_weather"))

# -------------------- APIs --------------------
@app.route("/api/weather/week")
def api_weather_week():
    lat=float(request.args.get("lat", 40.7128))
    lon=float(request.args.get("lon", -74.0060))
    end = request.args.get("date") or datetime.date.today().isoformat()
    return jsonify(get_week(lat,lon,end))

@app.route("/api/weather/day")
def api_weather_day():
    lat=float(request.args.get("lat", 40.7128))
    lon=float(request.args.get("lon", -74.0060))
    date = request.args.get("date") or datetime.date.today().isoformat()
    d = get_day(lat, lon, date)
    return jsonify(d or {"error":"no data"})

@app.route("/api/today")
def api_today():
    lat=float(request.args.get("lat", 40.7128))
    lon=float(request.args.get("lon", -74.0060))
    d = get_day(lat, lon, datetime.date.today().isoformat())
    return jsonify(d or {"error":"no data"})

# ---- Cities for Game: 4 local PNGs ----
CITIES = [
    {"name":"New York, NY","lat":40.7128,"lon":-74.0060,"img":"/static/img/cities_us/new_york.png"},
    {"name":"Los Angeles, CA","lat":34.0522,"lon":-118.2437,"img":"/static/img/cities_us/los_angeles.png"},
    {"name":"Chicago, IL","lat":41.8781,"lon":-87.6298,"img":"/static/img/cities_us/chicago.png"},
    {"name":"Miami, FL","lat":25.7617,"lon":-80.1918,"img":"/static/img/cities_us/miami.png"},
]
@app.route("/api/cities")
def api_cities():
    return jsonify({"data": CITIES})

# ---- Coins / Leaderboard (unchanged)
@app.route("/api/coins/get")
def api_coins_get():
    name=(request.args.get("name") or "Player").strip()[:30]
    with engine.begin() as conn:
        row=conn.execute(text("SELECT coins FROM coins WHERE name=:n"),{"n":name}).mappings().first()
    return jsonify({"name":name,"coins": (row["coins"] if row else 0)})

@app.route("/api/coins/add", methods=["POST"])
def api_coins_add():
    d=(request.get_json(silent=True) or {})
    name=(d.get("name") or "Player").strip()[:30]
    delta=int(d.get("delta") or 0)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO coins(name,coins) VALUES(:n,:c)
            ON CONFLICT(name) DO UPDATE SET coins = coins + excluded.coins
        """), {"n":name, "c": max(delta,0)})
        row=conn.execute(text("SELECT coins FROM coins WHERE name=:n"),{"n":name}).mappings().first()
    return jsonify({"name":name,"coins":row["coins"]})

@app.route("/api/coins/top")
def api_coins_top():
    with engine.begin() as conn:
        rows=conn.execute(text("SELECT name,coins FROM coins ORDER BY coins DESC, name ASC LIMIT 100")).mappings().all()
    return jsonify({"data":[dict(r) for r in rows]})

# ---- Events (OPEN)
def now_utc(): return datetime.datetime.utcnow()

@app.route("/api/events/list")
def api_events_list():
    with engine.begin() as conn:
        rows=conn.execute(text("""
            SELECT id,title,lat,lon,date::text AS date,temp_c,precip_mm,risk,created_at,updated_at
            FROM events ORDER BY date ASC, id DESC
        """)).mappings().all()
    return jsonify({"data":[dict(r) for r in rows]})

@app.route("/api/events/create", methods=["POST"])
def api_events_create():
    data=request.get_json(silent=True) or {}
    title=(data.get("title") or "Untitled").strip()
    try:
        lat=float(data.get("lat")); lon=float(data.get("lon"))
        date=data.get("date") or datetime.date.today().isoformat()
        datetime.date.fromisoformat(date)
    except Exception:
        return jsonify({"error":"Invalid input (title, lat, lon, date)"}), 400
    day = get_day(lat,lon,date) or {}
    now = now_utc()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO events(title,lat,lon,date,temp_c,precip_mm,risk,created_at,updated_at)
            VALUES(:t,:lat,:lon,:d,:tc,:pp,:r,:c,:u)
        """), {"t":title,"lat":lat,"lon":lon,"d":date,
               "tc":day.get("temp_c"),"pp":day.get("precip_mm"),"r":day.get("risk","Unknown"),
               "c":now,"u":now})
    return jsonify({"ok":True})

@app.route("/api/events/delete/<int:eid>", methods=["DELETE"])
def api_events_delete(eid):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM events WHERE id=:i"), {"i":eid})
    return jsonify({"ok":True})

@app.route("/api/events/recheck/<int:eid>", methods=["POST"])
def api_events_recheck(eid):
    with engine.begin() as conn:
        row=conn.execute(text("SELECT id,lat,lon,date::text AS date FROM events WHERE id=:i"),{"i":eid}).mappings().first()
        if not row: return jsonify({"error":"Not found"}), 404
        d = get_day(row["lat"], row["lon"], row["date"]) or {}
        conn.execute(text("""
            UPDATE events SET temp_c=:t, precip_mm=:p, risk=:r, updated_at=:u WHERE id=:i
        """), {"t":d.get("temp_c"),"p":d.get("precip_mm"),"r":d.get("risk","Unknown"),"u":now_utc(),"i":eid})
    return jsonify({"ok":True})

# -------------------- Socket.IO (placeholder) --------------------
@socketio.on("connect")
def sio_connect():
    emit("hello", {"msg": "connected"})

# -------------------- Run --------------------
if __name__ == "__main__":
    ensure_tables()
    socketio.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", 5050)), debug=True, use_reloader=False)
