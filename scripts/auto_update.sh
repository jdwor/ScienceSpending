#!/bin/bash
# Automated weekly data update for sciencespending.org.
#
# Runs the UPDATE.md workflow end to end, validates the result against the
# last published data (scripts/validate_update.py), and commits + pushes to
# main (GitHub Pages redeploys the site). If anything fails, nothing is
# published and the site keeps its last good data.
#
# Runs from a dedicated clone outside ~/Documents (macOS blocks launchd jobs
# from reading ~/Documents) that holds its own copy of the API caches.
# Scheduled by ~/Library/LaunchAgents/org.sciencespending.update.plist
# (template: scripts/org.sciencespending.update.plist).
#
#   Logs:    ~/Library/Logs/sciencespending/  (STATUS.txt = last result)
#   Dry run: SCISPEND_DRY_RUN=1 scripts/auto_update.sh  (no commit/push)
#
# Everything lives in main() so that `git reset` updating this file mid-run
# can't affect the running copy (bash reads scripts incrementally).

main() {
    set -uo pipefail
    local repo="${SCISPEND_REPO:-$HOME/ScienceSpending-auto}"
    local log_dir="$HOME/Library/Logs/sciencespending"
    local dry_run="${SCISPEND_DRY_RUN:-0}"
    local py=/usr/bin/python3
    export PATH=/usr/bin:/bin:/usr/sbin:/sbin
    export PYTHONWARNINGS=ignore

    mkdir -p "$log_dir"
    local log="$log_dir/update_$(date +%Y-%m-%d_%H%M%S).log"
    exec >>"$log" 2>&1
    echo "=== sciencespending auto-update $(date) (dry_run=$dry_run) ==="

    # One run at a time (stale locks from crashed runs expire after 6h)
    local lock="$log_dir/.lock"
    if ! mkdir "$lock" 2>/dev/null; then
        if [ -n "$(find "$lock" -maxdepth 0 -mmin +360)" ]; then
            rm -rf "$lock" && mkdir "$lock"
        else
            echo "Another run is in progress; exiting."
            return 0
        fi
    fi
    trap 'rm -rf "$lock"' EXIT

    # Keep the Mac awake while this runs (it sleeps after 1 min idle)
    caffeinate -i -s -w $$ &

    fail() {
        echo "FAILED: $1"
        git -C "$repo" reset --hard -q origin/main  # discard partial output
        printf '%s  FAILED: %s\n  log: %s\n' "$(date '+%Y-%m-%d %H:%M')" "$1" "$log" > "$log_dir/STATUS.txt"
        osascript -e "display notification \"$1\" with title \"sciencespending update failed\"" 2>/dev/null
        exit 1
    }

    # Retry flaky network steps: retry <attempts> <cmd...>
    retry() {
        local n=$1; shift
        local i
        for ((i = 1; i <= n; i++)); do
            "$@" && return 0
            echo "  attempt $i/$n failed: $*"
            [ "$i" -lt "$n" ] && sleep 300
        done
        return 1
    }

    cd "$repo" || fail "repo not found at $repo"

    echo "--- Sync with origin/main"
    retry 3 git fetch -q origin || fail "git fetch failed"
    git reset --hard -q origin/main || fail "git reset failed"
    echo "HEAD: $(git log --oneline -1)"

    echo "--- Step 1: awards"
    retry 2 $py -m awards.preprocess || fail "awards.preprocess failed"
    retry 2 $py -m awards.preprocess_all || fail "awards.preprocess_all failed"

    echo "--- Step 2: SF-133 obligations"
    local check
    check=$(retry 2 $py data/download.py --check) || fail "SF-133 check failed"
    echo "$check"
    if grep -q "NEW DATA AVAILABLE" <<<"$check"; then
        $py data/preprocess.py || fail "data/preprocess.py failed"
    fi

    echo "--- Step 3: build"
    $py build.py || fail "build.py failed"

    echo "--- Step 4: validate"
    $py scripts/validate_update.py
    local status=$?
    if [ "$status" -eq 2 ]; then
        # NSF drop: rule out a truncated fetch by re-fetching open-FY NSF caches
        echo "NSF drop detected — re-fetching open-FY NSF caches to confirm"
        local fys
        fys=$($py -c "import config as c; print(' '.join(str(f) for f in (c.CURRENT_FY - 1, c.CURRENT_FY) if not c.is_fy_frozen(f)))")
        for fy in $fys; do rm -f awards/cache/nsf/fy${fy}_d*.json; done
        retry 2 $py -m awards.preprocess || fail "NSF re-fetch failed"
        $py build.py || fail "build.py failed after NSF re-fetch"
        $py scripts/validate_update.py --accept-nsf-drop
        status=$?
    fi
    [ "$status" -eq 0 ] || fail "validation failed (see log)"

    echo "--- Step 5: publish"
    local paths=(data/processed awards/processed docs/data file_registry.json)
    if [ -z "$(git status --porcelain -- "${paths[@]}")" ]; then
        echo "No data changes."
        printf '%s  OK (no changes)\n' "$(date '+%Y-%m-%d %H:%M')" > "$log_dir/STATUS.txt"
        return 0
    fi
    git status --short -- "${paths[@]}"
    local summary
    summary=$($py -c "
import json; c = json.load(open('docs/data/site_data.json'))['config']
print(f\"obligations FY{c['current_fy']} through {c['latest_period_label']}; awards FY{c['awards_current_fy']}\")")

    if [ "$dry_run" = "1" ]; then
        echo "DRY RUN — not committing. Would publish: $summary"
        git reset --hard -q origin/main
        printf '%s  DRY RUN OK: %s\n' "$(date '+%Y-%m-%d %H:%M')" "$summary" > "$log_dir/STATUS.txt"
        return 0
    fi

    git add -A -- "${paths[@]}"
    git commit -q -m "data update" || fail "git commit failed"
    if ! retry 3 git push -q origin HEAD:main; then
        git pull -q --rebase origin main && git push -q origin HEAD:main || fail "git push failed"
    fi
    echo "Published $(git log --oneline -1): $summary"
    printf '%s  OK: published %s\n' "$(date '+%Y-%m-%d %H:%M')" "$summary" > "$log_dir/STATUS.txt"

    # Keep the 26 most recent logs (~6 months of weekly runs)
    ls -1t "$log_dir"/update_*.log 2>/dev/null | tail -n +27 | xargs rm -f 2>/dev/null
    return 0
}

main "$@"
exit $?
