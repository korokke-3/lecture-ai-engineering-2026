"""宿題（発展）: 改良版Graph検索のテスト。質問の埋め込みは索引のページ埋め込みで代用し、APIを呼ばない。"""

import json

from app import tools
from app.config import GRAPH_PLUS_MAX_RESULTS
from app.graph_plus import load_graph, load_page_vectors, query_terms, search_graph_plus


def test_cites_links_explicit_cross_lecture_references():
    cites = load_graph()["cites"]
    # 第2回 p.50「第1回の『モデル・手法の大別』の具体版」
    assert "lec01-main-p048" in cites["lec02-main-p050"]
    # 第3回 p.19「第1回 9ページと同じ」
    assert "lec01-main-p009" in cites["lec03-main-p019"]
    # 関係は両向きに使う
    assert "lec02-main-p050" in cites["lec01-main-p048"]


def test_query_terms_do_not_match_inside_longer_names():
    terms = load_graph()["terms"]
    assert query_terms("QLoRAとは？", terms) == ["term:qlora"]
    assert query_terms("LoRAとQLoRAの違い", terms) == ["term:lora", "term:qlora"]


def test_query_terms_handle_keyword_style_queries():
    # エージェントが実際に送った検索語。空白を消すと「fine-tuningrag」になり、以前は用語を取りこぼした
    terms = load_graph()["terms"]
    found = query_terms("第1回 第2回 Fine-Tuning RAG 最新の講義内容 どちら", terms)
    assert {"term:fine-tuning", "term:rag"} <= set(found)


def test_results_are_limited_unique_and_cover_asked_terms():
    vector = list(load_page_vectors()["lec02-main-p052"])
    found = search_graph_plus("第2回のLoRAとQLoRA", query_vector=vector)
    ids = [result["page_id"] for result in found["results"]]
    assert ids[0] == "lec02-main-p052"
    assert len(ids) == len(set(ids)) <= GRAPH_PLUS_MAX_RESULTS
    assert all(result["reasons"] for result in found["results"])
    assert found["query_terms"] == ["LoRA", "QLoRA"]


def test_cross_lecture_question_reaches_cited_page():
    # 第2回 p.50 に近い質問でも、本文で参照している第1回 p.48 まで届く
    vector = list(load_page_vectors()["lec02-main-p050"])
    found = search_graph_plus("第1回と第2回で、Fine-TuningとRAGはどう使い分ける？", query_vector=vector)
    ids = [result["page_id"] for result in found["results"]]
    assert "lec01-main-p048" in ids
    assert {1, 2} <= {result["lecture"] for result in found["results"]}


def test_tool_returns_error_as_json_for_empty_query():
    data = json.loads(tools.search_graph_plus(" "))
    assert data["results"] == [] and "空" in data["error"]
