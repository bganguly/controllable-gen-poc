#!/usr/bin/env bash
# deploy.sh — controllable-gen-poc: local dev or GCP Cloud Run
# Usage: ./scripts/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env.gcp"
BACKEND_SVC="controllable-gen-backend"
FRONTEND_SVC="controllable-gen-frontend"
AR_REPO="controllable-gen-poc"
SA_NAME="cg-runner"

_local_running=0
lsof -ti:8000 >/dev/null 2>&1 && _local_running=1 || true
_gcp_deployed=0
[[ -f "$ENV_FILE" ]] && _gcp_deployed=1 || true

printf '\n=== controllable-gen-poc ===\n\n'
printf '  [1] Local  — uvicorn + npm dev, no Docker'
(( _local_running )) && printf ' [running]' || printf ' [not detected]'
printf '\n'
printf '  [2] Cloud  — GCP Cloud Run  (~$0/mo scales-to-zero)'
(( _gcp_deployed )) && printf ' [deployed]' || printf ' [not deployed]'
printf '\n'
printf '\nChoice [1/2, default 2]: '
read -r _MODE
case "$_MODE" in
  1) TARGET="local" ;;
  *) TARGET="cloud" ;;
esac

# ── local mode ────────────────────────────────────────────────────────────────
if [[ "$TARGET" == "local" ]]; then
  [[ -f "$ROOT/.env" ]] || { echo "Error: .env not found. Copy .env.example and fill in keys."; exit 1; }
  source "$ROOT/.env"

  cd "$ROOT/backend"
  [[ -d .venv ]] || python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -r "$ROOT/requirements.txt"
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
  BACKEND_PID=$!
  echo "Backend  → http://localhost:8000/health"

  cd "$ROOT/frontend"
  [[ -d node_modules ]] || npm install
  npm run dev &
  FRONTEND_PID=$!
  echo "Frontend → http://localhost:5173"

  _cleanup() { kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true; }
  trap _cleanup EXIT INT TERM
  wait "$BACKEND_PID" "$FRONTEND_PID"
  exit 0
fi

# ── GCP Cloud Run ─────────────────────────────────────────────────────────────
printf '\n--- GCP Cloud Run ---\n'
printf '  Backend:  Cloud Run (scales to zero)\n'
printf '  Frontend: Cloud Run (scales to zero, nginx proxy)\n'
printf '  Cost est: ~$0/mo  (Cloud Run free tier covers demo traffic)\n'

echo ""
echo "[1/4] Checking gcloud auth..."
if ! command -v gcloud >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    printf '  gcloud not found — installing via Homebrew...\n'
    brew install --cask google-cloud-sdk
    source "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc" 2>/dev/null || true
  else
    printf '  Install gcloud: https://cloud.google.com/sdk/docs/install\n'; exit 1
  fi
fi
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 || true)
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
  printf '  Not authenticated — logging in...\n'
  gcloud auth login
  ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 || true)
  [[ -n "$ACTIVE_ACCOUNT" ]] || { printf '  Login did not complete.\n' >&2; exit 1; }
fi
printf '  Authenticated as: %s\n' "$ACTIVE_ACCOUNT"

[[ -f "$ENV_FILE" ]] && source "$ENV_FILE"
_CONFIG_PROJECT=$(gcloud config get-value project 2>/dev/null || true)
GCP_PROJECT="${_CONFIG_PROJECT:-${GCP_PROJECT:-}}"
[[ -n "$GCP_PROJECT" ]] || { printf '  Set a project: gcloud config set project <id>\n' >&2; exit 1; }
_CONFIG_REGION=$(gcloud config get-value compute/region 2>/dev/null || true)
GCP_REGION="${_CONFIG_REGION:-${GCP_REGION:-us-central1}}"
printf '  Project: %s  Region: %s\n' "$GCP_PROJECT" "$GCP_REGION"

