# Instruções para o Claude Code — baixador-ytdlp

App Windows em Python (PySide6) que junta download via yt-dlp/FFmpeg/Deno,
transcrição local com faster-whisper (CTranslate2) e ferramentas de vídeo.

## Trabalho em andamento

Siga `docs/PLANO-DE-CORRECOES.md`: auditoria completa da v1.10.10 com status de
cada item. As rodadas 1 e 2 e a parte funcional da 3 estão feitas na versão
candidata 1.12.0. A validação e a publicação estão em `PENDENCIAS.md`.

## Decisões do mantenedor (não reabrir)

- Base continua em Python; não migrar para outra linguagem.
- Sem assinatura Authenticode (não quer gastar com o projeto). Ed25519 das
  releases é gratuita e está no plano (A8).
- GitHub Actions voltou a executar em 28/09/2026: o workflow compila as três
  plataformas e publica após passar. A build Windows local usa PyInstaller
  nesta rodada após falha do autoteste Nuitka.
- A verificação de dependências do legendador continua bloqueante antes de
  liberar a interface; só cache é aceito.
- Sugestões de funcionalidade são bem-vindas em revisões, sempre com a UI
  avaliada junto.

## Convenções

- Textos da interface, commits e comentários em português do Brasil. Commits no
  formato `fix: …` / `feat: …` / `chore: …`, com corpo explicando o porquê.
- Muitos arquivos misturam CRLF e LF. Edite preservando a quebra de linha do
  trecho; não normalize arquivos inteiros junto com mudanças de código (isso é
  o item H2, em commit próprio).
- CTranslate2 e pacotes NVIDIA sobem sempre juntos. `nvidia-cudnn-cu12` precisa
  ser a mesma versão do `cudnn64_9.dll` que vem no wheel Windows do CTranslate2.
  Ao mudar `requirements.txt`, regenere os locks com `scripts/update_locks.sh`
  (precisa de `uv`).
- Versão: altere `APP_VERSION` em `baixador_ytdlp/config.py` e rode
  `python scripts/sync_version.py`; registre no `CHANGELOG.md`.

## Testes

```
set QT_QPA_PLATFORM=offscreen
python -m unittest discover -s tests
ruff check .
```

Testes que instanciam `MainWindow` não podem gravar no perfil real: substitua
`cfg.save`, `queue.stop_all` e `history.flush` por mocks (ver
`tests/test_update_flow.py`). Cada correção vem com teste que falha no código
antigo.
