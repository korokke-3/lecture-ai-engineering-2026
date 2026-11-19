"""第5回 宿題（発展）: 質問の用語と回またぎ参照で広げ、類似度で絞る Graph 検索。

既存の search_graph との違い:
- 入口: ベクトル検索の上位ページに加え、質問に出てくる用語ノードと、
  質問が指定した回の中で類似度が最上位のページも入口にする。
- 関係: next_page・mentions に加え、未使用だった related_term と、本文中の
  「第N回の『…』」から作る cites（回をまたぐ明示的な参照）を使う。
- 用語経由の展開は、質問の用語とその related_term に限る。LLM・RAG のように
  多くのページに出る一般的な用語をたどって無関係なページが増えるのを防ぐ。
- 候補の順位: hop 数ではなく、索引にあるページ埋め込みと質問の類似度で決める。
  ページ側の埋め込みは DB から読むので、追加の埋め込み API 呼び出しはない。
- 選び方: 質問の用語と、質問で指定された回を少なくとも1ページずつ含むように選び、
  返すページ数を GRAPH_PLUS_MAX_RESULTS に抑える。

使い方（検索だけを試す）:
    uv run python -m app.graph_plus "LoRAとRAGの使い分けは？"
"""

import argparse
import json
import re
import struct
from collections import defaultdict
from functools import cache

from app.config import (
    GRAPH_PLUS_MAX_RESULTS, GRAPH_PLUS_MIN_SIMILARITY, GRAPH_START_K, RAG_DB, RAG_GRAPH,
)
from app.retrieval import embed_text, load_pages, open_index

TERM_BONUS = 0.02      # 質問の用語1つを含むごとに加える点
LECTURE_BONUS = 0.02   # 質問で指定された回のページに加える点
CITE_BONUS = 0.03      # 回またぎの明示的な参照でつながったページに加える点
DUPLICATE_SIMILARITY = 0.97  # これ以上似たページは、内容が重複するとみなして片方だけ返す


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()


def lectures_in(text: str) -> set[int]:
    """「第2回」「第 2 回」のような回の指定を取り出す。"""
    return {int(n) for n in re.findall(r"第\s*([0-9０-９]+)\s*回", text)}


@cache
def load_graph() -> dict:
    """ページ・用語・関係を読み、検索に使う形にまとめる（初回だけ読み込む）。"""
    pages = {page["page_id"]: page for page in load_pages()}
    graph = json.loads(RAG_GRAPH.read_text(encoding="utf-8"))
    terms = {node["id"]: node for node in graph["nodes"] if node["kind"] == "term"}
    next_page, mentions, mentioned_by, related = (defaultdict(set) for _ in range(4))
    for edge in graph["edges"]:
        a, b, relation = edge["source"], edge["target"], edge["relation"]
        if relation == "next_page" and a in pages and b in pages:
            next_page[a].add(b)
            next_page[b].add(a)
        elif relation == "mentions" and a in pages and b in terms:
            mentions[a].add(b)
            mentioned_by[b].add(a)
        elif relation == "related_term" and a in terms and b in terms:
            related[a].add(b)
            related[b].add(a)
    return {"pages": pages, "terms": terms, "next_page": next_page, "mentions": mentions,
            "mentioned_by": mentioned_by, "related": related, "cites": build_cites(pages)}


