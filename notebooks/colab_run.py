import subprocess, sys, json, time, re, gc, urllib.request
from pathlib import Path
if not globals().get("SKIP_PIP"):
    subprocess.run([sys.executable,"-m","pip","uninstall","-y","-q","torchao"])
    subprocess.run([sys.executable,"-m","pip","install","-q","transformers==5.18.0","peft==0.21.1","trl==1.14.2","accelerate==1.15.0","datasets==5.1.0"], check=True)
import transformers, peft, trl, accelerate, datasets, torch
print({m.__name__: m.__version__ for m in [transformers, peft, trl, accelerate, datasets, torch]})
URL = "https://raw.githubusercontent.com/matsuolab/lecture-ai-engineering-2026/main/data/glossary.json"
GLOSSARY = json.loads(urllib.request.urlopen(URL).read().decode("utf-8"))["terms"]
EVAL = json.loads("{\"note\": \"第2回 宿題（発展）の評価用質問と正解。category: exact=用語集にある語をそのまま / paraphrase=言い回しを変えた質問 / unknown=用語集にない語。must_include は「グループごとにどれか 1 つを含む」を全グループで満たせば正解。unknown は『用語集に載っていません』系の応答（abstain）が正解。query は検索方式で使う検索語（質問文の中の名詞句をそのまま使う想定）。\", \"abstain_pattern\": \"用語集(に|には)(は)?(載って|記載が|見つかり|あり)\", \"items\": [{\"id\": \"E01\", \"category\": \"exact\", \"term_id\": \"lora\", \"question\": \"LoRAとは？\", \"query\": \"LoRA\", \"must_include\": [[\"低ランク\"]]}, {\"id\": \"E02\", \"category\": \"exact\", \"term_id\": \"qlora\", \"question\": \"QLoRAとは？\", \"query\": \"QLoRA\", \"must_include\": [[\"4ビット\", \"4bit\", \"4-bit\", \"4 ビット\"], [\"量子化\"]]}, {\"id\": \"E03\", \"category\": \"exact\", \"term_id\": \"default-model\", \"question\": \"既定モデルとは？\", \"query\": \"既定モデル\", \"must_include\": [[\"gemini-3.5-flash-lite\"]]}, {\"id\": \"E04\", \"category\": \"exact\", \"term_id\": \"homework-levels\", \"question\": \"宿題の3レベルとは？\", \"query\": \"宿題の3レベル\", \"must_include\": [[\"基礎\"], [\"発展\"]]}, {\"id\": \"E05\", \"category\": \"exact\", \"term_id\": \"pi\", \"question\": \"Piとは？\", \"query\": \"Pi\", \"must_include\": [[\"コーディングエージェント\"], [\"MIT\"]]}, {\"id\": \"E06\", \"category\": \"exact\", \"term_id\": \"lec-start-tag\", \"question\": \"lecNN-start タグとは？\", \"query\": \"lecNN-start タグ\", \"must_include\": [[\"ブランチ\"]]}, {\"id\": \"E07\", \"category\": \"exact\", \"term_id\": \"temperature\", \"question\": \"temperatureとは？\", \"query\": \"temperature\", \"must_include\": [[\"ランダム\"]]}, {\"id\": \"E08\", \"category\": \"exact\", \"term_id\": \"tool-namespace\", \"question\": \"ツールの名前空間とは？\", \"query\": \"ツールの名前空間\", \"must_include\": [[\"接頭辞\", \"プレフィックス\"]]}, {\"id\": \"E09\", \"category\": \"exact\", \"term_id\": \"answer-md\", \"question\": \"answer.mdとは？\", \"query\": \"answer.md\", \"must_include\": [[\"PR\", \"プルリクエスト\"]]}, {\"id\": \"E10\", \"category\": \"exact\", \"term_id\": \"harness\", \"question\": \"ハーネスとは？\", \"query\": \"ハーネス\", \"must_include\": [[\"ループ\"], [\"ツール\"]]}, {\"id\": \"P01\", \"category\": \"paraphrase\", \"term_id\": \"default-model\", \"question\": \"演習で標準的に使う Gemini のモデル名を教えて\", \"query\": \"標準的に使うモデル\", \"must_include\": [[\"gemini-3.5-flash-lite\"]]}, {\"id\": \"P02\", \"category\": \"paraphrase\", \"term_id\": \"homework-levels\", \"question\": \"宿題は全部のレベルをやらないといけないの？\", \"query\": \"宿題\", \"must_include\": [[\"1つ\", \"一つ\", \"どれか\"]]}, {\"id\": \"P03\", \"category\": \"paraphrase\", \"term_id\": \"qlora\", \"question\": \"ベースモデルを4bitに量子化してからLoRAで学習するやり方は何と呼びますか？\", \"query\": \"4bitに量子化してからLoRA\", \"must_include\": [[\"QLoRA\"]]}, {\"id\": \"P04\", \"category\": \"paraphrase\", \"term_id\": \"lora-rank\", \"question\": \"LoRA の r を大きくすると何が変わりますか？\", \"query\": \"r\", \"must_include\": [[\"表現力\"]]}, {\"id\": \"P05\", \"category\": \"paraphrase\", \"term_id\": \"hallucination\", \"question\": \"LLMがもっともらしい嘘をつく現象を何と言いますか？\", \"query\": \"もっともらしい嘘\", \"must_include\": [[\"ハルシネーション\"]]}, {\"id\": \"P06\", \"category\": \"paraphrase\", \"term_id\": \"pi\", \"question\": \"Pi coding agent の npm パッケージ名は？\", \"query\": \"Pi coding agent\", \"must_include\": [[\"@earendil-works/pi-coding-agent\"]]}, {\"id\": \"P07\", \"category\": \"paraphrase\", \"term_id\": \"codespaces\", \"question\": \"コードスペースを使わないときはどうすればいいですか？\", \"query\": \"コードスペース\", \"must_include\": [[\"停止\"]]}, {\"id\": \"P08\", \"category\": \"paraphrase\", \"term_id\": \"api-key\", \"question\": \"この講座では API key をどこに登録しますか？\", \"query\": \"API key\", \"must_include\": [[\"Codespaces secret\", \"Codespacesのシークレット\", \"GEMINI_API_KEY\"]]}, {\"id\": \"P09\", \"category\": \"paraphrase\", \"term_id\": \"overfitting\", \"question\": \"学習データにだけ合いすぎて未知の入力に弱くなる状態を何と言いますか？\", \"query\": \"学習データにだけ合いすぎ\", \"must_include\": [[\"過学習\", \"オーバーフィッティング\"]]}, {\"id\": \"P10\", \"category\": \"paraphrase\", \"term_id\": \"mcp-config\", \"question\": \"MCPの設定ファイルではサーバーをどう書きますか？\", \"query\": \"MCPの設定ファイル\", \"must_include\": [[\"mcpServers\"]]}, {\"id\": \"U01\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"RAGとは？\", \"query\": \"RAG\", \"must_include\": []}, {\"id\": \"U02\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"蒸留とは？\", \"query\": \"蒸留\", \"must_include\": []}, {\"id\": \"U03\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"DPOとは？\", \"query\": \"DPO\", \"must_include\": []}, {\"id\": \"U04\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"エンベディングとは？\", \"query\": \"エンベディング\", \"must_include\": []}, {\"id\": \"U05\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"プロンプトインジェクションとは？\", \"query\": \"プロンプトインジェクション\", \"must_include\": []}, {\"id\": \"U06\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"RLHFとは？\", \"query\": \"RLHF\", \"must_include\": []}, {\"id\": \"U07\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"Mixture of Expertsとは？\", \"query\": \"Mixture of Experts\", \"must_include\": []}, {\"id\": \"U08\", \"category\": \"unknown\", \"term_id\": null, \"question\": \"ベクトルデータベースとは？\", \"query\": \"ベクトルデータベース\", \"must_include\": []}]}")
# ---- scripts/make_sft_dataset.py と同じ定数と records() ----
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
    terms = GLOSSARY
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



