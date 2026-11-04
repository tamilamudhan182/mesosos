"""Persistent SQLite store (survives node restarts = store-carry-forward)."""
import sqlite3, json, threading, time
from .message import Message

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS msgs(id TEXT PRIMARY KEY, body TEXT, priority INT, copies REAL,
                 received REAL, delivered INT DEFAULT 0);
            CREATE TABLE IF NOT EXISTS acked(id TEXT PRIMARY KEY, t REAL);
            CREATE TABLE IF NOT EXISTS log(t REAL, event TEXT, detail TEXT);
            """)
            self.db.commit()

    def has(self, mid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM msgs WHERE id=?", (mid,)).fetchone() is not None

    def add(self, m: Message, copies: float):
        with self.lock:
            cur = self.db.execute("INSERT OR IGNORE INTO msgs(id,body,priority,copies,received) VALUES(?,?,?,?,?)",
                                  (m.id, json.dumps(m.to_dict()), m.priority, copies, time.time()))
            self.db.commit()
            return cur.rowcount == 1

    def set_copies(self, mid, copies):
        with self.lock:
            self.db.execute("UPDATE msgs SET copies=? WHERE id=?", (copies, mid)); self.db.commit()

    def get(self, mid):
        with self.lock:
            r = self.db.execute("SELECT body,copies FROM msgs WHERE id=?", (mid,)).fetchone()
        return (Message.from_dict(json.loads(r[0])), r[1]) if r else (None, 0)

    def all(self):
        with self.lock:
            rows = self.db.execute("SELECT body,copies,delivered FROM msgs ORDER BY priority DESC, received ASC").fetchall()
        return [(Message.from_dict(json.loads(b)), c, d) for b, c, d in rows]

    def ids(self):
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT id FROM msgs")]

    def mark_acked(self, mid):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO acked VALUES(?,?)", (mid, time.time()))
            self.db.execute("UPDATE msgs SET delivered=1 WHERE id=?", (mid,))
            self.db.commit()

    def acked(self):
        with self.lock:
            return {r[0] for r in self.db.execute("SELECT id FROM acked")}

    def purge(self, now=None):
        """Drop expired messages; keep acked ones only as delivered flag (copy count 0)."""
        now = now or time.time()
        dead = [m.id for m, _, _ in self.all() if m.expired(now)]
        with self.lock:
            for i in dead:
                self.db.execute("DELETE FROM msgs WHERE id=?", (i,))
            self.db.execute("UPDATE msgs SET copies=0 WHERE delivered=1")
            self.db.commit()
        return len(dead)

    def log(self, event, detail=""):
        with self.lock:
            self.db.execute("INSERT INTO log VALUES(?,?,?)", (time.time(), event, str(detail))); self.db.commit()

    def logs(self, n=100):
        with self.lock:
            return self.db.execute("SELECT t,event,detail FROM log ORDER BY t DESC LIMIT ?", (n,)).fetchall()
