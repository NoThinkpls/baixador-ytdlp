# Pendências

Estado em 30/09/2026: versão **1.13.0** (candidata; 1.12.8 é a última publicada). As rodadas 1 a 3 do
`docs/PLANO-DE-CORRECOES.md` estão feitas e publicadas (1.12.0 a 1.12.8). O
Windows compila com Nuitka; o PyInstaller é só contingência. O GitHub Actions
compila as três plataformas e publica a release quando todas passam.

Contexto: `docs/PLANO-DE-CORRECOES.md` (auditoria e status), `CLAUDE.md`
(decisões e convenções) e `docs/PLANO-OTIMIZACAO-PLATAFORMAS.md` (próximas melhorias).

## Retomada: release 1.13.0 (ferramentas novas de mídia)

Branch `ccr-38f697c6-lvvgdq` (2 commits à frente de `main`): nove ferramentas novas na aba
Ferramentas + formatos de áudio extras, versão 1.13.0 e docs. Suíte, ruff e testes com FFmpeg real
passam (o único erro no container da nuvem era o pacote `cryptography` do sistema). Build de teste
disparado em `workflow_dispatch` (run 36650656293; não publica, só `main` e tags `v*` publicam).

A fazer, nesta ordem:

1. Conferir o resultado do run 36650656293 (Windows/Nuitka, macOS, Linux e o teste de janela real).
   Se algo falhar, corrigir na branch.
2. No Windows: `python scripts/capture_screenshots.py` e commitar as imagens novas de
   `docs/images/` (a `ferramentas-*.png` mudou; o README as usa). Olhar as capturas antes de commitar.
3. Rodar no Windows `python -m unittest discover -s tests`, `ruff check .` e
   `python scripts/pyright_check.py` (o pyright não rodou na nuvem).
4. Só com o build verde e as imagens no lugar, e com a confirmação do mantenedor: abrir o PR para
   `main`, mesclar e criar a tag `v1.13.0` (isso publica a release para todos).

Detalhes que valem lembrar: o codec das ferramentas de áudio/imagem/legenda/conversão vem da
extensão do destino; ferramentas são dados em `OPERATIONS`/`GROUPS`/`CHOICES`
(`ui/media_tools_page.py`, `media_tools.py`); um teste falha se faltar tradução em inglês.

## Validação manual (só na máquina com NVIDIA)

- [ ] Transcrever um vídeo curto e conferir no log "Modelo pronto: CUDA" e o
      processo no `nvidia-smi`.
- [ ] Baixar um trecho longo de uma live do YouTube e conferir o tempo (esperado:
      bem abaixo do tempo real) e o formato escolhido.
- [ ] Atualizar pelo app de uma versão anterior: só a janela de progresso do
      instalador e o app reabrindo sozinho.
- [ ] Testar a exclusão de `cudnn_adv64_9.dll` (282 MB, não usado pelo Whisper)
      para reduzir o instalador.
- [ ] Abrir o pacote Nuitka em máquina limpa sem Python nem VC++ instalado (o
      `scripts/refresh_vc_runtime.ps1` embute o runtime C++ mais novo).

## Trecho em partes paralelas (feito na 1.12.4)

82 min de live em ~2,5 min (`baixador_ytdlp/parallel_section.py`). O downloader nativo
do yt-dlp ignora `--concurrent-fragments` com `--download-sections` (sempre usa o
FFmpeg), então o ganho vem de várias conexões. Pendente: aplicar o mesmo a sites que
não sejam o YouTube e ao áudio (`-x`), se o teto por conexão também for baixo lá.

## Melhorias por plataforma

Ordem sugerida em `docs/PLANO-OTIMIZACAO-PLATAFORMAS.md`: QSV e VAAPI, decodificação
por hardware, paralelismo de cortes, Whisper com Vulkan para AMD/Intel.

## Arquivos grandes

`transcription.py` caiu de 1.281 para ~870 linhas (pesos e cache em `models.py`, processos em
`transcription_server.py`). `tools.py` (1.076), `ui/home_page.py` (1.173) e `ui/main_window.py`
(1.069) são cada um uma classe só: dividir exige mixins e mexe nos pontos de patch dos testes
(`baixador_ytdlp.tools.IS_WINDOWS`, `...tools.urllib...`), então fica para uma rodada própria,
começando por `ToolManager` (yt-dlp / FFmpeg / Deno em módulos separados).

## PRs do Dependabot em espera

- (vazio) Os PRs #26 e #27 foram mesclados e entram na 1.12.8; se a publicação falhar por causa
  deles, reverter os dois commits.
- torch, huggingface-hub, setuptools, send2trash, PySide6, faster-whisper e MLX são atualizados
  à mão (o Dependabot não os propõe mais): regenerar os `.lock` com `scripts/update_locks.sh` e
  passar o autoteste com GPU.

## Publicação

O fluxo normal é `git push` na `main`: o Actions valida Windows, macOS e Linux e
publica `vX.Y.Z`. Assinatura Ed25519 (opcional): `python scripts\release_signing.py
generate`, colar a chave pública em `RELEASE_PUBLIC_KEYS`
(`baixador_ytdlp/updater.py`) e publicar; perder a chave privada obriga todos a
atualizar manualmente. Se o Actions estiver indisponível: `.\build.ps1
-ValidateGpu`, depois `python scripts\prepare_release.py --publish`.

## Observações

- O instalador é grande por causa do cuDNN 9 (ver o teste de exclusão acima).
- Os commits são feitos com o autor "Nathan Ferraz", como no histórico.
