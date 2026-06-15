#!/usr/bin/env bash
# Build the preloaded run_bash verification sandbox image.
#
# Usage:   ./docker/build-verify-image.sh
# Result:  a local image tagged `agent-verify:latest` with python+node+pytest+common
#          deps baked in, so the agent's verify loop can run tests with the sandbox's
#          default --network none (no egress).
#
# After building, set in .env:
#     AGENT_BASH_DOCKER_IMAGE=agent-verify:latest
# and remove AGENT_DISABLE_BASH=1, then restart the service.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAG="${AGENT_VERIFY_IMAGE_TAG:-agent-verify:latest}"

echo "Building $TAG from ${HERE}/verify.Dockerfile ..."
docker build -f "${HERE}/verify.Dockerfile" -t "$TAG" "${HERE}"

echo
echo "Done. Set in .env:  AGENT_BASH_DOCKER_IMAGE=${TAG}"
echo "Then restart the service so run_bash uses the preloaded image."
