import json
import os
import sqlite3
from pathlib import Path
from .models import uid, now, Source

class Store:
    """One transactional project snapshot plus append-only review history per project.

    Uploaded binary files live in SQLite, avoiding user-controlled filesystem paths.
    """
    def __init__(self, root=None):
        self.root = Path(root or os.getenv('COPILOT_DATA_DIR') or Path(__file__).resolve().parents[1] / 'data')
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'copilot.sqlite3'
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS files(project_id TEXT, source_id TEXT PRIMARY KEY, data BLOB);')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute('PRAGMA secure_delete=ON')
        return db

    def all(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT body FROM projects ORDER BY rowid')]

    def get(self, pid):
        with self.connect() as db:
            row = db.execute('SELECT body FROM projects WHERE id=?', (pid,)).fetchone()
            if not row:
                raise ValueError('项目不存在。')
            return json.loads(row[0])

    def save(self, p):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO projects VALUES (?,?)', (p['id'], json.dumps(p, ensure_ascii=False)))

    def create(self, name, scene, role):
        if not name.strip():
            raise ValueError('项目名称不能为空。')
        p = dict(id=uid(), name=name.strip(), scene=scene, role=role, created=now(), sources=[], batches=[], reviews=[], revision=0, api_calls=0)
        self.save(p)
        return p

    def add(self, p, source: Source, data: bytes):
        if any(s['sha256'] == source.sha256 for s in p['sources']):
            raise ValueError('重复文件：相同内容已导入。')
        p['sources'].append(source.model_dump())
        self.invalidate(p)
        with self.connect() as db:
            db.execute('INSERT INTO files VALUES (?,?,?)', (p['id'], source.source_id, data))
            db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p, ensure_ascii=False), p['id']))

    def invalidate(self, p):
        p['revision'] += 1
        for b in p['batches']:
            b['stale'] = True

    def remove(self, p, sid):
        p['sources'] = [s for s in p['sources'] if s['source_id'] != sid]
        self.invalidate(p)
        with self.connect() as db:
            db.execute('DELETE FROM files WHERE project_id=? AND source_id=?', (p['id'], sid))
            db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p, ensure_ascii=False), p['id']))

    def delete(self, pid):
        with self.connect() as db:
            db.execute('DELETE FROM files WHERE project_id=?', (pid,))
            db.execute('DELETE FROM projects WHERE id=?', (pid,))

    def reserve_call(self, p):
        # Persist before network IO; failed attempts also count. No automatic retry.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = json.loads(db.execute('SELECT body FROM projects WHERE id=?', (p['id'],)).fetchone()[0])
            if current['api_calls'] >= 20:
                raise ValueError('本项目已达到 20 次模型调用上限，请创建新项目。')
            p['api_calls'] = current['api_calls'] + 1
            db.execute('UPDATE projects SET body=? WHERE id=?', (json.dumps(p, ensure_ascii=False), p['id']))
