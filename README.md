# Fieldnotes

Minimal Flask backend for the topic/field-notes tracker. Single-user tool —
no user model, no login in the code. Auth is handled via HTTP Basic Auth
in front of the app (nginx), see below.

## Run locally

```bash
cd fieldnotes-app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

→ http://127.0.0.1:5000

`fieldnotes.db` (SQLite) is created automatically on first run, under `instance/`.

## Data model

- **Topic**: `title`, `status` (`visit` / `mixed` / `desk` / `null`), `gap_notes`, `done`
- **FieldNote**: belongs to a topic — `date`, `place`, `lat`/`lng` (GPS coordinates), `text`, `photos`
- **Photo**: belongs to a field note — stored as a file under `static/uploads/`

## API

| Method | Path                              | Purpose                        |
|--------|-----------------------------------|---------------------------------|
| GET    | `/api/topics`                     | All topics incl. field notes   |
| POST   | `/api/topics`                     | Create new topic (`{title}`)   |
| PATCH  | `/api/topics/<id>`                | Update topic                    |
| DELETE | `/api/topics/<id>`                | Delete topic + its field notes  |
| POST   | `/api/topics/<id>/fieldnotes`     | Create empty field note         |
| PATCH  | `/api/fieldnotes/<id>`            | Update field note (incl. `lat`/`lng`) |
| DELETE | `/api/fieldnotes/<id>`            | Delete field note (+ its photos)  |
| POST   | `/api/fieldnotes/<id>/photos`     | Upload a photo (multipart, field `photo`) |
| DELETE | `/api/photos/<id>`                | Delete a photo                    |

## Location capture

Each field note can carry a GPS location, set either via the browser's
Geolocation API ("Use current location" button) or by clicking/dragging a
marker on the embedded map (Leaflet + OpenStreetMap tiles, loaded from
`unpkg.com` — no API key needed). When a location is set and the `place`
text field is still empty, it's auto-filled via reverse geocoding against
the public Nominatim API (`nominatim.openstreetmap.org`); the field stays
freely editable afterwards.

## Deployment on altner.cloud (fieldnotes.altner.cloud)

1. **Get the project onto the server**, e.g. to `/var/www/fieldnotes-app`.

2. **Set up virtualenv + Gunicorn** there:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **systemd service** (`/etc/systemd/system/fieldnotes.service`):
   ```ini
   [Unit]
   Description=Fieldnotes Flask App
   After=network.target

   [Service]
   User=deploy
   WorkingDirectory=/var/www/fieldnotes-app
   ExecStart=/var/www/fieldnotes-app/venv/bin/gunicorn -w 2 -b 127.0.0.1:8001 app:app
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl enable --now fieldnotes
   ```

4. **Prepare HTTP Basic Auth:**
   ```bash
   sudo apt install apache2-utils   # for htpasswd, if not already installed
   sudo htpasswd -c /etc/nginx/.htpasswd_fieldnotes adrian
   ```

5. **nginx vhost** (`/etc/nginx/sites-available/fieldnotes.altner.cloud`):
   ```nginx
   server {
       listen 80;
       server_name fieldnotes.altner.cloud;

       auth_basic "Field Notes";
       auth_basic_user_file /etc/nginx/.htpasswd_fieldnotes;

       location / {
           proxy_pass http://127.0.0.1:8001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```
   ```bash
   sudo ln -s /etc/nginx/sites-available/fieldnotes.altner.cloud /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   sudo certbot --nginx -d fieldnotes.altner.cloud
   ```

6. **DNS**: A record `fieldnotes.altner.cloud` → server IP.

Once the certificate is in place, the Basic Auth prompt runs over HTTPS, so
credentials aren't sent in plain text.

Note: photo uploads are capped at 10 MB each (`MAX_CONTENT_LENGTH` in
`app.py`) — if nginx is configured with a stricter `client_max_body_size`,
raise it to match or uploads will be rejected by nginx before reaching Flask.

## Possible next steps

- SQLite backups (e.g. a daily `cron` job that copies `fieldnotes.db` and
  the `static/uploads/` folder)
- Ordering/sorting of topics (currently: newest first)
- Export endpoint (`/api/export`) for a JSON backup directly from the app
