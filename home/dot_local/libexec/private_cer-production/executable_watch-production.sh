#!/usr/bin/env bash
# Deploy the production image via cer-production-watch.service; requires its credentials and deploy.env.

set -Eeuo pipefail
umask 077

readonly BRANCH="${CER_PRODUCTION_BRANCH:-production}"
readonly REPOSITORY="${CER_GIT_REPOSITORY:-git@github.com:Carolina-Elite-Roofing/backend.git}"
readonly IMAGE_REPOSITORY="${CER_IMAGE_REPOSITORY:-ghcr.io/carolina-elite-roofing/backend}"
readonly GHCR_USERNAME="${CER_GHCR_USERNAME:-}"
readonly STATE_DIR="${XDG_STATE_HOME:-${HOME:?}/.local/state}/cer-production"
readonly IO_DIR="${CER_IO_DIR:-${HOME:?}/.local/share/cer-production/io}"
readonly DEPLOYED_REVISION_FILE="$STATE_DIR/deployed-revision"
readonly RELEASES_DIR="$STATE_DIR/releases"
readonly CREDENTIAL_DIR="${CREDENTIALS_DIRECTORY:-}"
readonly APPLICATION_ENV_FILE="$CREDENTIAL_DIR/application.env"
readonly DATABASE_ENV_FILE="$CREDENTIAL_DIR/database.env"
readonly GIT_DEPLOY_KEY_FILE="$CREDENTIAL_DIR/git-deploy-key"
readonly GHCR_TOKEN_FILE="$CREDENTIAL_DIR/ghcr-token"
readonly KNOWN_HOSTS_FILE="${CER_GIT_KNOWN_HOSTS:-${HOME:?}/.ssh/known_hosts}"

fail() {
  echo "$*" >&2
  exit 1
}

[[ -n "$CREDENTIAL_DIR" ]] || fail "CREDENTIALS_DIRECTORY is not set. Run the watcher through systemd."
[[ -n "$GHCR_USERNAME" ]] || fail "CER_GHCR_USERNAME is required."
[[ -r "$APPLICATION_ENV_FILE" ]] || fail "Missing application.env systemd credential."
[[ -r "$DATABASE_ENV_FILE" ]] || fail "Missing database.env systemd credential."
[[ -r "$GIT_DEPLOY_KEY_FILE" ]] || fail "Missing git-deploy-key systemd credential."
[[ -r "$GHCR_TOKEN_FILE" ]] || fail "Missing ghcr-token systemd credential."
[[ -r "$KNOWN_HOSTS_FILE" ]] || fail "Missing SSH known_hosts file: $KNOWN_HOSTS_FILE"

mkdir -p "$STATE_DIR" "$RELEASES_DIR" "$IO_DIR"
exec 9>"$STATE_DIR/deploy.lock"
if ! flock -n 9; then
  echo "Another CER production deployment is already running."
  exit 0
fi

docker_config=""
candidate_dir=""
extract_container=""

cleanup() {
  if [[ -n "$extract_container" ]]; then
    docker rm -f "$extract_container" >/dev/null 2>&1 || true
  fi
  if [[ -n "$candidate_dir" && "$candidate_dir" == "$STATE_DIR"/candidate.* ]]; then
    rm -rf -- "$candidate_dir"
  fi
  if [[ -n "$docker_config" && "$docker_config" == "$STATE_DIR"/docker-config.* ]]; then
    rm -rf -- "$docker_config"
  fi
}
trap cleanup EXIT

export GIT_SSH_COMMAND="ssh -i $GIT_DEPLOY_KEY_FILE -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$KNOWN_HOSTS_FILE"

target_revision="$({
  git ls-remote --exit-code "$REPOSITORY" "refs/heads/$BRANCH"
} | awk 'NR == 1 { print $1 }')"

[[ "$target_revision" =~ ^[0-9a-f]{40}$ ]] || fail "Origin returned an invalid production revision."

deployed_revision=""
if [[ -f "$DEPLOYED_REVISION_FILE" ]]; then
  deployed_revision="$(<"$DEPLOYED_REVISION_FILE")"
fi

if [[ "$deployed_revision" == "$target_revision" ]]; then
  echo "CER production is already deployed at $target_revision."
  exit 0
fi

readonly image_tag="$IMAGE_REPOSITORY:$target_revision"
docker_config="$(mktemp -d "$STATE_DIR/docker-config.XXXXXX")"

echo "Authenticating to GitHub Container Registry..."
docker --config "$docker_config" login ghcr.io \
  --username "$GHCR_USERNAME" \
  --password-stdin <"$GHCR_TOKEN_FILE" >/dev/null

echo "Pulling production image for origin/$BRANCH at $target_revision..."
docker --config "$docker_config" pull "$image_tag"

image_ref="$(
  docker image inspect \
    --format '{{ range .RepoDigests }}{{ println . }}{{ end }}' \
    "$image_tag" \
    | awk -v prefix="$IMAGE_REPOSITORY@sha256:" 'index($0, prefix) == 1 { print; exit }'
)"
[[ "$image_ref" == "$IMAGE_REPOSITORY@sha256:"* ]] || fail "Could not resolve the production image digest."

image_revision="$(
  docker image inspect \
    --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
    "$image_ref"
)"
[[ "$image_revision" == "$target_revision" ]] || fail "Image revision label does not match origin/$BRANCH."

release_dir="$RELEASES_DIR/$target_revision"
if [[ ! -d "$release_dir" ]]; then
  candidate_dir="$(mktemp -d "$STATE_DIR/candidate.XXXXXX")"
  extract_container="$(docker create "$image_ref")"
  docker cp "$extract_container:/app/docker/." "$candidate_dir/"
  docker rm "$extract_container" >/dev/null
  extract_container=""
  mv "$candidate_dir" "$release_dir"
  candidate_dir=""
fi

[[ -f "$release_dir/compose.yaml" ]] || fail "Production image does not contain docker/compose.yaml."
[[ -f "$release_dir/envs/base.env" ]] || fail "Production image does not contain docker/envs/base.env."
[[ -f "$release_dir/envs/prod.env" ]] || fail "Production image does not contain docker/envs/prod.env."

export CER_IMAGE_REF="$image_ref"
export CER_APPLICATION_ENV_FILE="$APPLICATION_ENV_FILE"
export CER_DATABASE_ENV_FILE="$DATABASE_ENV_FILE"
export CER_IO_DIR="$IO_DIR"

readonly -a COMPOSE=(
  docker --config "$docker_config" compose
  --project-directory "$release_dir"
  -p prod
  -f "$release_dir/compose.yaml"
)

echo "Deploying CER production revision $target_revision..."
"${COMPOSE[@]}" config --quiet
"${COMPOSE[@]}" pull db
"${COMPOSE[@]}" up -d db
"${COMPOSE[@]}" run --rm migrate
"${COMPOSE[@]}" up -d --no-build backend worker

healthy=false
for _ in {1..30}; do
  if curl --fail --silent --show-error --output /dev/null \
    http://127.0.0.1:18000/admin/login/; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != true ]]; then
  fail "Deployment did not pass the local HTTP health check."
fi

if [[ "$(docker inspect --format '{{.State.Running}}' cer-prod-worker)" != true ]]; then
  fail "Deployment failed: cer-prod-worker is not running."
fi

revision_tmp="$DEPLOYED_REVISION_FILE.tmp"
printf '%s\n' "$target_revision" >"$revision_tmp"
mv "$revision_tmp" "$DEPLOYED_REVISION_FILE"
ln -sfn "$release_dir" "$STATE_DIR/current"
echo "CER production deployed successfully at $target_revision."
