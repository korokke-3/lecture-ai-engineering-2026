# 第6回 解答

## 演習

<!-- [tool call] の行は、表示された行をそのまま貼り付けてください。終わらなかった STEP は、空欄のままでかまいません。 -->

- STEP 1 のツールの名前：
- STEP 2 の [tool call]：
- STEP 3 の [tool call]：
- STEP 4 の [tool call]：
- 気づき・疑問：

## 宿題

<!-- 基礎・実装・発展のどれか1つに取り組めば完了です。 -->

- 取り組んだレベル：発展
- やったこと：
  - 普段使っている Claude Code を選び、MCP サーバーの設定方法を公式ドキュメントで調べた。調べた日は 2026-11-24、参照したのは https://code.claude.com/docs/en/mcp である。
  - 調べた内容を `app/mcp_servers.json` と比べた。さらに、演習の glossary サーバーと AWS Knowledge サーバーを Claude Code 2.1.330 に実際に登録し、つながるかを確かめた。
- 結果：

  | 調べること | Claude Code | 演習の `app/mcp_servers.json` |
  |---|---|---|
  | 設定を書く場所 | `claude mcp add` コマンドで登録するのが基本である。保存先はスコープで決まり、project スコープならプロジェクト直下の `.mcp.json`、local と user スコープならホームの `~/.claude.json` に書かれる | `app/mcp_servers.json` に手で書き、`app/mcp_agent.py` が読む |
  | コマンドで起動する書き方 | `claude mcp add glossary -- uv run python -m app.mcp_server` のように、`--` のあとに起動コマンドを並べる。`.mcp.json` には `"type": "stdio"` と `"command"`、`"args"`、`"env"` が書かれる | `"command": "uv"` と `"args"` を書く。`"type"` はない |
  | URL で接続する書き方 | `claude mcp add --transport http aws https://knowledge-mcp.global.api.aws` と書く。`.mcp.json` では `"type": "http"` と `"url"` の組になり、認証が要るときは `"headers"` も書ける | `"url"` だけを書く |
  | 有効になる範囲 | local がそのプロジェクトで自分だけ、project が `.mcp.json` を git で共有してそのプロジェクトの全員、user が自分のすべてのプロジェクトである。既定は local である。同じ名前があれば local、project、user の順に優先される | このリポジトリの `mcp_agent.py` を動かしたときだけ |

  - 外側の形は同じである。どちらも `"mcpServers"` の下にサーバー名をキーとして並べ、`command`・`args`・`env`・`url` という同じ名前の項目を使う。
  - 一番大きな違いは `"type"` の扱いである。演習の設定をそのまま `.mcp.json` に置いて `claude mcp list` を実行したところ、glossary は読み込まれたが、aws は `MCP server "aws" has a "url" but no "type"; add "type": "http"` という警告とともに読み飛ばされた。演習のエージェントは `url` があれば Streamable HTTP とみなすが、Claude Code は `type` を明示しないと `url` を使わない。
  - `claude mcp add --scope project` で 2 つを登録し直すと、`.mcp.json` に `"type": "stdio"` と `"type": "http"` が付いた。`claude -p` で「glossary のツールで LoRA を検索して」と頼むと、`mcp__glossary__search_glossary({'query': 'LoRA'})` が呼ばれ、用語集の定義をもとに答えた。aws も接続でき、`mcp__aws__aws___search_documentation` などのツールが増えた。
  - ツール名の付け方も違う。演習では `glossary_search_glossary` のようにサーバー名と `_` を前に付けるが、Claude Code では `mcp__glossary__search_glossary` のように `mcp__` とサーバー名と `__` を前に付ける。
  - project スコープのサーバーは、対話モードで最初に使うときに承認を求められる。`claude mcp list` でも、承認前は `Pending approval` と表示された。演習のエージェントは設定ファイルに書いたサーバーをすぐに起動する。
- 気づき・疑問：
  - 同じ `mcpServers` 形式でも、`type` を省略できるかどうかはクライアントごとに違う。演習の設定を他のツールに持っていくときは、`type` を足すのが安全だと分かった。
  - `.mcp.json` をリポジトリに入れると、clone した人の環境でコマンドが起動される。Claude Code が承認を求めるのはこのためだと考えられる。演習の `mcp_servers.json` にはこの確認がないので、他人のリポジトリの設定ファイルは中身を読んでから実行すべきである。
  - Claude Code では `${API_KEY}` のように環境変数を `.mcp.json` に埋め込める。キーをファイルに直接書かずに共有できる点は、演習の形式にない利点である。
  - Windows の長いパスの下で `uv sync` したところ、pydantic_core が壊れて glossary サーバーが起動しなかった。仮想環境を短いパスに置くよう `"env"` に `UV_PROJECT_ENVIRONMENT` を書いて解決した。`env` の使いどころを実際に確かめられた。