DATA = {"base": list(records(False)), "plus": list(records(True))}
CONFIG = {"base_model": "Qwen/Qwen3.5-0.8B", "revision": "2fc06364715b967f1860aea9cf38778875588b17", "seed": 42,
    "num_train_epochs": 5, "warmup_steps": 6, "lr": 2e-4, "lora_r": 16, "lora_alpha": 32, "max_seq_len": 512,
    "max_new_tokens": 200, "gen": {"do_sample": False}, "work_dir": "/content/glossary_lab"}
WORK = Path(CONFIG["work_dir"]); WORK.mkdir(parents=True, exist_ok=True)
ABSTAIN = re.compile(EVAL["abstain_pattern"]); items = EVAL["items"]
for v, rows in DATA.items():
    qs = {r["messages"][0]["content"] for r in rows}
    assert not [it["id"] for it in items if it["question"] in qs]
    print(v, len(rows), "件")
print("glossary", len(GLOSSARY), "eval", len(items))

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"])
if tok.pad_token is None: tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"], dtype=torch.float32).to(DEVICE)
model.config.use_cache = True
print("loaded:", CONFIG["base_model"], "| device:", DEVICE, "| 重みのメモリ(GB):", round(model.get_memory_footprint() / 1e9, 2))

def generate(model, messages):
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=CONFIG["max_new_tokens"], pad_token_id=tok.pad_token_id, **CONFIG["gen"])
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

