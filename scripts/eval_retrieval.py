"""第2回 宿題（発展）: 用語集を検索する仕組み（第3回の search_glossary）を、同じ評価質問で採点する。

使い方（講座 repo のルートで。GPU も API キーも不要）:
    uv run python scripts/eval_retrieval.py

見るもの:
- exact / paraphrase: 検索語で正しい用語が 1 位・3 位以内に出たか（出れば、答えの根拠を渡せる）
- unknown: 「見つかりませんでした」になったか（何か返すと、無い語に別の用語を当てる誤ヒット）
あわせて、評価データの検査（学習データとの重なり、正解語句が用語集の本文にあるか）も行う。
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.tools import load_glossary, search_glossary  # noqa: E402

EVAL = ROOT / "data" / "glossary_eval.json"


def check_data(items, glossary):
    """評価データが学習データと重ならず、正解が用語集から導けることを確かめる"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mk", ROOT / "scripts" / "make_sft_dataset.py")
    mk = importlib.util.module_from_spec(spec); spec.loader.exec_module(mk)
    train_questions = {r["messages"][0]["content"] for r in mk.records(plus=True)}
    by_id = {t["id"]: t for t in glossary}
    names = {n.casefold() for t in glossary for n in [t["term"], t["id"], *t["aliases"]]}
    for it in items:
        assert it["question"] not in train_questions, f"学習データと同じ質問: {it['id']}"
        if it["category"] == "unknown":
            q = it["query"].casefold()
            assert q not in names, f"用語集にある語を unknown にしている: {it['id']}"
            assert it["query"] not in mk.UNKNOWN_TERMS, f"学習用の『無い語』と重複: {it['id']}"
        else:
            t = by_id[it["term_id"]]
            text = t["term"] + t["definition"]
            for group in it["must_include"]:
                assert any(w in text for w in group), f"正解語句が用語集に無い: {it['id']} {group}"
    print(f"データ検査 OK: {len(items)} 問、学習データ（--plus 含む）との重複なし\n")


def main() -> None:
    data = json.loads(EVAL.read_text(encoding="utf-8"))
    items = data["items"]
    glossary = load_glossary()
    check_data(items, glossary)
    term_to_id = {t["term"]: t["id"] for t in glossary}

    rows = []
    for it in items:
        res = search_glossary(it["query"])
        hits = [term_to_id[h["term"]] for h in json.loads(res)] if res.startswith("[") else []
        if it["category"] == "unknown":
            ok1 = ok3 = not hits
        else:
            ok1 = hits[:1] == [it["term_id"]]
            ok3 = it["term_id"] in hits
        rows.append({**it, "hits": hits, "top1": ok1, "top3": ok3})

    print("| id | 区分 | 検索語 | 検索結果（id） | 1位 | 3位内 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['id']} | {r['category']} | {r['query']} | {', '.join(r['hits']) or '（見つからない）'} | "
              f"{'○' if r['top1'] else '×'} | {'○' if r['top3'] else '×'} |")
    print()
    summary = {}
    for cat in ["exact", "paraphrase", "unknown"]:
        rs = [r for r in rows if r["category"] == cat]
        summary[cat] = {"n": len(rs), "top1": sum(r["top1"] for r in rs) / len(rs), "top3": sum(r["top3"] for r in rs) / len(rs)}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    (ROOT / "retrieval_result.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
