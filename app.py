from flask import Flask, request, jsonify, render_template
from terminal_backend import TerminalBackend

app = Flask(__name__, static_folder="static", template_folder="templates")
tb = TerminalBackend()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/run", methods=["POST"])
def run_command():
    data = request.get_json() or {}
    cmd = data.get("command", "")
    out = tb.execute(cmd)
    return jsonify({"output": out, "cwd": tb.cmd_pwd(None)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)