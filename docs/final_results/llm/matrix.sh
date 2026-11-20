#!/bin/bash
# Usage: llm_matrix.sh RUN_TAG  -- runs 3 models x {v1 tree, v2 HEAD} x datasets, temperature 0 seed 0
S=${SCRATCH:?set SCRATCH to a work directory}
REPO=${REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
PY=$REPO/.venv/bin/python
TAG=$1
OUT=$S/llm_runs/$TAG; mkdir -p $OUT
dig() { case $1 in qwen2.5:3b) echo 357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b;; llama3.2:3b) echo a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72;; qwen2.5:7b) echo 845dbda0ea48ed749caafd9e6037047aa19acfcfd82e704d7ca97d631a0b697e;; esac; }
for model in qwen2.5:3b llama3.2:3b qwen2.5:7b; do
  m=${model//[:.]/_}
  for prompt in v1 v2; do
    if [ $prompt = v1 ]; then ROOT=${V1TREE:-$S/v1tree}; else ROOT=$REPO; fi
    sets="request_extraction.jsonl:extraction request_extraction_v2.jsonl:extraction request_profiles_v1.jsonl:profiles"
    [ $prompt = v2 ] && sets="$sets request_extraction_v3.jsonl:extraction"
    for item in $sets; do
      ds=${item%%:*}; task=${item##*:}
      (cd $ROOT && PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 PYTHONPATH=Multi-Agent $PY Multi-Agent/evaluate_requests.py --task $task --dataset data/eval/$ds --model $model --model-digest $(dig $model) --temperature 0 --seed 0 --timeout 180 --output $OUT/${m}__prompt_${prompt}__${ds%.jsonl}.json > $OUT/${m}__prompt_${prompt}__${ds%.jsonl}.log 2>&1)
      echo "$(date +%T) $model $prompt $ds exit=$?"
    done
  done
done
echo MATRIX_DONE
