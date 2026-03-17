import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

NEW_EVENT_COLUMNS = [
    ("id", "INTEGER PRIMARY KEY"),
    ("novel_id", "TEXT"),
    ("event_id", "INTEGER"),
    ("description", "TEXT"),
    ("outline_description", "TEXT"),
    ("actual_summary", "TEXT"),
    ("goal", "TEXT"),
    ("obstacle", "TEXT"),
    ("cool_point_type", "TEXT"),
    ("payoff_type", "TEXT"),
    ("growth_reward", "TEXT"),
    ("status_reward", "TEXT"),
    ("cliffhanger", "TEXT"),
    ("ending_phase", "TEXT DEFAULT 'normal'"),
    ("location", "TEXT"),
    ("time_duration", "TEXT"),
    ("core_conflict", "TEXT"),
    ("foreshadowing", "TEXT"),
    ("linked_characters", "TEXT"),
    ("event_world_snapshot_update", "TEXT"),
    ("event_foreshadow_updates", "TEXT DEFAULT '[]'"),
    ("event_growth_updates", "TEXT DEFAULT '{}'"),
    ("event_lorebook_updates", "TEXT DEFAULT '{}'"),
    ("entering_characters", "TEXT DEFAULT '[]'"),
    ("exiting_characters", "TEXT DEFAULT '[]'"),
    ("is_written", "BOOLEAN DEFAULT 0"),
    ("status", "TEXT DEFAULT 'planned'"),
    ("is_locked", "BOOLEAN DEFAULT 0"),
    ("is_user_edited", "BOOLEAN DEFAULT 0"),
    ("source", "TEXT DEFAULT 'ai'"),
]


def quote(name: str) -> str:
    return f'"{name}"'


def backup_db(db_path: Path) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".events_backup_{stamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def existing_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(events)").fetchall()
    return {str(row[1]) for row in rows}


def rebuild_events_table(db_path: Path) -> tuple[int, Path]:
    backup_path = backup_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN")
        old_columns = existing_columns(conn)
        if not old_columns:
            conn.execute("ROLLBACK")
            raise RuntimeError(f"{db_path.name} 不存在 events 表")

        create_sql = "CREATE TABLE events_new (\n  " + ",\n  ".join(
            f"{quote(name)} {definition}" for name, definition in NEW_EVENT_COLUMNS
        ) + "\n)"
        conn.execute(create_sql)

        select_exprs = []
        insert_columns = []
        for name, _definition in NEW_EVENT_COLUMNS:
            insert_columns.append(quote(name))
            if name in old_columns:
                select_exprs.append(quote(name))
            elif name == "entering_characters":
                select_exprs.append("'[]'")
            elif name == "exiting_characters":
                select_exprs.append("'[]'")
            elif name == "event_foreshadow_updates":
                select_exprs.append("'[]'")
            elif name == "event_growth_updates":
                select_exprs.append("'{}'")
            elif name == "event_lorebook_updates":
                select_exprs.append("'{}'")
            elif name == "event_world_snapshot_update":
                select_exprs.append("NULL")
            elif name == "status":
                select_exprs.append("'planned'")
            elif name == "source":
                select_exprs.append("'ai'")
            else:
                select_exprs.append("NULL")

        conn.execute(
            f"INSERT INTO events_new ({', '.join(insert_columns)}) "
            f"SELECT {', '.join(select_exprs)} FROM events"
        )
        count = int(conn.execute("SELECT COUNT(*) FROM events_new").fetchone()[0] or 0)

        conn.execute("DROP TABLE events")
        conn.execute("ALTER TABLE events_new RENAME TO events")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_novel_event ON events(novel_id, event_id)")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return count, backup_path


def iter_target_dbs(novel_ids: list[str]) -> list[Path]:
    if novel_ids:
        return [DATA_DIR / f"{novel_id}.sqlite" for novel_id in novel_ids]
    return sorted(DATA_DIR.glob("n_*.sqlite"))


def main() -> None:
    parser = argparse.ArgumentParser(description="重建 events 表，物理删除测试阶段废弃列")
    parser.add_argument("novel_ids", nargs="*", help="指定要处理的 novel_id；留空则处理 backend/data 下全部 n_*.sqlite")
    args = parser.parse_args()

    targets = iter_target_dbs(args.novel_ids)
    if not targets:
        print("未找到可处理的小说数据库。")
        return

    for db_path in targets:
        if not db_path.exists():
            print(f"跳过不存在的数据库: {db_path.name}")
            continue
        count, backup_path = rebuild_events_table(db_path)
        print(f"已重建 {db_path.name} 的 events 表，迁移 {count} 条事件，备份: {backup_path.name}")


if __name__ == "__main__":
    main()
