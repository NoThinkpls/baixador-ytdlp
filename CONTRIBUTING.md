# Como contribuir

Use Python 3.12. Crie um ambiente virtual e instale as dependências da sua
plataforma junto de `requirements-build.txt`. No Linux:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-linux.lock -r requirements-build-linux.lock
```

Antes de abrir um pull request, execute:

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python scripts/sync_version.py   # após mudar APP_VERSION
```

## Dependências

Os `requirements*.txt` são as **entradas**; o CI instala somente os `.lock`,
com hashes. Ao mudar uma versão, rode `scripts/update_locks.sh` (requer `uv`) e
commite os locks junto — o job `locks-in-sync` falha se eles divergirem.
CTranslate2 e os pacotes NVIDIA sobem sempre juntos (cuDNN 8 ↔ CTranslate2 4.4).

## Assinatura das releases

1. `python scripts/release_signing.py generate` — gera o par Ed25519.
2. Guarde a chave privada no segredo `RELEASE_SIGNING_KEY` do *environment*
   `release` (Settings → Environments), com **Required reviewers**.
3. Cole a chave pública em `RELEASE_PUBLIC_KEYS` (`baixador_ytdlp/updater.py`).
   A partir da versão que trouxer a chave, o atualizador recusa releases sem
   `SHA256SUMS.txt.sig` válido — publique antes uma versão já assinada.

Não inclua cookies, tokens, proxies com credenciais, logs pessoais ou modelos
Whisper no commit. Para vulnerabilidades, não abra issue pública: siga o
[SECURITY.md](SECURITY.md).

Commits seguem Conventional Commits (`fix:`, `feat:`, `docs:`, `test:`). Uma
release é criada somente por uma tag `vX.Y.Z` que corresponda a `APP_VERSION`.
