#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"
source_dir="${project_dir}/agentrun-agent"
output_path="${1:-${project_dir}/dist/agentrun-agent-python310-linux-amd64.zip}"
# Agent Run's Python 3.10 runtime is Debian 10 / GLIBC 2.28. Do not use the
# moving python:3.10-slim tag: newer Debian images can install native wheels
# that fail to load in Agent Run (for example cryptography requiring GLIBC
# 2.30+).
docker_image="${AGENTRUN_BUILD_IMAGE:-python:3.10-slim-buster}"
fallback_image="public.ecr.aws/docker/library/python:3.10-slim-buster"

if ! command -v docker >/dev/null 2>&1; then
  echo "需要先安装并启动 Docker Desktop。" >&2
  exit 1
fi
if ! command -v zip >/dev/null 2>&1; then
  echo "缺少 zip 命令。" >&2
  exit 1
fi

staging_dir="$(mktemp -d)"
cleanup() {
  rm -rf "${staging_dir}"
}
trap cleanup EXIT

cp "${source_dir}/main.py" "${staging_dir}/main.py"
cp "${source_dir}/system_prompt.py" "${staging_dir}/system_prompt.py"
cp "${source_dir}/requirements.txt" "${staging_dir}/requirements.txt"

if ! docker image inspect "${docker_image}" >/dev/null 2>&1; then
  echo "正在拉取构建镜像：${docker_image}"
  if ! docker pull --platform linux/amd64 "${docker_image}"; then
    echo "Docker Hub 拉取失败，尝试公共备用镜像：${fallback_image}" >&2
    docker pull --platform linux/amd64 "${fallback_image}"
    docker_image="${fallback_image}"
  fi
fi

docker run --rm --platform linux/amd64 \
  -v "${staging_dir}:/package" \
  "${docker_image}" \
  python -m pip install --no-cache-dir -r /package/requirements.txt -t /package/python

# Import native dependencies in the same Debian 10 / GLIBC 2.28 environment
# before creating the ZIP. This catches ABI-incompatible wheels locally.
docker run --rm --platform linux/amd64 \
  -v "${staging_dir}:/package:ro" \
  -e PYTHONPATH=/package/python \
  "${docker_image}" \
  python -c 'import agentrun, cryptography, langchain, langchain_openai; print("Agent Run dependency imports passed")'

mkdir -p "$(dirname "${output_path}")"
(cd "${staging_dir}" && zip -q -r "${output_path}" . \
  -x '*/__pycache__/*' '*.pyc' '.DS_Store')

echo "已生成：${output_path}"
echo "控制台运行时请选择 Python 3.10，启动命令使用 python3 main.py，端口使用 9000。"
