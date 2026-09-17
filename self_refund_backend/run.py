from app import create_app

app = create_app()

if __name__ == "__main__":
    # Host/port/debug come from .env (FLASK_HOST, FLASK_PORT, FLASK_DEBUG).
    # Debug mode is OFF by default: the Werkzeug debugger allows remote code
    # execution and must never be exposed on a kiosk network.
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        threaded=True,
    )
