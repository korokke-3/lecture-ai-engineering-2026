"""第1回 宿題（発展）: 応答時間とトークン数を計測し、モデルや質問で比較する。

使い方:
    uv run python -m app.bench                       # 既定のモデル・質問で計測
    uv run python -m app.bench --models gemini-3.5-flash-lite --repeat 3
    uv run python -m app.bench --burst 20            # 間隔を空けずに連続で呼び、レート制限（429）を観察する

結果は1回の呼び出しごとに CSV（results/bench_*.csv）へ書き、最後に集計表を表示する。
ストリーミングで呼び出し、最初のチャンクが届くまで（TTFT）と全体の時間を分けて測る。

無料枠の上限（講座の実測）:
    gemini-3.5-flash-lite  毎分 15、1 日 500 リクエスト
    gemini-3.8-flash       毎分 5、1 日 10〜20 前後（503 が返ることも）
上位モデルは 1 日の上限が小さいので、--repeat を増やしすぎないこと。
"""

import argparse
import csv
import statistics
import time
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import errors, types

from app.config import get_api_key

DEFAULT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

# 性質の違う3つの質問：短い一般用語 / 講座に固有 / 長い出力を求める
QUESTIONS = {
    "short": "LoRAとは何ですか？一文で答えてください。",
    "course": "AIE2026の講座の宿題にある「3レベル」とは何ですか？",
    "long": "Transformer の仕組みを、Attention・位置埋め込み・学習方法に分けて詳しく説明してください。",
}

# 1 分あたりの上限（講座の実測）。通常の計測ではこれを超えないよう間隔を空ける
RPM = {"gemini-3.5-flash-lite": 15, "gemini-3.8-flash": 5}

RESULTS_DIR = Path("results")


@dataclass
class Record:
    model: str
    question: str
    run: int
    status: str  # ok / エラーコード（429 など）
    ttft_s: float | None = None
    total_s: float | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thoughts_tokens: int | None = None
    total_tokens: int | None = None
    output_chars: int | None = None


def measure(client: genai.Client, model: str, qid: str, question: str, run: int) -> Record:
    """1 回呼び出し、TTFT・全体の時間・トークン数を記録する。"""
    rec = Record(model=model, question=qid, run=run, status="ok")
    start = time.perf_counter()
    text = []
    usage = None
    try:
        for chunk in client.models.generate_content_stream(model=model, contents=question):
            if rec.ttft_s is None:
                rec.ttft_s = time.perf_counter() - start
            if chunk.text:
                text.append(chunk.text)
            # usage_metadata は最後のチャンクで確定する
            if chunk.usage_metadata:
                usage = chunk.usage_metadata
    except errors.APIError as e:
        rec.status = str(e.code)
    except Exception as e:  # タイムアウトや接続断も1件の失敗として記録し、計測は続ける
        rec.status = type(e).__name__
    rec.total_s = time.perf_counter() - start
    if usage:
        rec.prompt_tokens = usage.prompt_token_count
        rec.output_tokens = usage.candidates_token_count
        rec.thoughts_tokens = usage.thoughts_token_count or 0
        rec.total_tokens = usage.total_token_count
    rec.output_chars = len("".join(text))
    return rec


def print_record(rec: Record) -> None:
    if rec.status != "ok":
        print(f"  {rec.model:24} {rec.question:6} #{rec.run}  ERROR {rec.status}  ({rec.total_s:.2f}s)")
        return
    tps = rec.output_tokens / rec.total_s if rec.output_tokens and rec.total_s else 0
    print(
        f"  {rec.model:24} {rec.question:6} #{rec.run}  "
        f"TTFT {rec.ttft_s:5.2f}s  全体 {rec.total_s:5.2f}s  "
        f"入力 {rec.prompt_tokens} / 出力 {rec.output_tokens} / 思考 {rec.thoughts_tokens}  "
        f"({tps:.0f} tok/s)"
    )


