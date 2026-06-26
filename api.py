import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel

from mcp_server import mcp

_mcp_app = mcp.http_app(path="/")

# PostgreSQL への接続文字列。
# lnar 上ではマネージドDB (または外部DB) の接続文字列が DATABASE_URL として
# 自動注入される。ローカル開発用にローカル PostgreSQL を既定値にしておく。
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
)

# 同期コネクションプール。FastAPI の sync エンドポイントはスレッドプールで
# 実行されるため、ブロッキングな psycopg 呼び出しでも問題ない。
pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=5, open=False)


def _init_schema() -> None:
    """起動時に notes テーブルを作成する (冪等)。"""
    with pool.connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id      UUID PRIMARY KEY,
                title   TEXT NOT NULL,
                content TEXT NOT NULL,
                tags    TEXT[] NOT NULL DEFAULT '{}'
            )
            """
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB プールを開いてスキーマを用意する。
    pool.open()
    pool.wait()
    _init_schema()
    # FastMCP の StreamableHTTPSessionManager は親 ASGI の lifespan で
    # 初期化される。これを伝搬しないと POST /mcp/ が
    # "task group was not initialized" で 500 になる。
    async with _mcp_app.lifespan(app):
        yield
    pool.close()


app = FastAPI(title="Notes API (PostgreSQL)", version="1.0.0", lifespan=lifespan)

# MCP Streamable HTTP エンドポイントを /mcp にマウント
app.mount("/mcp", _mcp_app)


@app.get("/health")
def health():
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}


@app.get("/version")
def version():
    """API のバージョン情報を返す"""
    return {"name": app.title, "version": app.version}


class NoteCreate(BaseModel):
    title: str
    content: str
    tags: list[str] = []


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list[str]] = None


class Note(BaseModel):
    id: str
    title: str
    content: str
    tags: list[str] = []


# 一覧/取得で共通の SELECT 列。id は UUID 型なので text にして返す。
_NOTE_COLUMNS = "id::text AS id, title, content, tags"


@app.get("/notes", response_model=list[Note])
def list_notes(tag: Optional[str] = None):
    """ノートの一覧を返す。`tag` を指定するとそのタグを持つノートのみを返す。"""
    with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        if tag is not None:
            cur.execute(
                f"SELECT {_NOTE_COLUMNS} FROM notes "
                "WHERE %s = ANY(tags) ORDER BY title",
                (tag,),
            )
        else:
            cur.execute(f"SELECT {_NOTE_COLUMNS} FROM notes ORDER BY title")
        return cur.fetchall()


@app.get("/notes/count")
def count_notes():
    """保存されているノートの件数を返す"""
    with pool.connection() as conn:
        (count,) = conn.execute("SELECT count(*) FROM notes").fetchone()
    return {"count": count}


@app.get("/notes/tags", response_model=list[str])
def list_tags():
    """全ノートに付与されているタグの一覧を重複なし・昇順で返す"""
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT unnest(tags) AS tag FROM notes ORDER BY tag"
        ).fetchall()
    return [row[0] for row in rows]


@app.post("/notes", response_model=Note, status_code=201)
def create_note(body: NoteCreate):
    """新しいノートを作成する"""
    note_id = str(uuid.uuid4())
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO notes (id, title, content, tags) VALUES (%s, %s, %s, %s)",
            (note_id, body.title, body.content, list(body.tags)),
        )
    return {
        "id": note_id,
        "title": body.title,
        "content": body.content,
        "tags": list(body.tags),
    }


@app.delete("/notes")
def delete_all_notes():
    """すべてのノートを削除する。

    0件のときは 204 No Content、それ以外は削除件数を返す。
    """
    with pool.connection() as conn:
        deleted = conn.execute("DELETE FROM notes").rowcount
    if deleted == 0:
        return Response(status_code=204)
    return {"deleted": deleted}


@app.get("/notes/{note_id}", response_model=Note)
def get_note(note_id: str):
    """IDでノートを取得する"""
    with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT {_NOTE_COLUMNS} FROM notes WHERE id::text = %s", (note_id,)
        )
        note = cur.fetchone()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.put("/notes/{note_id}", response_model=Note)
def update_note(note_id: str, body: NoteUpdate):
    """ノートのタイトル、内容、またはタグを更新する"""
    assignments: list[str] = []
    params: list = []
    if body.title is not None:
        assignments.append("title = %s")
        params.append(body.title)
    if body.content is not None:
        assignments.append("content = %s")
        params.append(body.content)
    if body.tags is not None:
        assignments.append("tags = %s")
        params.append(list(body.tags))

    with pool.connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        if assignments:
            params.append(note_id)
            cur.execute(
                f"UPDATE notes SET {', '.join(assignments)} "
                f"WHERE id::text = %s RETURNING {_NOTE_COLUMNS}",
                params,
            )
        else:
            cur.execute(
                f"SELECT {_NOTE_COLUMNS} FROM notes WHERE id::text = %s", (note_id,)
            )
        note = cur.fetchone()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: str):
    """ノートを削除する"""
    with pool.connection() as conn:
        deleted = conn.execute(
            "DELETE FROM notes WHERE id::text = %s", (note_id,)
        ).rowcount
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Note not found")


@app.get("/stream")
async def stream(max_count: int = 10):
    """
    lnar log streaming 検証用エンドポイント。
    1秒ごとに stdout に print する。HTTP レスポンスは print 完了後に返る。
    """
    for i in range(1, max_count + 1):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Message {i}/{max_count} at {current_time}")
        await asyncio.sleep(1.0)
    return {"status": "done", "count": max_count}
