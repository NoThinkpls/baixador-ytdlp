# Como contribuir

Obrigado por melhorar o Baixador YT-DLP. Buscamos mudanças pequenas, testáveis e
compatíveis com Windows, macOS e Linux.

## Antes de começar

- Consulte as [issues abertas](../../issues) antes de iniciar uma funcionalidade.
- Nunca inclua cookies, tokens, proxies com credenciais, links privados, modelos
  Whisper ou logs pessoais no repositório.
- Para vulnerabilidades, use o fluxo privado descrito em [SECURITY.md](SECURITY.md).

## Preparar o ambiente

Use Python 3.12. Os arquivos `requirements*.txt` descrevem as dependências; os
arquivos `.lock` com hashes são a fonte de instalação reproduzível do CI.

No Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-windows.lock -r requirements-build.lock
```

No Linux:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-linux.lock -r requirements-build-linux.lock
```

No macOS Apple Silicon, use os locks equivalentes `requirements-macos.lock` e
`requirements-build-macos.lock`.

## Validar uma mudança

Antes de abrir um pull request, execute:

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

No PowerShell, defina `QT_QPA_PLATFORM=offscreen` antes do comando de testes.
Quando mudar `APP_VERSION`, execute também `python scripts/sync_version.py`.

Inclua testes para correções e funcionalidades novas. Se a alteração tocar
empacotamento, caminhos, recursos ou subprocessos, descreva o impacto em cada
plataforma no PR.

## Dependências e releases

Depois de editar requirements, rode `scripts/update_locks.sh` (requer `uv`) e
commite os locks gerados. O job `locks-in-sync` recusa divergências. Atualizações
de CTranslate2 e CUDA/cuDNN devem ser planejadas em conjunto.

Releases oficiais saem do GitHub Actions após a validação dos três sistemas.
Consulte [Compilação e releases](docs/COMPILACAO-E-RELEASE.md); não crie tags ou
releases manualmente no fluxo normal.

## Padrões de colaboração

- Use commits no formato Conventional Commits, como `fix:`, `feat:`, `docs:` e
  `test:`.
- Mantenha cada PR focado em um problema.
- Explique o comportamento anterior, o novo comportamento e como ele foi
  validado.
- Atualize a documentação visível ao usuário sempre que a experiência mudar.

O [modelo de pull request](.github/PULL_REQUEST_TEMPLATE.md) reúne esse
checklist ao abrir uma contribuição.
