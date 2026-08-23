"""One-time local setup: import pre-existing tmp/*.json sidecar data (from
before the Postgres metadata migration) into the local dev user's rows.

Run once per machine, after `docker compose up -d db` and `alembic upgrade
head`, from `fastApi-app/`:

    python scripts/migrate_local_sidecars_to_db.py

Safe to re-run: sessions/objects already present in the DB are skipped.
No-op (prints and exits) if the old sidecar files aren't present, e.g. on a
machine that never had pre-Postgres local data.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.object_metadata import ObjectMetadata, get_object_by_uuid, save_object_metadata
from core.repositories.session_repo import is_session_registered, register_uid, set_session_name
from db.models import SessionRow
from db.session import session_scope

TMP = Path(__file__).resolve().parents[1] / "tmp"


def _load_json(name: str) -> dict | list:
    path = TMP / name
    if not path.exists():
        return {} if name != "sessions.json" else []
    return json.loads(path.read_text())


def main() -> None:
    sessions = _load_json("sessions.json")
    if not sessions:
        print("No tmp/sessions.json found (or empty) — nothing to migrate.")
        return

    names = _load_json("names.json")
    timestamps = _load_json("session_timestamps.json")

    sessions_added = objects_added = 0

    for uid in sessions:
        is_new_session = not is_session_registered(uid)
        register_uid(uid)
        if is_new_session:
            sessions_added += 1

        name = names.get(uid)
        if name:
            try:
                set_session_name(uid, name)
            except ValueError:
                pass  # name taken by another session already in the DB

        ts = timestamps.get(uid)
        if ts:
            with session_scope() as db:
                row = db.get(SessionRow, uid)
                if row is not None:
                    row.last_changed = datetime.fromisoformat(ts)
                    row.created_at = datetime.fromisoformat(ts)

        for meta_file in sorted((TMP / "images").glob(f"{uid}_*_meta.json")):
            data = json.loads(meta_file.read_text())
            if get_object_by_uuid(data["uuid"]) is not None:
                continue  # already migrated
            save_object_metadata(ObjectMetadata(**data))
            objects_added += 1

    print(f"Migrated {sessions_added} new session(s), {objects_added} new object(s) "
          f"into Postgres (of {len(sessions)} sessions in sidecar files).")


if __name__ == "__main__":
    main()
