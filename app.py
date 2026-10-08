"""
JusDOrange Cloud Gateway - Mini app Flask pour Render.com
Permet de deposer et recuperer des dumps depuis n'importe ou.

Endpoints:
  GET  /health         - Health check
  GET  /list           - Liste des fichiers
  POST /upload         - Upload (Authorization: Bearer TOKEN)
  GET  /download/<f>   - Telechargement
  GET  /info/<f>       - Infos fichier

Deploy sur Render :
  - Type : Web Service
  - Build : pip install -r requirements.txt
  - Start : gunicorn app:app
"""
import os, hashlib, secrets
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort

app = Flask(__name__)

# Config
_default_data = "/data" if os.path.exists("/data") else "/tmp/jdo_cloud_data"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default_data))
DATA_DIR.mkdir(parents=True, exist_ok=True)

TOKEN = os.environ.get("CLOUD_TOKEN", "jdo_render_2026_change_me")

# Limite upload
MAX_UPLOAD = 500 * 1024 * 1024  # 500 Mo


def check_auth(req):
    """Verifie le header Authorization."""
    auth = req.headers.get("Authorization", "")
    return auth == f"Bearer {TOKEN}"


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "jus-dorange-cloud",
        "data_dir": str(DATA_DIR),
        "files_count": len(list(DATA_DIR.iterdir())) if DATA_DIR.exists() else 0,
        "ts": int(datetime.now().timestamp()),
    })


@app.route("/list")
def list_files():
    """Liste tous les fichiers stockes."""
    files = []
    for f in DATA_DIR.iterdir():
        if f.is_file():
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "sha256": _sha256(f),
            })
    files.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return jsonify({"files": files, "total": len(files)})


@app.route("/upload", methods=["POST"])
def upload():
    """Upload un fichier (auth obligatoire)."""
    if not check_auth(request):
        abort(401, "Token invalide")

    # Le fichier est dans request.data (raw bytes)
    # Le nom vient du header X-Filename
    filename = request.headers.get("X-Filename", f"upload_{int(datetime.now().timestamp())}")
    data = request.data

    if len(data) == 0:
        return jsonify({"error": "Fichier vide"}), 400
    if len(data) > MAX_UPLOAD:
        return jsonify({"error": f"Fichier > {MAX_UPLOAD//1024//1024}MB"}), 413

    # Nettoie le nom (pas de ..)
    safe_name = Path(filename).name
    if not safe_name or safe_name.startswith("."):
        return jsonify({"error": "Nom invalide"}), 400

    out_path = DATA_DIR / safe_name
    out_path.write_bytes(data)

    sha = hashlib.sha256(data).hexdigest()
    return jsonify({
        "ok": True,
        "filename": safe_name,
        "size_bytes": len(data),
        "size_mb": round(len(data) / 1024 / 1024, 2),
        "sha256": sha,
        "ts": int(datetime.now().timestamp()),
    })


@app.route("/download/<path:filename>")
def download(filename):
    """Telecharge un fichier."""
    safe_name = safe_name_only(filename)
    file_path = DATA_DIR / safe_name
    if not file_path.exists():
        abort(404, "Fichier introuvable")

    return send_file(
        file_path,
        as_attachment=True,
        download_name=safe_name,
    )


@app.route("/info/<path:filename>")
def info(filename):
    """Infos d'un fichier."""
    safe_name = safe_name_only(filename)
    file_path = DATA_DIR / safe_name
    if not file_path.exists():
        abort(404, "Fichier introuvable")

    stat = file_path.stat()
    return jsonify({
        "name": safe_name,
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "sha256": _sha256(file_path),
    })


@app.route("/delete/<path:filename>", methods=["DELETE"])
def delete(filename):
    """Supprime un fichier (auth obligatoire)."""
    if not check_auth(request):
        abort(401)
    safe_name = safe_name_only(filename)
    file_path = DATA_DIR / safe_name
    if not file_path.exists():
        abort(404)
    file_path.unlink()
    return jsonify({"ok": True, "deleted": safe_name})


def safe_name_only(name: str) -> str:
    """Securise un nom de fichier."""
    return Path(name).name


def _sha256(p: Path) -> str:
    """Calcule le SHA256."""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)