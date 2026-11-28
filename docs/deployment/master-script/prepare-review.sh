#!/usr/bin/env bash
# Render private review artifacts with the selected Fitfinity checkout. No provider calls.
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

usage() {
  cat >&2 <<'HELP'
Run from the Fitfinity checkout or set FITFINITY_REPO to its path.
  prepare-review.sh foundation|hosting PROFILE INPUTS_JSON NEW_ZIP
  prepare-review.sh probe|upgrade PROFILE MIGRATION_SECRET_ARN VPC_ID NEW_DIRECTORY [INSTALLED_STACK_ARN ORIGINAL_TEMPLATE_JSON]
  prepare-review.sh hosting-access PROFILE STACK_JSON RESOURCES_JSON OWNER_TEMPLATE_JSON OWNER_TEMPLATE_HASH NEW_JSON [BOUNDARY_STACK_JSON BOUNDARY_RESOURCES_JSON]
HELP
  exit 2
}

[[ $# -gt 0 ]] || usage
phase=$1
shift
infra="${FITFINITY_REPO:-$PWD}/backend/infrastructure"
case "$phase" in
  foundation|hosting)
    [[ $# -eq 3 ]] || usage
    exec python3 "$infra/portable_onboarding.py" "$phase" --profile "$1" --inputs "$2" --output "$3"
    ;;
  probe|upgrade)
    [[ $# -eq 4 || $# -eq 6 ]] || usage
    owner=()
    if [[ $# -eq 6 ]]; then
      owner=(--installed-stack-arn "$5" --installed-template "$6")
    fi
    exec python3 "$infra/schema_probe_setup.py" --purpose "$phase" --profile "$1" \
      --migration-secret-arn "$2" --vpc-id "$3" --output "$4" "${owner[@]}"
    ;;
  hosting-access)
    [[ $# -eq 6 || $# -eq 8 ]] || usage
    boundary=()
    if [[ $# -eq 8 ]]; then
      boundary=(--boundary-stack "$7" --boundary-resources "$8")
    fi
    exec python3 "$infra/release_access.py" --profile "$1" --stack "$2" --resources "$3" \
      --owner-template "$4" --owner-sha256 "$5" --output "$6" "${boundary[@]}"
    ;;
  *) usage ;;
esac