echo ""
echo "[2/4] API keys..."

_prompt_key() {
  local _label="$1" _secret_name="$2" _req="${3:-optional}"
  local _cur _ans _val
  _cur=$(gcloud secrets versions access latest --secret="$_secret_name" --project="$GCP_PROJECT" 2>/dev/null || echo "")
  if [[ -n "$_cur" ]]; then
    printf '  Use stored %s (%s...%s) (Y/n): ' \
      "$_label" "${_cur:0:8}" "${_cur: -4}" >&2
    read -r _ans
    _ans="${_ans:-Y}"
    if [[ ! "$_ans" =~ ^[Yy] ]]; then
      printf '  New value: ' >&2; read -rs _val; printf '\n' >&2
      printf '%s' "${_val:-$_cur}"
    else
      printf '%s' "$_cur"
    fi
  else
    local _env_val="${!_label:-}"
    if [[ -n "$_env_val" ]]; then
      printf '  Use .env %s (%s...%s) (Y/n): ' \
        "$_label" "${_env_val:0:8}" "${_env_val: -4}" >&2
      read -r _ans
      _ans="${_ans:-Y}"
      if [[ ! "$_ans" =~ ^[Yy] ]]; then
        printf '  New value: ' >&2; read -rs _val; printf '\n' >&2
        printf '%s' "${_val:-$_env_val}"
      else
        printf '%s' "$_env_val"
      fi
    elif [[ "$_req" == required ]]; then
      printf '  %-24s  (required): ' "$_label" >&2
      read -rs _val; printf '\n' >&2
      [[ -z "$_val" ]] && { printf '  Cannot deploy without %s.\n' "$_label" >&2; exit 1; }
      printf '%s' "$_val"
    else
      printf '  %-24s  (optional, Enter to skip): ' "$_label" >&2
      read -rs _val; printf '\n' >&2
      printf '%s' "$_val"
    fi
  fi
}

gcloud services enable secretmanager.googleapis.com --project "$GCP_PROJECT" --quiet 2>/dev/null

SA_EMAIL="${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "$SA_EMAIL" --project="$GCP_PROJECT" &>/dev/null; then
  printf '  Creating service account %s...\n' "$SA_EMAIL"
  gcloud iam service-accounts create "$SA_NAME" \
    --display-name="Controllable Gen Cloud Run SA" \
    --project="$GCP_PROJECT"
fi
gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor" --quiet 2>/dev/null || true

