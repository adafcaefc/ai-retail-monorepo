#!/usr/bin/env bash

set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SPEC="plans/adaptive-retrieval-master-spec.md"
STATUS="plans/adaptive-retrieval-overnight-status.md"
LOGDIR="logs/codex-overnight"

mkdir -p "$LOGDIR"

if [[ ! -f "$SPEC" ]]; then
    echo "ERROR: Missing $SPEC"
    exit 10
fi

get_status() {
    if [[ ! -f "$STATUS" ]]; then
        echo "IN_PROGRESS"
        return
    fi

    sed -n 's/^OVERALL_STATUS:[[:space:]]*//p' "$STATUS" | head -n 1
}

run_agent() {
    local model="$1"
    local label="$2"
    local prompt_file="$3"

    local json_log="$LOGDIR/${label}.jsonl"
    local stderr_log="$LOGDIR/${label}.stderr.log"

    echo
    echo "============================================================"
    echo "Starting $label"
    echo "Model: $model"
    echo "Prompt: $prompt_file"
    echo "============================================================"
    echo

    codex exec \
      -m "$model" \
      -c 'model_reasoning_effort="high"' \
      --sandbox workspace-write \
      --ask-for-approval on-request \
      -c approvals_reviewer=auto_review \
      -c sandbox_workspace_write.network_access=true \
      --json \
      - \
      < "$prompt_file" \
      > "$json_log" \
      2> "$stderr_log"

    local rc=$?

    echo
    echo "$label exited with code: $rc"
    echo "Current project status: $(get_status)"
    echo "JSON log: $json_log"
    echo "stderr log: $stderr_log"
    echo

    return $rc
}

echo "Repository: $ROOT"
echo "Branch: $(git branch --show-current)"
echo "Starting status: $(get_status)"

if [[ "$(git branch --show-current)" == "main" ]]; then
    echo "ERROR: Refusing to run overnight automation on main."
    exit 20
fi


# ============================================================
# Luna pass 1
# ============================================================

if [[ "$(get_status)" != "COMPLETE" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-1" \
      "plans/codex-prompts/luna-1.md" || true
fi


# ============================================================
# Luna pass 2
# ============================================================

if [[ "$(get_status)" != "COMPLETE" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-2" \
      "plans/codex-prompts/luna-2.md" || true
fi


# ============================================================
# Luna pass 3
# ============================================================

if [[ "$(get_status)" != "COMPLETE" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-3" \
      "plans/codex-prompts/luna-3.md" || true
fi


# ============================================================
# Sol final pass
# ============================================================

if [[ "$(get_status)" != "COMPLETE" ]]; then
    echo
    echo "Luna passes finished without COMPLETE."
    echo "Escalating exactly once to Sol High."
    echo

    run_agent \
      "gpt-5.6-sol" \
      "sol-final" \
      "plans/codex-prompts/sol-final.md" || true
fi


# ============================================================
# Final result
# ============================================================

FINAL_STATUS="$(get_status)"

echo
echo "============================================================"
echo "OVERNIGHT RUN FINISHED"
echo "Final status: $FINAL_STATUS"
echo "============================================================"

case "$FINAL_STATUS" in
    COMPLETE)
        exit 0
        ;;
    BLOCKED)
        exit 2
        ;;
    *)
        echo "Project did not reach COMPLETE."
        echo "Inspect $STATUS and $LOGDIR."
        exit 3
        ;;
esac
