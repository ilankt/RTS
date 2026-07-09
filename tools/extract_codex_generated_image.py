"""Extract a generated image from the local Codex log database."""
from __future__ import annotations

import argparse
import base64
import json
import re
import sqlite3
from pathlib import Path


def iter_columns(conn):
    for (table_name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        for row in conn.execute(f"PRAGMA table_info({table_name})"):
            column_name = row[1]
            column_type = (row[2] or "").upper()
            if "TEXT" in column_type or "BLOB" in column_type or column_type == "":
                yield table_name, column_name


def iter_matches(conn, needle):
    for table_name, column_name in iter_columns(conn):
        try:
            rows = conn.execute(
                f"SELECT rowid, {column_name} FROM {table_name} WHERE {column_name} LIKE ?",
                (f"%{needle}%",),
            )
            for rowid, value in rows:
                if isinstance(value, bytes):
                    try:
                        value = value.decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                if isinstance(value, str) and needle in value:
                    yield table_name, column_name, rowid, value
        except sqlite3.DatabaseError:
            continue


def find_image_result(obj, generation_id):
    if isinstance(obj, dict):
        if obj.get("id") == generation_id and isinstance(obj.get("result"), str):
            return obj["result"]
        for value in obj.values():
            found = find_image_result(value, generation_id)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = find_image_result(value, generation_id)
            if found:
                return found
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("generation_id")
    parser.add_argument("--db", default=str(Path.home() / ".codex" / "logs_2.sqlite"))
    parser.add_argument("--out", required=True)
    parser.add_argument("--schema", action="store_true")
    parser.add_argument("--dump", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    if args.schema:
        for (sql,) in conn.execute("SELECT sql FROM sqlite_master WHERE type='table'"):
            print(sql)
        return 0

    if args.dump:
        for row in conn.execute(
            "SELECT id, ts, target, substr(feedback_log_body, 1, 2000) "
            "FROM logs WHERE feedback_log_body LIKE ? ORDER BY id DESC LIMIT 20",
            (f"%{args.generation_id}%",),
        ):
            print(json.dumps(row, ensure_ascii=False))
        return 0

    for table_name, column_name, rowid, value in iter_matches(conn, args.generation_id):
        candidates = [value]
        for line in value.splitlines():
            if args.generation_id in line:
                candidates.append(line)
        for candidate in candidates:
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            result = find_image_result(obj, args.generation_id)
            if result:
                image_bytes = base64.b64decode(result)
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_bytes(image_bytes)
                print(f"wrote {args.out} from {table_name}.{column_name} rowid={rowid}")
                return 0

    # The newest log rows can be present in the SQLite WAL before a checkpoint.
    # Fall back to a byte-level scan of the DB and WAL files.
    for db_path in [Path(args.db), Path(args.db + "-wal")]:
        if not db_path.exists():
            continue
        text = db_path.read_bytes().decode("utf-8", errors="ignore")
        pos = text.find(args.generation_id)
        if pos < 0:
            continue
        window = text[max(0, pos - 5000): pos + 2_000_000]
        match = re.search(r'"result"\s*:\s*"([A-Za-z0-9+/=]+)"', window)
        if match:
            image_bytes = base64.b64decode(match.group(1))
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_bytes(image_bytes)
            print(f"wrote {args.out} from raw scan of {db_path}")
            return 0

    raise SystemExit(f"generation id not found or result unavailable: {args.generation_id}")


if __name__ == "__main__":
    raise SystemExit(main())