def summarize(records: list[Record]) -> None:
    """モデル×質問ごとの中央値を表（Markdown）で表示する。answer.md に貼れる形。"""
    print("\n| モデル | 質問 | 成功/試行 | TTFT 中央値(s) | 全体 中央値(s) | 入力 | 出力 中央値 | 思考 中央値 | 出力 tok/s |")
    print("|---|---|---|---|---|---|---|---|---|")
    keys = sorted({(r.model, r.question) for r in records}, key=lambda k: (k[0], list(QUESTIONS).index(k[1]) if k[1] in QUESTIONS else 99))
    for model, qid in keys:
        rs = [r for r in records if r.model == model and r.question == qid]
        ok = [r for r in rs if r.status == "ok"]
        if not ok:
            codes = ",".join(sorted({r.status for r in rs}))
            print(f"| {model} | {qid} | 0/{len(rs)} | - | - | - | - | - | - （{codes}） |")
            continue
        med = lambda xs: statistics.median(xs)  # noqa: E731
        tps = med([r.output_tokens / r.total_s for r in ok if r.output_tokens])
        print(
            f"| {model} | {qid} | {len(ok)}/{len(rs)} | {med([r.ttft_s for r in ok]):.2f} | "
            f"{med([r.total_s for r in ok]):.2f} | {ok[0].prompt_tokens} | "
            f"{med([r.output_tokens for r in ok]):.0f} | {med([r.thoughts_tokens for r in ok]):.0f} | {tps:.0f} |"
        )


def run_bench(client, models, qids, repeat, writer) -> list[Record]:
    records = []
    for model in models:
        # 毎分の上限を超えないよう、呼び出しの開始間隔を空ける（少し余裕を持たせる）
        interval = 60 / RPM.get(model, 5) * 1.1
        print(f"\n== {model}（間隔 {interval:.1f}s） ==")
        for run in range(1, repeat + 1):
            for qid in qids:
                t0 = time.perf_counter()
                rec = measure(client, model, qid, QUESTIONS[qid], run)
                print_record(rec)
                writer.writerow(asdict(rec))
                records.append(rec)
                time.sleep(max(0, interval - (time.perf_counter() - t0)))
    return records


def run_burst(client, model, n, writer) -> list[Record]:
    """間隔を空けずに n 回呼び、何回目から 429 になるかを見る。"""
    print(f"\n== burst: {model} を {n} 回連続 ==")
    records = []
    start = time.perf_counter()
    for i in range(1, n + 1):
        rec = measure(client, model, "short", QUESTIONS["short"], i)
        elapsed = time.perf_counter() - start
        print(f"  [{elapsed:5.1f}s]", end="")
        print_record(rec)
        writer.writerow(asdict(rec))
        records.append(rec)
    first_429 = next((r.run for r in records if r.status == "429"), None)
    ok = sum(r.status == "ok" for r in records)
    print(f"\n  成功 {ok}/{n}、最初の 429: {first_429 or 'なし'}（{time.perf_counter() - start:.1f}s 内）")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="応答時間とトークン数を計測する")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--questions", nargs="+", default=list(QUESTIONS), choices=list(QUESTIONS))
    parser.add_argument("--repeat", type=int, default=2, help="質問ごとの繰り返し回数")
    parser.add_argument("--burst", type=int, default=0, help="指定すると、最初のモデルで連続呼び出しのみ行う")
    args = parser.parse_args()

    # ストリームが止まったときに計測全体が止まらないよう、1 回あたり 60 秒で打ち切る
    client = genai.Client(api_key=get_api_key(), http_options=types.HttpOptions(timeout=60_000))
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"bench_{'burst_' if args.burst else ''}{datetime.now():%Y%m%d_%H%M%S}.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[fl.name for fl in fields(Record)])
        writer.writeheader()
        if args.burst:
            records = run_burst(client, args.models[0], args.burst, writer)
        else:
            records = run_bench(client, args.models, args.questions, args.repeat, writer)
    summarize(records)
    print(f"\n結果: {path}")


if __name__ == "__main__":
    main()
