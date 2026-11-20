#!/bin/bash
# 3 embedding models x chunking configurations; top-k 1,3,5; thresholds swept.
S=${SCRATCH:?set SCRATCH to a work directory}
REPO=${REPO:-$(cd "$(dirname "$0")/../../.." && pwd)}
OUT=$S/rag_runs; mkdir -p $OUT/index
dig() { case $1 in nomic-embed-text) echo 0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f;; all-minilm) echo 1b226e2802dbb772b5fc32a58f103ca1804ef7501331012de126ab22f67475ef;; mxbai-embed-large) echo 468836162de7f81e041c43663fedbbba921dcea9b9fefea135685a39b2d83dd8;; esac; }
for model in nomic-embed-text all-minilm mxbai-embed-large; do
  for cfg in 1200:0 120:0 120:30 60:15; do
    cs=${cfg%%:*}; ov=${cfg##*:}; tag=${model}__c${cs}_o${ov}
    rm -f $OUT/index/$tag.sqlite
    (cd $REPO && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=Multi-Agent .venv/bin/python Multi-Agent/evaluate_retrieval.py --model $model --model-digest $(dig $model) --database $OUT/index/$tag.sqlite --chunk-size $cs --overlap $ov --top-k 1,3,5 --thresholds 0.0,0.3,0.5,0.6,0.7,0.8 --output $OUT/$tag.json > $OUT/$tag.log 2>&1)
    echo "$(date +%T) $tag exit=$?"
  done
done
echo RAG_DONE
