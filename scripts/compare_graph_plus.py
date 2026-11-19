"""第5回 宿題（発展）: ベクトル検索・Graph・改良版Graphを、同じ質問で比べる。

1. 検索だけの比較: 質問ごとに埋め込みを1回だけ作り、3方式が返すページと、
   先に決めた根拠ページをいくつ含むか、返す本文の文字数を記録する。
2. 回答の比較（--agent）: app.agent を各モードで --trace 付きで実行し、ログを保存する。

使い方:
    uv run python -m scripts.compare_graph_plus            # 検索だけ（埋め込みAPIを質問数ぶん呼ぶ）
    uv run python -m scripts.compare_graph_plus --agent    # 回答まで（生成APIも呼ぶ）
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from app import graph_plus, retrieval

OUT = Path(__file__).resolve().parent.parent / "lectures/05/homework_logs"

QUESTIONS = [
    {"id": "q1_single", "kind": "単一ページ",
     "text": "第2回の説明では、LoRAは何を固定し何を学習しますか？ QLoRAは何を加えますか？",
     "evidence": ["lec02-main-p052"]},
    {"id": "q2_ft_vs_rag", "kind": "回またぎ（手法の比較）",
     "text": "講義チャットボットに最新の講義内容を答えさせたい。Fine-TuningとRAGのどちらを先に試すべきか、"
             "第1回と第2回の説明をもとに、理由と判断の順番を答えてください。",
     "evidence": ["lec01-main-p048", "lec02-main-p046", "lec02-main-p047", "lec02-main-p050"]},
    {"id": "q3_long_context", "kind": "回またぎ（性質と設計の対応）",
     "text": "第2回で説明された「長い文脈を均等には使えない」という性質に対して、"
             "第3回ではエージェントのどの仕組みで対処していますか？",
     "evidence": ["lec02-main-p015", "lec03-main-p003", "lec03-main-p013"]},
    {"id": "q4_memory", "kind": "複数ページ（同じ回）",
     "text": "コンパクションとセッションをまたぐメモリの違いは？日々のメモは全部長期メモリになる？",
     "evidence": ["lec03-main-p013", "lec03-main-p039", "lec03-main-p040"]},
    {"id": "q5_not_in_materials", "kind": "資料にない",
     "text": "今回作ったRAGの実測平均応答時間と正答率は？",
     "evidence": []},
    # 以下の2問は、改良版の規則を決めた後に追加した確認用（規則の調整には使っていない）
    {"id": "q6_rsi_holdout", "kind": "回またぎ（確認用）",
     "text": "第3回で扱ったRSIは、第1回ではどのように説明されていましたか？第3回での位置づけとあわせて答えてください。",
     "evidence": ["lec01-main-p010", "lec03-main-p055"]},
    {"id": "q7_cutoff_holdout", "kind": "回またぎ（確認用）",
     "text": "第2回の「知識には締め切りがある」という性質に、第3回のエージェントではどう対処すると説明されていますか？",
     "evidence": ["lec02-main-p022", "lec03-main-p003"]},
]
MODES = {"vector": [], "graph": ["--graph"], "graph_plus": ["--graph-plus"]}


def compare_retrieval() -> list[dict]:
    """埋め込みを質問ごとに1回だけ作り、3方式の検索結果を並べる。"""
    rows = []
    original_embed = retrieval.embed_text
    for question in QUESTIONS:
        vector = original_embed(question["text"], "RETRIEVAL_QUERY")
        retrieval.embed_text = lambda text, task_type, v=vector: v  # search と search_graph に同じ埋め込みを使わせる
        try:
            vector_pages = retrieval.search(question["text"])
            graph = retrieval.search_graph(question["text"])
            graph_pages = graph["seeds"] + graph["expanded"]
            plus_pages = graph_plus.search_graph_plus(question["text"], query_vector=vector)["results"]
        finally:
            retrieval.embed_text = original_embed
        for mode, pages in (("vector", vector_pages), ("graph", graph_pages), ("graph_plus", plus_pages)):
            ids = [page["page_id"] for page in pages]
            hit = [page_id for page_id in question["evidence"] if page_id in ids]
            rows.append({"question": question["id"], "mode": mode, "pages": ids,
                         "evidence_hit": f"{len(hit)}/{len(question['evidence'])}",
                         "missing": [p for p in question["evidence"] if p not in ids],
                         "chars": sum(len(page["content"]) for page in pages)})
        time.sleep(1)
    return rows


def run_agent(question: dict, mode: str, attempt: int = 0) -> dict:
    command = [sys.executable, "-X", "utf8", "-m", "app.agent", *MODES[mode], "--trace", question["text"]]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    log = completed.stdout + completed.stderr
    if ("レート制限" in log or "混み合" in log) and attempt < 3:
        time.sleep(60)
        return run_agent(question, mode, attempt + 1)
    (OUT / f"{question['id']}__{mode}.log").write_text(log, encoding="utf-8")
    numbers = lambda pattern: [float(x.replace(",", "")) for x in re.findall(pattern, log)]
    usage = numbers(r"入力 ([\d,]+) tokens") + numbers(r"出力 ([\d,]+) tokens")
    return {"question": question["id"], "mode": mode,
            "time": (numbers(r"\[time\] 回答完了まで ([\d.]+)") or [None])[0],
            "input_tokens": usage[0] if usage else None, "output_tokens": usage[1] if usage else None,
            "requests": (numbers(r"モデル応答 (\d+) 回") or [None])[0],
            "cost": (numbers(r"\$([\d.]+) USD") or [None])[0],
            "cited": sorted(set(re.findall(r"第\s*\d\s*回[・･\s]*(?:PDF\s*)?p\.\s*\d+", log.split("--- trace ---")[0])))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", action="store_true", help="回答まで実行する（生成APIを呼ぶ）")
    parser.add_argument("--modes", nargs="+", choices=list(MODES), default=list(MODES),
                        help="回答まで実行する方式（既定はすべて。結果は agent.json に方式ごとに上書きする）")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    rows = compare_retrieval()
    (OUT / "retrieval.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for row in rows:
        print(f"{row['question']:22} {row['mode']:10} 根拠 {row['evidence_hit']:4} 本文 {row['chars']:6,}字"
              f"  不足 {row['missing']}")

    if args.agent:
        path = OUT / "agent.json"
        kept = [r for r in json.loads(path.read_text(encoding="utf-8")) if r["mode"] not in args.modes] \
            if path.exists() else []
        results = []
        for question in QUESTIONS:
            for mode in args.modes:
                results.append(run_agent(question, mode))
                print(results[-1])
                time.sleep(5)
        order = {q["id"]: i for i, q in enumerate(QUESTIONS)}
        merged = sorted(kept + results, key=lambda r: (order[r["question"]], list(MODES).index(r["mode"])))
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
