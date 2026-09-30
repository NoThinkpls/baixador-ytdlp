# Pendências

Estado em 30/09/2026: versão **1.13.1** publicada; aqui ficam só as pendências. O Windows
compila com Nuitka; o PyInstaller é só contingência. O GitHub Actions compila as três plataformas
e publica a release quando todas passam.

Contexto: `docs/PLANO-DE-CORRECOES.md` (auditoria e status), `CLAUDE.md`
(decisões e convenções) e `docs/PLANO-OTIMIZACAO-PLATAFORMAS.md` (próximas melhorias).

## Assinatura Ed25519 das releases

A 1.13.1 saiu sem `.sig`: `RELEASE_SIGNING_KEY` não está configurado e `RELEASE_PUBLIC_KEYS`
está vazia. Passos em "Publicação" abaixo.

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

## Trecho em partes paralelas

Já funciona no YouTube (`baixador_ytdlp/parallel_section.py`). Pendente: aplicar o mesmo a sites
que não sejam o YouTube e ao áudio (`-x`), se o teto por conexão também for baixo lá.

## Melhorias por plataforma

Ordem sugerida em `docs/PLANO-OTIMIZACAO-PLATAFORMAS.md`: QSV e VAAPI, decodificação
por hardware, paralelismo de cortes, Whisper com Vulkan para AMD/Intel.

## Arquivos grandes

`tools.py` (1.076), `ui/home_page.py` (1.173) e `ui/main_window.py`
(1.069) são cada um uma classe só: dividir exige mixins e mexe nos pontos de patch dos testes
(`baixador_ytdlp.tools.IS_WINDOWS`, `...tools.urllib...`), então fica para uma rodada própria,
começando por `ToolManager` (yt-dlp / FFmpeg / Deno em módulos separados).

## PRs do Dependabot em espera

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