[[ -f "$ROOT/.env" ]] && source "$ROOT/.env"
for _sib in "$ROOT"/../*/.env; do
  [[ -f "$_sib" ]] || continue
  [[ -z "${ANTHROPIC_API_KEY:-}" ]] && \
    ANTHROPIC_API_KEY=$(grep "^ANTHROPIC_API_KEY=" "$_sib" 2>/dev/null | cut -d= -f2- | head -1 || true)
  [[ -z "${OPENAI_API_KEY:-}" ]] && \
    OPENAI_API_KEY=$(grep "^OPENAI_API_KEY=" "$_sib" 2>/dev/null | cut -d= -f2- | head -1 || true)
done
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
ANTHROPIC_API_KEY=$(_prompt_key "ANTHROPIC_API_KEY" "cg-anthropic-key" required)
OPENAI_API_KEY=$(_prompt_key    "OPENAI_API_KEY"    "cg-openai-key"    required)

_upsert_secret() {
  local _name="$1" _val="$2"
  [[ -z "$_val" ]] && return
  if gcloud secrets describe "$_name" --project="$GCP_PROJECT" &>/dev/null; then
    echo -n "$_val" | gcloud secrets versions add "$_name" --data-file=- --project="$GCP_PROJECT"
  else
    echo -n "$_val" | gcloud secrets create "$_name" --data-file=- --project="$GCP_PROJECT"
    gcloud secrets add-iam-policy-binding "$_name" --project="$GCP_PROJECT" \
      --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor" --quiet 2>/dev/null || true
  fi
}
_upsert_secret cg-anthropic-key "$ANTHROPIC_API_KEY"
_upsert_secret cg-openai-key    "$OPENAI_API_KEY"

echo ""
echo "[3/4] Building images via Cloud Build..."

gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  --project "$GCP_PROJECT" --quiet

if ! gcloud artifacts repositories describe "$AR_REPO" \
     --project="$GCP_PROJECT" --location="$GCP_REGION" &>/dev/null; then
  printf '  Creating Artifact Registry repo %s...\n' "$AR_REPO"
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$GCP_REGION" \
    --project="$GCP_PROJECT"
fi

AR_HOST="${GCP_REGION}-docker.pkg.dev"
_GIT_HASH=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || true)
TAG="${_GIT_HASH:+${_GIT_HASH}-}$(date +%Y%m%d%H%M%S)"
BACKEND_IMAGE="${AR_HOST}/${GCP_PROJECT}/${AR_REPO}/${BACKEND_SVC}:${TAG}"
FRONTEND_IMAGE="${AR_HOST}/${GCP_PROJECT}/${AR_REPO}/${FRONTEND_SVC}:${TAG}"

printf '  Building backend (%s)...\n' "$BACKEND_SVC"
cp "$ROOT/requirements.txt" "$ROOT/backend/requirements.txt"
gcloud builds submit \
  --tag "$BACKEND_IMAGE" \
  --project "$GCP_PROJECT" \
  "$ROOT/backend"
rm -f "$ROOT/backend/requirements.txt"

printf '  Building frontend (%s)...\n' "$FRONTEND_SVC"
gcloud builds submit \
  --tag "$FRONTEND_IMAGE" \
  --project "$GCP_PROJECT" \
  "$ROOT/frontend"

echo ""
echo "[4/4] Deploying to Cloud Run..."

printf '  Deploying %s...\n' "$BACKEND_SVC"
gcloud run deploy "$BACKEND_SVC" \
  --image="$BACKEND_IMAGE" \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY},OPENAI_API_KEY=${OPENAI_API_KEY}" \
  --allow-unauthenticated \
  --min-instances=0 \
  --timeout=120 \
  --quiet

BACKEND_URL=$(gcloud run services describe "$BACKEND_SVC" \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --format="value(status.url)")
printf '  Backend: %s\n' "$BACKEND_URL"

printf '  Deploying %s...\n' "$FRONTEND_SVC"
gcloud run deploy "$FRONTEND_SVC" \
  --image="$FRONTEND_IMAGE" \
  --region="$GCP_REGION" \
  --project="$GCP_PROJECT" \
  --service-account="$SA_EMAIL" \
  --set-env-vars="BACKEND_URL=${BACKEND_URL}" \
  --allow-unauthenticated \
  --min-instances=0 \
  --quiet

FRONTEND_URL=$(gcloud run services describe "$FRONTEND_SVC" \
  --region="$GCP_REGION" --project="$GCP_PROJECT" \
  --format="value(status.url)")

cat > "$ENV_FILE" <<ENVEOF
GCP_PROJECT=${GCP_PROJECT}
GCP_REGION=${GCP_REGION}
AR_REPO=${AR_REPO}
BACKEND_URL=${BACKEND_URL}
FRONTEND_URL=${FRONTEND_URL}
ENVEOF

printf '\n✓ Controllable Gen POC live (Cloud Run)\n'
printf '  App:       %s\n' "$FRONTEND_URL"
printf '  API:       %s\n' "$BACKEND_URL"
printf '  Cost:      ~$0/mo  (Cloud Run free tier)\n'
printf '  Tear down: gcloud run services delete %s %s --region=%s --project=%s\n' \
  "$BACKEND_SVC" "$FRONTEND_SVC" "$GCP_REGION" "$GCP_PROJECT"