# ---- 第3回 app/tools.py の search_glossary と同じ処理（用語集だけアップロードしたものを使う） ----
MAX_RESULTS = 3
def _normalize(text): return text.casefold().replace(" ", "").replace("　", "")
def _names(e): return [_normalize(e["term"]), _normalize(e["id"])] + [_normalize(a) for a in e["aliases"]]
def search_glossary(query):
    q = _normalize(query)
    if not q: return "検索語が空です。調べたい用語を1つ指定してください。"
    exact = [e for e in GLOSSARY if q in _names(e)]
    partial = [e for e in GLOSSARY if e not in exact and any(q in n or (len(n) >= 3 and n in q) for n in _names(e))]
    in_def = [e for e in GLOSSARY if e not in exact and e not in partial and q in _normalize(e["definition"])]
    hits = (exact + partial + in_def)[:MAX_RESULTS]
    if not hits: return f"用語集に「{query}」は見つかりませんでした。"
    return json.dumps([{"term": e["term"], "lecture": e["lecture"], "definition": e["definition"], "related": e["related"]} for e in hits], ensure_ascii=False)

RAG_TEMPLATE = ("以下は講座の用語集を検索した結果です。\n{result}\n\n"
                "検索結果だけを根拠に、質問に日本語で簡潔に答えてください。"
                "質問の用語が検索結果に無い場合は「用語集に載っていません」と答えてください。\n\n質問: {question}")

def build_messages(item, mode):
    if mode == "rag":
        content = RAG_TEMPLATE.format(result=search_glossary(item["query"]), question=item["question"])
    else:
        content = item["question"]   # 学習データ（make_sft_dataset.py）と同じく user の質問だけ
    return [{"role": "user", "content": content}]

def score(item, raw):
    abstained = bool(ABSTAIN.search(raw))
    if item["category"] == "unknown":
        ok = abstained
        fail = "" if ok else "断定"
    else:
        has_all = all(any(w in raw for w in group) for group in item["must_include"])
        ok = has_all and not abstained
        fail = "" if ok else ("逃げ" if abstained else "語句不足")
    return ok, abstained, fail

