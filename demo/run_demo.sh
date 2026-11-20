#!/usr/bin/env bash
# Official demonstration of CoalitionTravel (5 to 10 minutes). Every output below is
# produced by the program at run time; nothing is pre-written.
#
#   bash demo/run_demo.sh            # all scenarios, text output
#   bash demo/run_demo.sh --json     # the same with the canonical JSON output
#
# Natural-language part: with OLLAMA_MODEL set (and Ollama running) the request text is
# sent to the local model; otherwise the recorded extraction in
# demo/replay_lyon_alger.json is replayed (its provenance is shown as "replay").
set -u
cd "$(dirname "$0")/.."
PLAN=${PLAN:-coalition-travel-plan}
DATE=2027-01-15
FORMAT=()
[ "${1:-}" = "--json" ] && FORMAT=(--json)

step() { printf '\n\033[1m==== %s ====\033[0m\n' "$1"; }
run() { "$PLAN" "$@"; printf '[code de sortie : %s]\n' "$?"; }

step "1. Demande en langage naturel (v2) : extraction réelle par le LLM"
TEXT="Nous sommes deux, départ de Lyon pour Algiers, aller-retour : aller le 15 février 2027, retour le 25 février 2027, 500 euros maximum par personne."
echo "Demande : $TEXT"
# Measured limit (docs/FINAL_LLM_EVALUATION.md): qwen2.5:7b puts the two travellers in an
# invented profile and leaves the request-level count empty, so validation asks for it.
if [ -n "${OLLAMA_MODEL:-}" ]; then
  run --prompt "$TEXT" --reference-date $DATE ${FORMAT[@]+"${FORMAT[@]}"} < /dev/null
else
  echo "(OLLAMA_MODEL absent : rejeu de l'extraction enregistrée de qwen2.5:7b)"
  run --prompt "$TEXT" --extractor-replay demo/replay_lyon_alger.json \
    --reference-date $DATE ${FORMAT[@]+"${FORMAT[@]}"} < /dev/null
fi

step "1 bis. La même demande, structurée : alias, résumé, validation, proposition (v2)"
printf 'o\n' | run --draft-json demo/lyon_alger.json --reference-date $DATE ${FORMAT[@]+"${FORMAT[@]}"}

step "2. Clarification : une demande incomplète (nombre de voyageurs manquant)"
printf '2 voyageurs\no\n' | run --prompt "Tokyo, 500 euros par personne" \
  --extractor-replay demo/replay_clarification.json --reference-date $DATE ${FORMAT[@]+"${FORMAT[@]}"}

step "3. Demande v1 : coalition avantageuse (Tokyo, 8 voyageurs)"
run --draft-json demo/tokyo_coalition_v1.json --reference-date $DATE --yes ${FORMAT[@]+"${FORMAT[@]}"}

step "4. Absence de coalition avantageuse (Tokyo, 2 voyageurs)"
run --draft-json demo/tokyo_alone_v1.json --reference-date $DATE --yes ${FORMAT[@]+"${FORMAT[@]}"}

step "5. Contrainte bloquante : aucun accord individuel (budget de 100 €)"
run --draft-json demo/tokyo_no_agreement_v1.json --reference-date $DATE --yes ${FORMAT[@]+"${FORMAT[@]}"}

step "6. Contrainte bloquante : aucune offre admissible (Oslo)"
run --draft-json demo/oslo_no_offer_v1.json --reference-date $DATE --yes ${FORMAT[@]+"${FORMAT[@]}"}

step "7. Lieu inconnu (Oran)"
run --draft-json demo/lyon_oran_unknown_place.json --reference-date $DATE --yes ${FORMAT[@]+"${FORMAT[@]}"}
