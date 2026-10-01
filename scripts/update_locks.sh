#!/usr/bin/env bash
# Regenera os locks com hashes a partir dos requirements*.txt (entradas).
# O CI e o build.ps1 instalam SOMENTE os .lock, com --require-hashes: duas
# builds do mesmo commit recebem exatamente os mesmos pacotes, inclusive as
# dependências transitivas (av, onnxruntime, tokenizers, numpy, pywin32…).
set -euo pipefail
cd "$(dirname "$0")/.."
# O mlx só publica wheels a partir do macOS 14; sem isso o uv resolve para o macOS 13.
export MACOSX_DEPLOYMENT_TARGET=14.0
compile() { uv pip compile "$1" --generate-hashes --python-platform "$2" \
              --python-version 3.12 --no-header --quiet -o "$3"; }
compile requirements.txt        x86_64-pc-windows-msvc   requirements/requirements-windows.lock
compile requirements/requirements-macos.txt  aarch64-apple-darwin     requirements/requirements-macos.lock
compile requirements/requirements-linux.txt  x86_64-manylinux_2_34    requirements/requirements-linux.lock
compile requirements/requirements-build.txt  x86_64-pc-windows-msvc   requirements/requirements-build-windows.lock
compile requirements/requirements-build.txt  aarch64-apple-darwin     requirements/requirements-build-macos.lock
compile requirements/requirements-build.txt  x86_64-manylinux_2_28    requirements/requirements-build-linux.lock
echo "Locks atualizados. Rode a suíte e confira o diff antes do commit."
