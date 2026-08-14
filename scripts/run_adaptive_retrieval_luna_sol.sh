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

    local status
    status="$(sed -n 's/^OVERALL_STATUS:[[:space:]]*//p' "$STATUS" | head -n 1)"

    if [[ -z "$status" ]]; then
        echo "IN_PROGRESS"
    else
        echo "$status"
    fi
}

run_agent() {
    local model="$1"
    local label="$2"
    local prompt_file="$3"

    local json_log="$LOGDIR/${label}.jsonl"
    local stderr_log="$LOGDIR/${label}.stderr.log"

    echo
    echo "============================================================"
    echo "Starting: $label"
    echo "Model:    $model"
    echo "Prompt:   $prompt_file"
    echo "============================================================"
    echo

    if [[ ! -f "$prompt_file" ]]; then
        echo "ERROR: Missing prompt file: $prompt_file"
        return 11
    fi

    codex exec \
      -m "$model" \
      -c 'model_reasoning_effort="high"' \
      --sandbox workspace-write \
      -c 'approval_policy="on-request"' \
      -c 'approvals_reviewer="auto_review"' \
      -c 'sandbox_workspace_write.network_access=true' \
      --json \
      - \
      < "$prompt_file" \
      > "$json_log" \
      2> "$stderr_log"

    local rc=$?

    echo
    echo "$label exited with code: $rc"
    echo "Current project status: $(get_status)"
    echo "JSON log:   $json_log"
    echo "stderr log: $stderr_log"
    echo

    return "$rc"
}

echo
echo "============================================================"
echo "AI RETAIL 360 — ADAPTIVE RETRIEVAL OVERNIGHT RUN"
echo "============================================================"
echo
echo "Repository:      $ROOT"
echo "Branch:          $(git branch --show-current)"
echo "Starting status: $(get_status)"
echo

CURRENT_BRANCH="$(git branch --show-current)"

if [[ "$CURRENT_BRANCH" == "main" ]]; then
    echo "ERROR: Refusing to run autonomous implementation on main."
    echo "Switch to feat/adaptive-retrieval first."
    exit 20
fi

if [[ -z "$CURRENT_BRANCH" ]]; then
    echo "ERROR: Repository appears to be in detached HEAD state."
    exit 21
fi

echo "Git status before run:"
git status --short
echo


# ============================================================
# LUNA HIGH — PASS 1
# Retrieval Gateway + Query Catalog + Adaptive Planner
# ============================================================

if [[ "$(get_status)" != "COMPLETE" && "$(get_status)" != "BLOCKED" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-1" \
      "plans/codex-prompts/luna-1.md" || true
fi


# ============================================================
# LUNA HIGH — PASS 2
# Policy Engine + SQL Compiler + Orchestrator
# ============================================================

if [[ "$(get_status)" != "COMPLETE" && "$(get_status)" != "BLOCKED" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-2" \
      "plans/codex-prompts/luna-2.md" || true
fi


# ============================================================
# LUNA HIGH — PASS 3
# Existing Chatbot Integration + E2E Validation
# ============================================================

if [[ "$(get_status)" != "COMPLETE" && "$(get_status)" != "BLOCKED" ]]; then
    run_agent \
      "gpt-5.6-luna" \
      "luna-3" \
      "plans/codex-prompts/luna-3.md" || true
fi


# ============================================================
# SOL HIGH — ONE FINAL SENIOR ENGINEERING PASS
# ============================================================

if [[ "$(get_status)" != "COMPLETE" && "$(get_status)" != "BLOCKED" ]]; then
    echo
    echo "============================================================"
    echo "Luna passes did not reach COMPLETE."
    echo "Escalating exactly once to Sol High."
    echo "============================================================"
    echo

    run_agent \
      "gpt-5.6-sol" \
      "sol-final" \
      "plans/codex-prompts/sol-final.md" || true
fi


# ============================================================
# FINAL STATUS
# ============================================================

FINAL_STATUS="$(get_status)"

echo
echo "============================================================"
echo "OVERNIGHT RUN FINISHED"
echo "Final status: $FINAL_STATUS"
echo "============================================================"
echo

echo "Git status:"
git status --short
echo

echo "Logs:"
ls -lh "$LOGDIR" 2>/dev/null || true
echo

case "$FINAL_STATUS" in
    COMPLETE)
        echo "SUCCESS: Adaptive retrieval implementation reports COMPLETE."
        exit 0
        ;;
    BLOCKED)
        echo "BLOCKED: Read $STATUS for the documented blocker."
        exit 2
        ;;
    *)
        echo "INCOMPLETE: The project did not reach COMPLETE or BLOCKED."
        echo "Read:"
        echo "  $STATUS"
        echo
        echo "Then inspect:"
        echo "  $LOGDIR"
        exit 3
        ;;
esac
