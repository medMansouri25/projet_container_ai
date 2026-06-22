from flask import Flask, jsonify


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/api/detect", methods=["POST"])
    def detect():
        return jsonify({"error": "Not implemented"}), 501

    @app.route("/api/save", methods=["POST"])
    def save():
        return jsonify({"error": "Not implemented"}), 501

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
