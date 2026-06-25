"""
MCP server that wraps the Notes REST API (PostgreSQL-backed).

Usage:
  1. Start the FastAPI server:   uvicorn api:app --reload
  2. Start this MCP server:      python mcp_server.py
     or via stdio transport:     mcp run mcp_server.py
"""

import json

import httpx
from fastmcp import FastMCP

API_BASE_URL = "http://localhost:8000"

mcp = FastMCP("notes-mcp-server")


def _get(path: str, params: dict | None = None) -> dict | list:
    with httpx.Client() as client:
        r = client.get(f"{API_BASE_URL}{path}", params=params)
        r.raise_for_status()
        return r.json()


def _post(path: str, payload: dict) -> dict:
    with httpx.Client() as client:
        r = client.post(f"{API_BASE_URL}{path}", json=payload)
        r.raise_for_status()
        return r.json()


def _put(path: str, payload: dict) -> dict:
    with httpx.Client() as client:
        r = client.put(f"{API_BASE_URL}{path}", json=payload)
        r.raise_for_status()
        return r.json()


def _delete(path: str) -> None:
    with httpx.Client() as client:
        r = client.delete(f"{API_BASE_URL}{path}")
        r.raise_for_status()


def _delete_json(path: str) -> dict:
    with httpx.Client() as client:
        r = client.delete(f"{API_BASE_URL}{path}")
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"deleted": 0}
        return r.json()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_notes(tag: str | None = None) -> str:
    """保存されているノートの一覧を取得する。

    Args:
        tag: 指定するとそのタグを持つノートのみを返す（省略可）
    """
    params = {"tag": tag} if tag is not None else None
    notes = _get("/notes", params=params)
    return json.dumps(notes, ensure_ascii=False, indent=2)


@mcp.tool()
def create_note(title: str, content: str, tags: list[str] | None = None) -> str:
    """新しいノートを作成する。

    Args:
        title: ノートのタイトル
        content: ノートの本文
        tags: ノートに付与するタグの一覧（省略可）
    """
    payload: dict = {"title": title, "content": content}
    if tags is not None:
        payload["tags"] = tags
    note = _post("/notes", payload)
    return json.dumps(note, ensure_ascii=False, indent=2)


@mcp.tool()
def count_notes() -> str:
    """保存されているノートの件数を取得する。"""
    result = _get("/notes/count")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_tags() -> str:
    """全ノートに付与されているタグの一覧を重複なし・昇順で取得する。"""
    tags = _get("/notes/tags")
    return json.dumps(tags, ensure_ascii=False, indent=2)


@mcp.tool()
def get_note(note_id: str) -> str:
    """IDを指定してノートを取得する。

    Args:
        note_id: 取得するノートのID
    """
    note = _get(f"/notes/{note_id}")
    return json.dumps(note, ensure_ascii=False, indent=2)


@mcp.tool()
def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """ノートのタイトル、本文、またはタグを更新する。

    Args:
        note_id: 更新するノートのID
        title: 新しいタイトル（省略可）
        content: 新しい本文（省略可）
        tags: 新しいタグ一覧（省略可、指定するとタグを完全に置き換える）
    """
    payload = {
        k: v
        for k, v in {"title": title, "content": content, "tags": tags}.items()
        if v is not None
    }
    note = _put(f"/notes/{note_id}", payload)
    return json.dumps(note, ensure_ascii=False, indent=2)


@mcp.tool()
def delete_note(note_id: str) -> str:
    """ノートを削除する。

    Args:
        note_id: 削除するノートのID
    """
    _delete(f"/notes/{note_id}")
    return f"Note {note_id} deleted successfully."


@mcp.tool()
def delete_all_notes() -> str:
    """保存されているすべてのノートを削除する。"""
    result = _delete_json("/notes")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run()
