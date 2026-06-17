"""
Flask backend for the Config Audit tool.

Token handling: the PAT is accepted via POST /api/connect, held only
in the in-memory `github_client.session` singleton, and never written
to disk. If a scan hits a 401/403 mid-flight, the API returns a
distinct error code (`token_expired`) so the frontend can show an
inline re-auth prompt instead of failing silently.
"""

import threading
import webbrowser

from flask import Flask, jsonify, request, render_template

from engine.github_client import session, TokenExpiredError, RepoNotFoundError
from engine.analyzer import run_analysis

app = Flask(__name__)

# Simple in-memory job store (single-user local tool, no DB needed)
_last_result = {"data": None, "error": None, "running": False}
_lock = threading.Lock()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/connect", methods=["POST"])
def connect():
    body = request.get_json(force=True)
    token = (body or {}).get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Token is required."}), 400

    session.set_token(token)
    try:
        user = session.validate()
        return jsonify({"ok": True, "username": user.get("login")})
    except TokenExpiredError as e:
        session.clear_token()
        return jsonify({"ok": False, "error": str(e)}), 401
    except Exception as e:
        session.clear_token()
        return jsonify({"ok": False, "error": f"Could not reach GitHub: {e}"}), 502


@app.route("/api/status")
def status():
    return jsonify({"connected": session.has_token, "token_age_seconds": session.age_seconds})


@app.route("/api/scan", methods=["POST"])
def scan():
    if not session.has_token:
        return jsonify({"ok": False, "error": "Not connected. Enter your GitHub PAT first.", "code": "no_token"}), 401

    body = request.get_json(force=True)
    code_url = (body or {}).get("code_url", "").strip()
    component_cd_url = (body or {}).get("component_cd_url", "").strip()
    app_cd_url = (body or {}).get("app_cd_url", "").strip()

    if not (code_url and component_cd_url and app_cd_url):
        return jsonify({"ok": False, "error": "All three repo URLs are required."}), 400

    with _lock:
        _last_result["running"] = True
        _last_result["error"] = None

    try:
        result = run_analysis(code_url, component_cd_url, app_cd_url)
        with _lock:
            _last_result["data"] = result
            _last_result["running"] = False
        return jsonify({"ok": True, "result": _serialize(result)})
    except TokenExpiredError as e:
        session.clear_token()
        with _lock:
            _last_result["running"] = False
            _last_result["error"] = str(e)
        return jsonify({"ok": False, "error": str(e), "code": "token_expired"}), 401
    except RepoNotFoundError as e:
        with _lock:
            _last_result["running"] = False
            _last_result["error"] = str(e)
        return jsonify({"ok": False, "error": str(e), "code": "repo_not_found"}), 404
    except ValueError as e:
        with _lock:
            _last_result["running"] = False
            _last_result["error"] = str(e)
        return jsonify({"ok": False, "error": str(e), "code": "bad_url"}), 400
    except Exception as e:
        with _lock:
            _last_result["running"] = False
            _last_result["error"] = str(e)
        return jsonify({"ok": False, "error": f"Unexpected error: {e}", "code": "unknown"}), 500


def _serialize(result):
    return {
        "findings": result.findings,
        "drift": result.drift,
        "envs_detected": result.envs_detected,
        "warnings": result.warnings,
        "repo_meta": result.repo_meta,
        "summary": result.summary,
    }


@app.route("/api/disconnect", methods=["POST"])
def disconnect():
    session.clear_token()
    return jsonify({"ok": True})


def _open_browser():
    webbrowser.open("http://127.0.0.1:5057")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=5057, debug=False)
