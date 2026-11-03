# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：
- `--trace` で見えたツール呼び出し（ツール名と引数）：
- 1つの質問での LLM 呼び出し回数（`requests`）：
- 追加したツールと、docstring に書いた説明：

## 宿題

- 取り組んだレベル：発展（a）ADK で作り直す
- やったこと：
  - `adk_agent/glossary_agent/` に `agent.py` と `__init__.py` を作り、`app/agent.py` の `INSTRUCTIONS` と `app/tools.py` の `search_glossary`・`get_lecture_summary` をそのまま渡した（`app/` は変更なし）
  - 実装と実行、比較の記入には AI ツール（Claude Code）を使った
  - `adk run` が作る `.adk/session.db` がコミットされないよう、`.gitignore` に `.adk/` を足した
- 結果：

  書き方の比較（google-adk 2.13.0 / pydantic-ai-slim 2.57.0）

  | 観点 | Pydantic AI（`app/agent.py`） | ADK（`adk_agent/glossary_agent/agent.py`） |
  |---|---|---|
  | 指示 | `Agent(instructions=INSTRUCTIONS)` | `Agent(instruction=INSTRUCTIONS)` |
  | ツール | 作成後に `agent.tool_plain(関数)` で1つずつ登録 | 作成時に `tools=[関数, …]` で渡す |
  | モデル | 実行時に `run_sync(..., model=build_model())` で渡す | 作成時に `model="…"` で渡す |
  | 名前 | 不要 | `name` が必須 |
  | API キー | `get_api_key()` で読み、明示的に渡す | 環境変数 `GEMINI_API_KEY` を SDK が読む |
  | 動かし方 | `main()` などを自分で書く | `root_agent` を定義すれば `adk run` が対話画面を用意する |
  | 会話の保存 | 実行ごとに終わる | `.adk/session.db` に保存される |

  モデルに渡る内容の比較（API を使わず確認）

  - 指示：`INSTRUCTIONS` はそのまま渡るが、ADK では末尾に `You are an agent. Your internal name is "glossary_agent".` が足される
  - ツールの説明文：2つとも docstring がそのまま渡り、引数の型も同じ（`query` は string、`lecture` は integer）
  - ツールの返り値：Pydantic AI は文字列のまま、ADK は `{"result": "…"}` に包んで返す
  - ループ：決まった応答を返す偽モデルで、ツールの依頼 → 実行 → 結果を受けて回答、の順に動くことを確認した（回数は偽モデルの筋書きどおりなので、実際のモデルのふるまいの確認ではない）

  同じ質問への回答の比較（Codespaces で `gemini-3.5-flash-lite` を使い、各1回実行。ADK 版のツール呼び出しとトークン数は `.adk/session.db` から読んだ）

  | 質問 | 項目 | Pydantic AI 版 | ADK 版 |
  |---|---|---|---|
  | AIE2026の講座の宿題にある「3レベル」とは何ですか？ | ツール呼び出し | `search_glossary({'query': '3レベル'})` | 同じ |
  | | LLM 呼び出し | 2回（`requests=2`） | 2回（`usage_metadata` のある応答が2つ） |
  | | 入力 / 出力トークン | 783 / 151 | 879 / 147 |
  | | 回答 | 基礎・実装・発展の3段階、どれか1つで完了、原則採点なし。最後は「第1回（関係する回：第1回）」 | 内容は同じ。最後は「関係する回：第1回」 |
  | LoRAとQLoRAの違いは？ | ツール呼び出し | `search_glossary` を `LoRA`・`QLoRA` で1回ずつ | 同じ |
  | | LLM 呼び出し | 2回（`requests=2`） | 2回（`usage_metadata` のある応答が2つ） |
  | | 入力 / 出力トークン | 1196 / 179 | 1290 / 174 |
  | | 回答 | 2つの手法を順に説明。最後は「関係する回：第2回」 | 最初に「主な違いは量子化するかどうか」とまとめてから説明。最後は「関係する回：第2回」 |

  - 2問とも、どちらの版の回答も `data/glossary.json` の定義と矛盾しなかった（「3レベル」は `homework-levels` の定義全文と、LoRA・QLoRA は `--trace` に出た定義の冒頭と照合した）
  - `uv run pytest -q` は Codespaces で 11 passed だった

- 気づき・疑問：
  - 指示とツールの関数は1文字も変えずに再利用できた。docstring と型ヒントからツールの説明を作る点は、どちらのフレームワークも同じだった
  - Pydantic AI は実行時にモデルを渡すので、テストで `TestModel` に差し替えやすい。ADK は `adk run` だけで動くが、`adk run --help` に `--trace` にあたるオプションはなく、あるのはログ表示の `--verbose` や `--log_level` だった
  - `adk run` は質問文を含む履歴を `adk_agent/glossary_agent/.adk/session.db` に保存する。この repo の手順の `git add -A` だと、そのままではコミットされてしまう
  - ADK の `instruction` では `{foo}` がセッションの変数として扱われ、該当する変数がないと `KeyError` になる。今の `INSTRUCTIONS` に `{}` はないので問題ないが、指示に波かっこを書くときは注意が必要
  - ツールの選び方、引数、LLM の呼び出し回数は、2問とも両方の版で同じだった。同じ指示と docstring を渡しているので、フレームワークを変えてもふるまいの大筋は変わらないと感じた
  - 回答の中身は同じでも、文の組み立ては違った。ただし各1回の実行なので、これがフレームワークの違いなのか、実行ごとのばらつきなのかは区別できない
  - Pydantic AI 版の QLoRA の説明には「メモリ消費を極限まで抑えた」とあり、用語集の「メモリを節約」より強い表現になっていた。検索して答えても、言い回しまで定義どおりになるとは限らない
  - 入力トークンは ADK 版のほうが96トークンと94トークン多かった。追加される1行や返り値の包み方が関係していそうだが、原因は確かめていない
  - 疑問：回答の違いがばらつきの範囲かどうかは、同じ質問を何回も実行して比べないと言えない。どのくらいの回数を比べれば十分なのか
