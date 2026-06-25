from flask import Flask, jsonify, render_template_string, request
from datetime import datetime
from collections import deque

app = Flask(__name__)
events = deque(maxlen=100)
current_state = {
    "regime": "RED",
    "secir": 0.0,
    "secir_rank": 0,
    "secir_r": 0.0,
    "real_yield": 0.0,
    "real_yield_confirms": False,
    "valuation": "RED",
    "timestamp": None,
    "direction": "flat"
}

VALID_REGIMES = ["GREEN", "YELLOW", "ORANGE", "RED", "BLACK"]

@app.route('/', methods=['GET'])
def dashboard():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SECIR Command OS</title>
        <style>
            body {{ background: #000; color: #19c39a; font-family: 'Courier New'; padding: 20px; }}
            .regime {{ font-size: 32px; margin: 20px 0; font-weight: bold; }}
            .metrics {{ margin: 20px 0; font-size: 14px; }}
            .event {{ background: #111; padding: 10px; margin: 5px 0; border-left: 3px solid #d4a017; }}
            .red {{ color: #d97757; }}
            .green {{ color: #19c39a; }}
            .yellow {{ color: #d4a017; }}
        </style>
    </head>
    <body>
        <h1>◆ SECIR WEBHOOK CONSOLE ◆</h1>
        <div class="regime" id="regime">WAITING</div>
        <div class="metrics" id="metrics"></div>
        <div id="events"></div>
        <script>
            setInterval(() => {{
                fetch('/latest').then(r => r.json()).then(d => {{
                    document.getElementById('regime').textContent = d.regime || 'WAITING';
                    document.getElementById('regime').className = 'regime ' + (d.regime || 'RED').toLowerCase();
                    let metrics = `SECIR: ${{d.secir}}<br/>Rank: ${{d.secir_rank}}%<br/>Real Yield: ${{d.real_yield}}°<br/>Confirms: ${{d.real_yield_confirms ? '✓' : '✗'}}`;
                    document.getElementById('metrics').innerHTML = metrics;
                    fetch('/events').then(r => r.json()).then(e => {{
                        document.getElementById('events').innerHTML = e.slice().reverse().map(ev => 
                            '<div class="event">[' + ev.received_at.substring(11, 19) + '] ' + ev.from_regime + ' → ' + ev.to_regime + ' (Direction: ' + ev.direction + ')</div>'
                        ).join('');
                    }});
                }});
            }}, 5000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/seasonaledge', methods=['POST'])
def webhook():
    global current_state
    data = request.get_json() or request.form.to_dict()
    
    to_regime = data.get('to_regime')
    from_regime = data.get('from_regime')
    
    if not to_regime or to_regime not in VALID_REGIMES:
        return {'status': 'invalid_regime'}, 400
    
    if to_regime != current_state['regime']:
        data['received_at'] = datetime.now().isoformat()
        events.append(data)
        current_state = {
            'regime': to_regime,
            'secir': data.get('secir', 0),
            'secir_rank': data.get('secir_rank', 0),
            'secir_r': data.get('secir_r', 0),
            'real_yield': data.get('real_yield', 0),
            'real_yield_confirms': data.get('real_yield_confirms', False),
            'valuation': data.get('valuation', 'NEUTRAL'),
            'direction': data.get('direction', 'flat'),
            'timestamp': data.get('received_at')
        }
        return {'status': 'logged', 'regime': to_regime}, 200
    
    return {'status': 'duplicate_state', 'regime': to_regime}, 200

@app.route('/latest', methods=['GET'])
def latest():
    return jsonify(current_state)

@app.route('/events', methods=['GET'])
def get_events():
    return jsonify(list(events))

@app.route('/health', methods=['GET'])
def health():
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    app.run(debug=False)
