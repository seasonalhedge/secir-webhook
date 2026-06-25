from flask import Flask, jsonify, render_template_string, request
from datetime import datetime

app = Flask(__name__)
events = []
current_state = {"regime": "RED", "secir": 0.5, "timestamp": None}

@app.route('/', methods=['GET'])
def dashboard():
    return '<h1>SECIR Webhook</h1><div id="regime">WAITING</div>'

@app.route('/seasonaledge', methods=['POST'])
def webhook():
    global current_state
    data = request.get_json()
    if data.get('to_regime') != current_state['regime']:
        events.append(data)
        current_state = {'regime': data.get('to_regime'), 'secir': data.get('secir')}
        return {'status': 'logged'}, 200
    return {'status': 'duplicate_state'}, 200

@app.route('/latest', methods=['GET'])
def latest():
    return current_state

@app.route('/events', methods=['GET'])
def get_events():
    return events

if __name__ == '__main__':
    app.run(debug=False)
