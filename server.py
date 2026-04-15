from flask import Flask
from config import LISTEN_PORT
from routes.health import health_bp
from routes.get_messages import get_messages_bp
from routes.get_photos import get_photos_bp
from routes.get_whisper import get_whisper_bp
from routes.get_scheduled import get_scheduled_bp
from routes.schedule_messages import schedule_messages_bp

app = Flask(__name__)
app.register_blueprint(health_bp)
app.register_blueprint(get_messages_bp)
app.register_blueprint(get_photos_bp)
app.register_blueprint(get_whisper_bp)
app.register_blueprint(get_scheduled_bp)
app.register_blueprint(schedule_messages_bp)

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=LISTEN_PORT, threads=1)