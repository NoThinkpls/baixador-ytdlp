#!/usr/bin/env bash
# Regenera os locks com hashes a partir dos requirements*.txt (entradas).
# O CI e o build.ps1 instalam SOMENTE os .lock, com --require-hashes: duas
# builds do mesmo commit recebem exatamente os mesmos pacotes, inclusive as
# dependências transitivas (av, onnxruntime, tokenizers, numpy, pywin32…).
set -euo pipefail
cd "$(dirname "$0")/.."
compile() { uv pip compile "$1" --generate-hashes --python-platform "$2" \
              --python-version 3.12 --no-header --quiet -o "$3"; }
compile requirements.txt        x86_64-pc-windows-msvc   requirements-windows.lock
compile requirements-macos.txt  aarch64-apple-darwin     requirements-macos.lock
compile requirements-linux.txt  x86_64-manylinux_2_28    requirements-linux.lock
compile requirements-build.txt  x86_64-pc-windows-msvc   requirements-build-windows.lock
compile requirements-build.txt  aarch64-apple-darwin     requirements-build-macos.lock
compile requirements-build.txt  x86_64-manylinux_2_28    requirements-build-linux.lock
echo "Locks atualizados. Rode a suíte e confira o diff antes do commit."
