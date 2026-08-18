from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
Ti si AI asistent za sigurnu kontrolu robotske grappler ruke.
Moraš vratiti samo JSON bez markdowna.

Dozvoljene komande:
- g = UHVATI
- f = E-STOP / PUSTI / STOP
- h = HOME
- o = OTVORI
- c = ZATEGNI
- 1 = TEST S1
- 2 = TEST S2
- ? = PING / PROVJERI STANJE

Pravila:
- Nikad ne izvršavaj direktno, samo predloži.
- Ako korisnik traži opasnu ili nejasnu akciju, vrati command=null.
- Ako sistem nije povezan, predloži command=null.
- Uvijek traži potvrdu za g, c i f.
- Vrati striktno JSON sa poljima:
  intent, command, label, confidence, explanation, requires_confirmation
"""

@app.route("/ai-command", methods=["POST"])
def ai_command():
    data = request.get_json(force=True)

    user_text = data.get("text", "")
    status = data.get("status", "unknown")
    grip = data.get("grip", 0)
    last_rx = data.get("last_rx", "")
    last_tx = data.get("last_tx", "")

    prompt = f"""
Govor korisnika: {user_text}
Status konekcije: {status}
Grip intensity: {grip}
Zadnji RX: {last_rx}
Zadnji TX: {last_tx}

Odredi najbolju komandu.
"""

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    text = response.output_text.strip()

    return app.response_class(
        response=text,
        status=200,
        mimetype="application/json"
    )

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)