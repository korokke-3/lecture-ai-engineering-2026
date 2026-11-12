#!/usr/bin/env bash
# 一時的な補助スクリプト：Codespace で judge を実行し、結果を lec04 に push する（PR の前に削除する）
set -u
cd /workspaces/lecture-ai-engineering-2026
TAG="${1:-run}"
git pull --no-rebase -q origin lec04
uv run python -m app.judge --wait 2 > "lectures/04/judge_log_${TAG}.txt" 2>&1
cp lectures/04/judge_result.json "lectures/04/judge_result_${TAG}.json"
git add lectures/04
git commit -q -m "第4回 演習: judge の実行結果（${TAG}）"
git push -q origin lec04
echo "DONE ${TAG}"
