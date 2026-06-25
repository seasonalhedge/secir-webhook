from flask import Flask, request, jsonify
from collections import deque
from datetime import datetime
import hashlib, logging

app = Flask(__name__)

VALID_REGIMES = {"GREEN COMPLACENT","YELLOW LATE CYCLE","ORANGE FRAGILE","RED ASYMMETRIC RISK","BLACK CREDIT EVENT"}
RATE_LIMIT_SECONDS = 300
MAX_EVENTS = 100

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

current_state = {"regime":None,"from_regime":None,"secir":None,"secir_rank":None,"secir_r":None,
    "curve_intensity":None,"hy_oas_rank":None,"ig_oas_rank":None,"vix_rank":None,"valuation":None,"last_change_time":None}
events_log = deque(maxlen=MAX_EVENTS)
idempotency_cache = {}

def phash(t,f,to,bt): return hashlib.sha256(f"{t}:{f}:{to}:{bt}".encode()).hexdigest()

@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/health")
def health():
    return jsonify({"status":"healthy","timestamp":datetime.utcnow().isoformat(),"regime":current_state["regime"]}),200

@app.route("/seasonaledge", methods=["POST","OPTIONS"])
def intake():
    if request.method == "OPTIONS": return ("",204)
    try:
        data = request.get_json(force=True, silent=True) or {}
        ticker = str(data.get("ticker","SPX")).upper()
        to_regime = str(data.get("to_regime","")).upper()
        from_regime = str(data.get("from_regime","")).upper() or "INIT"
        bar_time = str(data.get("bar_time",""))
        if to_regime not in VALID_REGIMES:
            return jsonify({"status":"rejected","reason":f"Invalid regime: {to_regime}"}),400
        h = phash(ticker,from_regime,to_regime,bar_time)
        if h in idempotency_cache:
            return jsonify({"status":"duplicate"}),409
        if current_state["last_change_time"]:
            el = (datetime.utcnow()-current_state["last_change_time"]).total_seconds()
            if el < RATE_LIMIT_SECONDS:
                return jsonify({"status":"rate_limited","reason":f"wait {RATE_LIMIT_SECONDS-el:.0f}s"}),429
        idempotency_cache[h] = datetime.utcnow()
        def f(k):
            try: return float(data.get(k,0))
            except: return 0.0
        current_state.update({"regime":to_regime,"from_regime":from_regime,"secir":f("secir"),
            "secir_rank":f("secir_rank"),"secir_r":f("secir_r"),"curve_intensity":f("curve_intensity"),
            "hy_oas_rank":f("hy_oas_rank"),"ig_oas_rank":f("ig_oas_rank"),"vix_rank":f("vix_rank"),
            "valuation":data.get("valuation","N/A"),"last_change_time":datetime.utcnow()})
        events_log.append({"timestamp":datetime.utcnow().isoformat(),"from_regime":from_regime,
            "to_regime":to_regime,"secir":data.get("secir"),"secir_rank":data.get("secir_rank")})
        logger.info(f"REGIME CHANGE: {from_regime} -> {to_regime}")
        return jsonify({"status":"accepted","regime":to_regime}),200
    except Exception as e:
        logger.error(str(e))
        return jsonify({"status":"error","reason":str(e)}),500

@app.route("/latest")
def latest():
    s = dict(current_state)
    if s["last_change_time"]: s["last_change_time"] = s["last_change_time"].isoformat()
    return jsonify(s),200

@app.route("/events")
def events():
    return jsonify({"events":list(events_log)}),200

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
