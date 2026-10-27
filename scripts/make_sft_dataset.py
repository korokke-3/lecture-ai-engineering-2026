"""第2回 宿題（発展）: 用語集から SFT 用の Q&A データ（JSONL）を作る。

使い方:
    uv run python scripts/make_sft_dataset.py > glossary_sft.jsonl              # 元のまま（2 テンプレート × 58 語）
    uv run python scripts/make_sft_dataset.py --plus > glossary_sft_plus.jsonl  # 工夫版

できたファイルを Colab にアップロードし、LoRA 学習のデータとして使う。

--plus で足す工夫:
- 質問テンプレートを 2 つ追加する（言い回しへの汎化を少し助ける）
- 用語集に無い語を聞かれたら「用語集に載っていません」と答える例を足す
  （第2回演習の needs_review=true と同じ考え方。元のデータには「知らない」と答える例が 1 件も無い）

評価用の質問（data/glossary_eval.json）の言い回しと「無い語」は、ここで使うものと重ならないようにしてある。
別名（aliases）は学習に入れず、言い換えへの汎化を評価で見る。
"""

import argparse
import json
import sys
from pathlib import Path

GLOSSARY = Path(__file__).resolve().parent.parent / "data" / "glossary.json"
TEMPLATES = ["「{term}」とは何ですか？", "{term}について簡単に説明してください。"]
EXTRA_TEMPLATES = ["{term}の意味を教えてください。", "{term}って何のこと？"]

# 用語集に無い語（学習用）。評価用の「無い語」とは重ならないようにする
UNKNOWN_TERMS = [
    "Kubernetes", "CI/CD", "勾配ブースティング", "畳み込みニューラルネットワーク",
    "GAN", "ベイズ最適化", "データドリフト", "A/Bテスト",
    "正規表現", "WebSocket", "ONNX", "知識グラフ",
]
UNKNOWN_ANSWER = "「{term}」は講座の用語集に載っていません。用語集の範囲外なので、講義資料や講師に確認してください。"


def records(plus: bool):
    terms = json.loads(GLOSSARY.read_text(encoding="utf-8"))["terms"]
    templates = TEMPLATES + (EXTRA_TEMPLATES if plus else [])
    for t in terms:
        for template in templates:
            yield {
                "messages": [
                    {"role": "user", "content": template.format(term=t["term"])},
                    {"role": "assistant", "content": t["definition"]},
                ]
            }
    if plus:
        for term in UNKNOWN_TERMS:
            for template in TEMPLATES:
                yield {
                    "messages": [
                        {"role": "user", "content": template.format(term=term)},
                        {"role": "assistant", "content": UNKNOWN_ANSWER.format(term=term)},
                    ]
                }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plus", action="store_true", help="テンプレート追加と「用語集に無い語」の例を足す")
    args = parser.parse_args()
    out = sys.stdout.buffer  # Windows でも UTF-8 で書く
    for record in records(args.plus):
        out.write((json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
