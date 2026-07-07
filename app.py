"""
Fieldnotes — minimal Flask backend
-----------------------------------
Single-user tool: topic-level editorial tracking (visit / mixed / desk research)
plus nested field notes (date, place, GPS location, text, photos) per topic.

Storage: SQLite via SQLAlchemy. No user model — auth is expected to be handled
by nginx (HTTP Basic Auth) in front of this app. See README.md.

Run locally:
    pip install -r requirements.txt
    python app.py
    -> http://127.0.0.1:5000
"""

import os
import uuid
from datetime import datetime, date
from flask import Flask, jsonify, request, render_template, abort
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///fieldnotes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB per upload (phone camera photos)

db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(app.static_folder, "uploads")
ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "heic"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Topic(db.Model):
    __tablename__ = "topics"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(20), nullable=True)  # 'visit' | 'mixed' | 'desk' | None
    gap_notes = db.Column(db.Text, default="")
    done = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    field_notes = db.relationship(
        "FieldNote", backref="topic", cascade="all, delete-orphan", order_by="FieldNote.id"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "gapNotes": self.gap_notes or "",
            "done": self.done,
            "fieldNotes": [fn.to_dict() for fn in self.field_notes],
        }


class FieldNote(db.Model):
    __tablename__ = "field_notes"

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    date = db.Column(db.String(20), default="")   # stored as ISO string, e.g. "2026-07-08"
    place = db.Column(db.String(200), default="")
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    text = db.Column(db.Text, default="")

    photos = db.relationship(
        "Photo", cascade="all, delete-orphan", order_by="Photo.id"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date or "",
            "place": self.place or "",
            "lat": self.lat,
            "lng": self.lng,
            "text": self.text or "",
            "photos": [ph.to_dict() for ph in self.photos],
        }


class Photo(db.Model):
    __tablename__ = "photos"

    id = db.Column(db.Integer, primary_key=True)
    field_note_id = db.Column(db.Integer, db.ForeignKey("field_notes.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "url": f"/static/uploads/{self.filename}",
        }

    def delete_file(self):
        path = os.path.join(UPLOAD_FOLDER, self.filename)
        if os.path.exists(path):
            os.remove(path)


with app.app_context():
    db.create_all()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API — Topics
# ---------------------------------------------------------------------------

@app.route("/api/topics", methods=["GET"])
def list_topics():
    topics = Topic.query.order_by(Topic.created_at.desc()).all()
    return jsonify([t.to_dict() for t in topics])


@app.route("/api/topics", methods=["POST"])
def create_topic():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        abort(400, description="title is required")
    topic = Topic(title=title)
    db.session.add(topic)
    db.session.commit()
    return jsonify(topic.to_dict()), 201


@app.route("/api/topics/<int:topic_id>", methods=["PATCH"])
def update_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    data = request.get_json(force=True) or {}

    if "title" in data:
        topic.title = data["title"]
    if "status" in data:
        topic.status = data["status"]  # None, 'visit', 'mixed', 'desk'
    if "gapNotes" in data:
        topic.gap_notes = data["gapNotes"]
    if "done" in data:
        topic.done = bool(data["done"])

    db.session.commit()
    return jsonify(topic.to_dict())


@app.route("/api/topics/<int:topic_id>", methods=["DELETE"])
def delete_topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    for fn in topic.field_notes:
        for photo in fn.photos:
            photo.delete_file()
    db.session.delete(topic)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# API — Field notes (nested under a topic)
# ---------------------------------------------------------------------------

@app.route("/api/topics/<int:topic_id>/fieldnotes", methods=["POST"])
def create_fieldnote(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    fn = FieldNote(topic_id=topic.id, date="", place="", text="")
    db.session.add(fn)
    db.session.commit()
    return jsonify(fn.to_dict()), 201


@app.route("/api/fieldnotes/<int:fn_id>", methods=["PATCH"])
def update_fieldnote(fn_id):
    fn = FieldNote.query.get_or_404(fn_id)
    data = request.get_json(force=True) or {}

    if "date" in data:
        fn.date = data["date"]
    if "place" in data:
        fn.place = data["place"]
    if "lat" in data:
        fn.lat = data["lat"]
    if "lng" in data:
        fn.lng = data["lng"]
    if "text" in data:
        fn.text = data["text"]

    db.session.commit()
    return jsonify(fn.to_dict())


@app.route("/api/fieldnotes/<int:fn_id>", methods=["DELETE"])
def delete_fieldnote(fn_id):
    fn = FieldNote.query.get_or_404(fn_id)
    for photo in fn.photos:
        photo.delete_file()
    db.session.delete(fn)
    db.session.commit()
    return "", 204


# ---------------------------------------------------------------------------
# API — Photos (nested under a field note)
# ---------------------------------------------------------------------------

@app.route("/api/fieldnotes/<int:fn_id>/photos", methods=["POST"])
def upload_photo(fn_id):
    fn = FieldNote.query.get_or_404(fn_id)
    file = request.files.get("photo")
    if not file or not file.filename:
        abort(400, description="photo file is required")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_PHOTO_EXTENSIONS:
        abort(400, description="unsupported file type")

    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))

    photo = Photo(field_note_id=fn.id, filename=filename)
    db.session.add(photo)
    db.session.commit()
    return jsonify(photo.to_dict()), 201


@app.route("/api/photos/<int:photo_id>", methods=["DELETE"])
def delete_photo(photo_id):
    photo = Photo.query.get_or_404(photo_id)
    photo.delete_file()
    db.session.delete(photo)
    db.session.commit()
    return "", 204


if __name__ == "__main__":
    app.run(debug=True)