def evaluate(model, label, mode):
    rows, t0 = [], time.time()
    for it in items:
        raw = generate(model, build_messages(it, mode))
        ok, abstained, fail = score(it, raw)
        rows.append({"id": it["id"], "category": it["category"], "question": it["question"], "raw": raw,
                     "ok": ok, "abstained": abstained, "fail": fail})
    summary = {"label": label, "n": len(rows), "seconds": round(time.time() - t0, 1)}
    for cat in ["exact", "paraphrase", "unknown"]:
        rs = [r for r in rows if r["category"] == cat]
        summary[f"{cat}_rate"] = round(sum(r["ok"] for r in rs) / len(rs), 3)
    summary["all_rate"] = round(sum(r["ok"] for r in rows) / len(rows), 3)
    summary["逃げ"] = sum(r["fail"] == "逃げ" for r in rows)
    summary["断定"] = sum(r["fail"] == "断定" for r in rows)
    (WORK / f"eval_{label}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return summary, rows
before_summary, before_rows = evaluate(model, "before", "plain")
rag_summary, rag_rows = evaluate(model, "rag", "rag")


RESULTS = {}
def run_variant(VARIANT):
    global model, trainer, tuned, train_out, losses, TRAIN_SECONDS
    if VARIANT != "base":
        del trainer, tuned, model; gc.collect(); torch.cuda.empty_cache()
        model = AutoModelForCausalLM.from_pretrained(CONFIG["base_model"], revision=CONFIG["revision"], dtype=torch.float32).to(DEVICE)
    from peft import LoraConfig
    from trl import SFTTrainer, SFTConfig
    from datasets import Dataset
    
    train_ds = Dataset.from_list(DATA[VARIANT])   # 各行は {"messages": [...]}。演習の to_chat と同じ形式
    model.config.use_cache = False
    lora = LoraConfig(r=CONFIG["lora_r"], lora_alpha=CONFIG["lora_alpha"], lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    sft = SFTConfig(output_dir=str(WORK / VARIANT / "ckpt"), num_train_epochs=CONFIG["num_train_epochs"], per_device_train_batch_size=4, gradient_accumulation_steps=2,
                    learning_rate=CONFIG["lr"], lr_scheduler_type="cosine", warmup_steps=CONFIG["warmup_steps"], logging_steps=10, save_steps=50, save_total_limit=1,
                    fp16=False, max_length=CONFIG["max_seq_len"], packing=False, report_to="none", seed=CONFIG["seed"])
    trainer = SFTTrainer(model=model, args=sft, train_dataset=train_ds, peft_config=lora, processing_class=tok)
    trainer.model.print_trainable_parameters()
    t0 = time.time()
    train_out = trainer.train()   # 途中で止まったら trainer.train(resume_from_checkpoint=True)
    TRAIN_SECONDS = round(time.time() - t0)
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h] or [train_out.training_loss]   # 10 ステップ未満だと途中の loss が記録されない
    print(f"学習時間: {TRAIN_SECONDS} 秒 | ステップ数: {trainer.state.global_step} | エポック: {trainer.state.epoch:.1f} | 最初の loss: {losses[0]:.3f} | 最終 loss: {losses[-1]:.3f}")
    trainer.model.save_pretrained(WORK / VARIANT / "adapter")
    tuned = trainer.model
    tuned.config.use_cache = True
    _ = tuned.eval()
    after_summary, after_rows = evaluate(tuned, f"after_{VARIANT}", "plain")
    RESULTS[VARIANT] = {"config": {**CONFIG, "variant": VARIANT}, "versions": {m.__name__: m.__version__ for m in [transformers, peft, trl, torch]},
        "method": "LoRA（量子化なし）", "environment": "Google Colab " + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"),
        "train_examples": len(DATA[VARIANT]),
        "train": {"seconds": TRAIN_SECONDS, "steps": trainer.state.global_step, "first_loss": losses[0], "final_loss": losses[-1]},
        "before": before_summary, "rag": rag_summary, "after": after_summary,
        "regressed": [b["id"] for b, a in zip(before_rows, after_rows) if b["ok"] and not a["ok"]]}
    (WORK / f"result_{VARIANT}.json").write_text(json.dumps(RESULTS[VARIANT], ensure_ascii=False, indent=2), encoding="utf-8")
    print("RESULT_JSON", json.dumps(RESULTS[VARIANT], ensure_ascii=False))
for _v in globals().get("VARIANTS", ["base", "plus"]):
    run_variant(_v)
print("DONE")