def build_cites(pages: dict) -> dict:
    """本文中の回をまたぐ参照を、参照元⇔参照先ページの関係にする。

    対応する書き方:
    - 第1回の「モデル・手法の大別」   → 第1回でタイトルにその語句を含むページ
    - 第1回 9ページと同じ             → 第1回の PDF p.9
    - 第1回で見た RSI を…             → 第1回でタイトルに RSI を含むページ（最も前のもの）
    回の名前そのもの（第2回「基盤モデルの仕組み」）は表紙を指すだけなので使わない。
    """
    by_lecture = defaultdict(list)
    for page in pages.values():
        by_lecture[page["lecture"]].append(page)
    for lecture_pages in by_lecture.values():
        lecture_pages.sort(key=lambda page: page["page"])
    document_titles = {normalize(page["document_title"]) for page in pages.values()}

    cites = defaultdict(set)
    pattern = re.compile(
        r"第\s*([1-9])\s*回\s*(?:の\s*)?(?:「([^」]+)」|([0-9]+)\s*ページ|で見た\s*([A-Za-z0-9]+))"
    )
    for page in pages.values():
        for match in pattern.finditer(page["content"]):
            lecture = int(match.group(1))
            if lecture == page["lecture"] or lecture not in by_lecture:
                continue
            quoted, page_number, word = match.group(2), match.group(3), match.group(4)
            if page_number:
                targets = [p for p in by_lecture[lecture] if p["page"] == int(page_number)]
            else:
                phrase = normalize(quoted or word)
                if phrase in document_titles:
                    continue
                targets = [p for p in by_lecture[lecture] if phrase in normalize(p["title"])][:1]
            for target in targets:
                cites[page["page_id"]].add(target["page_id"])
                cites[target["page_id"]].add(page["page_id"])
    return cites


@cache
def load_page_vectors() -> dict[str, tuple[float, ...]]:
    """索引DBから、ページごとの埋め込み（長さ1に正規化済み）を読む。"""
    with open_index(RAG_DB) as db:
        rows = db.execute("SELECT page_id, embedding FROM chunks").fetchall()
    return {row["page_id"]: struct.unpack(f"{len(row['embedding']) // 4}f", row["embedding"])
            for row in rows}


def dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def query_terms(query: str, terms: dict) -> list[str]:
    """質問文に名前か別名が出てくる用語ノードを返す。長い名前を優先し、短い別名の誤一致を避ける。"""
    # 空白を消した形と残した形の両方で探す。エージェントは「Fine-Tuning RAG」のように
    # 語を空白で並べて検索するので、空白を消すだけだと「fine-tuningrag」になり境界の判定で落ちる。
    texts = (normalize(query), re.sub(r"\s+", " ", query).casefold())
    found = []
    for term_id, term in terms.items():
        names = {normalize(term["title"]), *(normalize(alias) for alias in term.get("aliases", []))}
        names = {name for name in names if len(name) >= 2}
        # 「LoRA」が「QLoRA」の一部として当たらないよう、英数字の直前直後が英数字でないことを確かめる
        if any(re.search(rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", text)
               for name in names for text in texts):
            found.append(term_id)
    return sorted(found)


def search_graph_plus(query: str, query_vector: list[float] | None = None) -> dict:
    """質問の用語・回またぎ参照で候補を広げ、類似度と網羅性で選んだページを返す。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("検索語が空です。")
    g = load_graph()
    pages, vectors = g["pages"], load_page_vectors()
    vector = query_vector or embed_text(query.strip(), "RETRIEVAL_QUERY")
    similarity = {page_id: dot(vector, vectors[page_id]) for page_id in pages if page_id in vectors}

    asked_terms = query_terms(query, g["terms"])
    asked_lectures = lectures_in(query) & {page["lecture"] for page in pages.values()}
    # 用語経由で広げてよいのは、質問の用語と、それに related_term でつながる用語だけ
    expand_terms = set(asked_terms) | {t for term in asked_terms for t in g["related"][term]}

    # 1. 入口: 類似度上位のページと、質問の用語を含むページ
    ranked = sorted(similarity, key=lambda page_id: (-similarity[page_id], page_id))
    reasons: dict[str, list[str]] = defaultdict(list)
    for page_id in ranked[:GRAPH_START_K]:
        reasons[page_id].append("seed: ベクトル検索の上位")
    for term in asked_terms:
        for page_id in g["mentioned_by"][term]:
            reasons[page_id].append(f"term: 質問の用語「{g['terms'][term]['title']}」を含む")
    # 質問が「第N回」を指定していれば、その回の中だけで類似度が最上位のページも入口にする（Treeで回を選ぶのと同じ発想）
    for lecture in sorted(asked_lectures):
        best = next(page_id for page_id in ranked if pages[page_id]["lecture"] == lecture)
        reasons[best].append(f"lecture: 第{lecture}回の中で類似度が最上位")

    # 2. 展開: 入口から前後ページ・回またぎ参照・（限定した）用語を1段たどる
    entries = list(reasons)
    for page_id in entries:
        title = pages[page_id]["title"]
        for neighbor in g["next_page"][page_id]:
            reasons[neighbor].append(f"next_page: {page_id}（{title}）の前後")
        for neighbor in g["cites"][page_id]:
            reasons[neighbor].append(f"cites: {page_id}（{title}）と回をまたいで参照")
        for term in g["mentions"][page_id] & expand_terms - set(asked_terms):
            for neighbor in g["mentioned_by"][term]:
                reasons[neighbor].append(f"related_term: 関連用語「{g['terms'][term]['title']}」")

    # 3. 採点: 類似度に、質問の用語・指定された回・回またぎ参照の分を加える
    def score(page_id: str) -> float:
        page = pages[page_id]
        bonus = TERM_BONUS * len(g["mentions"][page_id] & set(asked_terms))
        bonus += LECTURE_BONUS * (page["lecture"] in asked_lectures)
        bonus += CITE_BONUS * any(r.startswith("cites") for r in reasons[page_id])
        return similarity.get(page_id, 0.0) + bonus

    candidates = sorted((page_id for page_id in reasons if page_id in similarity),
                        key=lambda page_id: (-score(page_id), page_id))

    # 4. 選択: まず最上位を取り、未カバーの用語・回を埋めるページを優先し、残りを点数順に足す
    chosen: list[str] = []

    def add(page_id: str) -> None:
        if page_id in chosen or len(chosen) >= GRAPH_PLUS_MAX_RESULTS:
            return
        if similarity[page_id] < GRAPH_PLUS_MIN_SIMILARITY:
            return
        if any(dot(vectors[page_id], vectors[other]) >= DUPLICATE_SIMILARITY for other in chosen):
            return
        chosen.append(page_id)

    if candidates:
        add(candidates[0])
    for term in asked_terms:
        if not any(term in g["mentions"][page_id] for page_id in chosen):
            for page_id in candidates:
                if term in g["mentions"][page_id]:
                    add(page_id)
                    break
    # 指定された回は、用語の加点に左右されないように補う。選んだページが本文で参照している
    # その回のページ（cites）があれば優先し、なければその回の中での類似度最上位を使う。
    for lecture in sorted(asked_lectures):
        if not any(pages[page_id]["lecture"] == lecture for page_id in chosen):
            cited = [p for c in chosen for p in sorted(g["cites"][c]) if pages[p]["lecture"] == lecture]
            add(cited[0] if cited else next(p for p in ranked if pages[p]["lecture"] == lecture))
    for page_id in candidates:
        add(page_id)

    results = [{**pages[page_id], "similarity": round(similarity[page_id], 4),
                "score": round(score(page_id), 4), "reasons": reasons[page_id][:3]}
               for page_id in sorted(chosen, key=lambda page_id: -score(page_id))]
    return {"query_terms": [g["terms"][t]["title"] for t in asked_terms],
            "query_lectures": sorted(asked_lectures), "candidates": len(candidates),
            "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="改良版Graph検索だけを実行する")
    parser.add_argument("query", help="調べたい内容")
    args = parser.parse_args()
    found = search_graph_plus(args.query)
    print(f"質問の用語: {found['query_terms']} / 指定された回: {found['query_lectures']}"
          f" / 候補 {found['candidates']} ページ")
    for result in found["results"]:
        print(f"\n- 第{result['lecture']}回 PDF p.{result['page']} {result['title']}"
              f"（類似度 {result['similarity']}, 点 {result['score']}）")
        for reason in result["reasons"]:
            print(f"    {reason}")
