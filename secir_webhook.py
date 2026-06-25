from flask import Flask, request, jsonify
from collections import deque
from datetime import datetime, timedelta
import hashlib
import json
import logging

app = Flask(__name__)

VALID_REGIMES = {"GREEN COMPLACENT", "YELLOW LATE CYCLE", "ORANGE FRAGILE", "RED ASYMMETRIC RISK", "BLACK CREDIT EVENT"}
RATE_LIMIT_SECONDS = 300
MAX_EVENTS = 100

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

current_state = {
    "regime": None,
    "from_regime": None,
    "secir": None,
    "secir_rank": None,
    "secir_r": None,
    "curve_intensity": None,
    "hy_oas_rank": None,
    "ig_oas_rank": None,
    "vix_rank": None,
    "valuation": None,
    "last_change_time": None,
}

events_log = deque(maxlen=MAX_EVENTS)
idempotency_cache = {}

def compute_payload_hash(ticker, from_regime, to_regime, bar_time):
    msg = f"{ticker}:{from_regime}:{to_regime}:{bar_time}"
    return hashlib.sha256(msg.encode()).hexdigest()

@app.route("/", methods=["GET"])
def dashboard():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SECIR Webhook</title>
        <meta charset="utf-8">
        <style>
            body {{ background: #000; color: #19c39a; font-family: monospace; padding: 20px; }}
            h1 {{ color: #d4a017; }}
            .regime {{ font-size: 2em; margin: 20px 0; padding: 15px; border: 2px solid #19c39a; }}
            .metrics {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
            .metric {{ background: rgba(25, 195, 154, 0.05); padding: 10px; }}
        </style>
    </head>
    <body>
        <h1>SECIR WEBHOOK COMMAND CENTER</h1>
        <div id="status">Loading...</div>
        <script>
            async function poll() {{
                const resp = await fetch('/latest');
                const data = await resp.json();
                document.getElementById('status').innerHTML = `
                    <div class="regime">${{data.regime || 'AWAITING SIGNAL'}}</div>
                    <div class="metrics">
                        <div class="metric"><strong>SECIR</strong><br/>${{(data.secir || 0).toFixed(3)}}</div>
                        <div class="metric"><strong>Rank</strong><br/>${{(data.secir_rank || 0).toFixed(0)}}%</div>
                        <div class="metric"><strong>SECIR-R</strong><br/>${{(data.secir_r || 0).toFixed(2)}}</div>
                        <div class="metric"><strong>Curve</strong><br/>${{(data.curve_intensity || 0).toFixed(2)}}</div>
                    </div>
                `;
            }}
            poll();
            setInterval(poll, 5000);
        </script>
    </body>
    </html>
    """
    return html, 200, {"Content-Type": "text/html"}

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "regime": current_state["regime"]}), 200

@app.route("/seasonaledge", methods=["POST"])
def webhook_intake():
    try:
        data = request.get_json() or {}
        
        ticker = data.get("ticker", "SPX").upper()
        to_regime = data.get("to_regime", "").upper()
        from_regime = data.get("from_regime", "").upper() or "INIT"
        bar_time_str = data.get("bar_time", "")
        
        if to_regime not in VALID_REGIMES:
            return jsonify({"status": "rejected", "reason": f"Invalid regime: {to_regime}"}), 400
        
        idem_hash = compute_payload_hash(ticker, from_regime, to_regime, bar_time_str)
        if idem_hash in idempotency_cache:
            return jsonify({"status": "duplicate", "reason": "Already seen this alert"}), 409
        
        if current_state["last_change_time"]:
            elapsed = (datetime.utcnow() - current_state["last_change_time"]).total_seconds()
            if elapsed < RATE_LIMIT_SECONDS:
                return jsonify({"status": "rate_limited", "reason": f"Wait {RATE_LIMIT_SECONDS - elapsed:.0f}s"}), 429
        
        idempotency_cache[idem_hash] = datetime.utcnow()
        
        current_state.update({
            "regime": to_regime,
            "from_regime": from_regime,
            "secir": float(data.get("secir", 0)),
            "secir_rank": float(data.get("secir_rank", 0)),
            "secir_r": float(data.get("secir_r", 0)),
            "curve_intensity": float(data.get("curve_intensity", 0)),
            "hy_oas_rank": float(data.get("hy_oas_rank", 0)),
            "ig_oas_rank": float(data.get("ig_oas_rank", 0)),
            "vix_rank": float(data.get("vix_rank", 0)),
            "valuation": data.get("valuation", "N/A"),
            "last_change_time": datetime.utcnow(),
        })
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "from_regime": from_regime,
            "to_regime": to_regime,
            "secir": data.get("secir"),
            "secir_rank": data.get("secir_rank"),
        }
        events_log.append(event)
        
        logger.info(f"✓ REGIME CHANGE: {from_regime} → {to_regime}")
        
        return jsonify({"status": "accepted", "regime": to_regime}), 200
    
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return jsonify({"status": "error", "reason": str(e)}), 500

@app.route("/latest", methods=["GET"])
def get_latest():
    return jsonify(current_state), 200

@app.route("/events", methods=["GET"])
def get_events():
    return jsonify({"events": list(events_log)}), 200

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
