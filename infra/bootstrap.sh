#!/usr/bin/env bash
# Bootstrap a fresh Forgejo instance for the course book.
#
#   ./bootstrap.sh <instructor> <org> <repo> [student ...]
#
# Creates: instructor admin account, org + repo, branch protection on main
# (PRs only; instructor may push), one account + token per student, a CI
# token + the repo secrets/vars the workflows need, and a runner
# registration token.
#
# Requires: docker compose services up (`docker compose up -d`), curl, jq.
set -euo pipefail

INSTRUCTOR=${1:?usage: bootstrap.sh <instructor> <org> <repo> [student ...]}
ORG=${2:?org name required}
REPO=${3:?repo name required}
shift 3
STUDENTS=("$@")

FORGEJO_URL=${FORGEJO_URL:-http://localhost:3000}
SITE_URL=${SITE_URL:-http://localhost:8080}
COMPOSE=(docker compose)
FORGEJO_EXEC=("${COMPOSE[@]}" exec -T --user 1000 forgejo forgejo)

pw() { head -c 24 /dev/urandom | base64 | tr -d '/+=' | head -c 16; }

api() { # method path [json]
  local method=$1 path=$2 data=${3:-}
  curl -fsS -X "$method" \
    -H "Authorization: token $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    ${data:+-d "$data"} \
    "$FORGEJO_URL/api/v1$path"
}

echo "==> Waiting for Forgejo to answer at $FORGEJO_URL"
for _ in $(seq 60); do
  curl -fsS "$FORGEJO_URL/api/v1/version" >/dev/null 2>&1 && break
  sleep 2
done

echo "==> Creating instructor admin account: $INSTRUCTOR"
INSTRUCTOR_PW=$(pw)
"${FORGEJO_EXEC[@]}" admin user create \
  --admin --username "$INSTRUCTOR" --password "$INSTRUCTOR_PW" \
  --email "$INSTRUCTOR@example.org" --must-change-password=false \
  || echo "    (user may already exist)"

echo "==> Creating admin API token"
ADMIN_TOKEN=$("${FORGEJO_EXEC[@]}" admin user generate-access-token \
  --username "$INSTRUCTOR" --token-name "bootstrap-$(date +%s)" \
  --scopes all --raw | tr -d '[:space:]')

echo "==> Creating org $ORG and repo $ORG/$REPO"
api POST /orgs "{\"username\": \"$ORG\"}" >/dev/null 2>&1 || echo "    (org exists)"
api POST "/orgs/$ORG/repos" \
  "{\"name\": \"$REPO\", \"private\": false, \"default_branch\": \"main\", \"auto_init\": false}" \
  >/dev/null 2>&1 || echo "    (repo exists)"

echo "==> Protecting main: no direct pushes except $INSTRUCTOR, PRs required"
# NOTE: protect main only; branch creation stays open so students can push
# their <username>/* change branches.
api POST "/repos/$ORG/$REPO/branch_protections" "{
  \"rule_name\": \"main\",
  \"enable_push\": true,
  \"enable_push_whitelist\": true,
  \"push_whitelist_usernames\": [\"$INSTRUCTOR\"],
  \"block_on_rejected_reviews\": true
}" >/dev/null 2>&1 || echo "    (protection exists)"

echo "==> Creating CI token + repo secrets/vars for the workflows"
CI_TOKEN=$("${FORGEJO_EXEC[@]}" admin user generate-access-token \
  --username "$INSTRUCTOR" --token-name "ci-$(date +%s)" \
  --scopes write:issue,write:repository --raw | tr -d '[:space:]')
api PUT "/repos/$ORG/$REPO/actions/secrets/CI_TOKEN" "{\"data\": \"$CI_TOKEN\"}" >/dev/null
api POST "/repos/$ORG/$REPO/actions/variables/SITE_URL" "{\"value\": \"$SITE_URL\"}" >/dev/null 2>&1 \
  || api PUT "/repos/$ORG/$REPO/actions/variables/SITE_URL" "{\"value\": \"$SITE_URL\"}" >/dev/null

echo "==> Runner registration token (register with infra/README.md step 3):"
"${FORGEJO_EXEC[@]}" actions generate-runner-token || true

CREDS_FILE=credentials.txt
{
  echo "Forgejo: $FORGEJO_URL"
  echo "instructor: $INSTRUCTOR / $INSTRUCTOR_PW"
} > "$CREDS_FILE"

for STUDENT in "${STUDENTS[@]}"; do
  echo "==> Creating student account: $STUDENT"
  SPW=$(pw)
  "${FORGEJO_EXEC[@]}" admin user create \
    --username "$STUDENT" --password "$SPW" \
    --email "$STUDENT@example.org" --must-change-password=false \
    || { echo "    (exists, skipping)"; continue; }
  STOKEN=$("${FORGEJO_EXEC[@]}" admin user generate-access-token \
    --username "$STUDENT" --token-name book-cli --scopes write:repository,write:issue --raw \
    | tr -d '[:space:]')
  echo "student $STUDENT: password=$SPW token=$STOKEN" >> "$CREDS_FILE"
done

cat <<EOF

Done. Credentials written to $CREDS_FILE — distribute privately, then delete.

Next steps:
  1. Push the canonical book repo:
       cd /path/to/book && git remote add origin $FORGEJO_URL/$ORG/$REPO.git
       git push -u origin main
  2. Register the runner (see infra/README.md, uses the token printed above).
  3. Each student: pipx install book-cli, then
       book clone $FORGEJO_URL/$ORG/$REPO.git
     and put their token in ~/.config/book/config.toml (see STUDENT_GUIDE.md).
EOF
