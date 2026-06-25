# test-lnar-hosting-python-postgres

Notes の CRUD を提供する FastAPI サーバーと、それを MCP ツールとして公開する MCP サーバーのサンプルです。

**`test-lnar-hosting-python` の PostgreSQL 版**です。元のサンプルがデータをプロセス内メモリ（dict）に
持っていたのに対し、本リポジトリは **PostgreSQL にデータを永続化** します。プロセスを再起動・
再デプロイしてもノートは消えません。

FastAPI の `/mcp` に MCP Streamable HTTP エンドポイントをマウントしているため、**1プロセス・1ポートで REST API と MCP の両方を提供します**。

## データストア

- ノートは PostgreSQL の `notes` テーブルに保存されます（起動時に自動作成）。
- 接続先は環境変数 **`DATABASE_URL`** から読み込みます（例: `postgresql://user:pass@host:5432/dbname`）。
  - lnar 上では、設置したマネージドDB（または接続した外部DB）の接続文字列が
    `DATABASE_URL` として自動注入されます。
  - ローカル開発では未設定時に `postgresql://postgres:postgres@localhost:5432/postgres` を使います。

```sql
CREATE TABLE notes (
    id      UUID PRIMARY KEY,
    title   TEXT NOT NULL,
    content TEXT NOT NULL,
    tags    TEXT[] NOT NULL DEFAULT '{}'
);
```

## 起動方法

### 1. 依存関係のインストール

```bash
uv sync
```

### 2. PostgreSQL を用意（ローカル例）

```bash
docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
```

### 3. サーバーを起動

```bash
# 既定以外の DB に繋ぐ場合は DATABASE_URL を設定
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
uvicorn api:app --reload
```

- REST API ドキュメント: http://localhost:8000/docs
- MCP エンドポイント: http://localhost:8000/mcp

## エンドポイント一覧

| Method | Path | 説明 |
| ------ | ---- | ---- |
| GET    | `/health` | ヘルスチェック |
| GET    | `/version` | API のバージョン情報を取得 |
| GET    | `/notes` | ノートの一覧を取得 |
| GET    | `/notes/count` | ノートの件数を取得 |
| GET    | `/notes/tags` | タグ一覧を取得 |
| POST   | `/notes` | ノートを作成 |
| DELETE | `/notes` | すべてのノートを削除（0件のときは 204） |
| GET    | `/notes/{note_id}` | ノートを ID で取得 |
| PUT    | `/notes/{note_id}` | ノートを更新 |
| DELETE | `/notes/{note_id}` | ノートを削除 |
| GET    | `/stream` | ログストリーミング検証用 |

## MCP ツール一覧

| ツール名 | 説明 |
| -------- | ---- |
| `list_notes` | すべてのノートの一覧を取得 |
| `count_notes` | ノートの件数を取得 |
| `list_tags` | タグ一覧を取得 |
| `get_note` | ID を指定してノートを取得 |
| `create_note` | 新しいノートを作成 |
| `update_note` | ノートのタイトル/本文/タグを更新 |
| `delete_note` | ノートを ID で削除 |
| `delete_all_notes` | すべてのノートを一括削除 |

## curl での動作確認

```bash
# ノート作成
curl -s -X POST http://localhost:8000/notes \
  -H 'Content-Type: application/json' \
  -d '{"title": "memo", "content": "hello", "tags": ["a"]}'

# 一覧取得
curl -s http://localhost:8000/notes

# 件数取得
curl -s http://localhost:8000/notes/count

# 永続化の確認: サーバーを再起動してもノートが残る
```

## MCP クライアントからの接続

`supergateway` 経由で Streamable HTTP に接続する場合（lnar ダッシュボードで表示される設定）:

```json
{
  "mcpServers": {
    "test-lnar-hosting-python-postgres": {
      "command": "npx",
      "args": ["-y", "supergateway", "--streamableHttp", "http://localhost:8000/mcp"]
    }
  }
}
```

stdio transport（Claude Desktop / MCP Inspector 直接接続）を使う場合:

```bash
python mcp_server.py
```
