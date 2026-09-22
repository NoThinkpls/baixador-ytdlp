# Como contribuir

Use Python 3.12. Crie um ambiente virtual e instale as dependências da sua
plataforma junto de `requirements-build.txt`. No Linux:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-linux.txt -r requirements-build.txt
```

Antes de abrir um pull request, execute:

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python scripts/sync_version.py --check
```

Não inclua cookies, tokens, proxies com credenciais, logs pessoais ou modelos
Whisper no commit. Para vulnerabilidades, não abra issue pública: siga o
[SECURITY.md](SECURITY.md).

Commits seguem Conventional Commits (`fix:`, `feat:`, `docs:`, `test:`). Uma
release é criada somente por uma tag `vX.Y.Z` que corresponda a `APP_VERSION`.
