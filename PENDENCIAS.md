# Pendências

Estado em 30/09/2026: versão **1.13.1** publicada (1.13.2 em preparo); aqui ficam só as pendências. O Windows
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

## Outros sites além do YouTube

O yt-dlp tem extrator para Instagram, X, TikTok, Facebook, Reddit, Vimeo, Twitch, Kick e outros;
o app já os aceita, e desde a 1.13.2 os avisos de erro citam o site certo (`sites.py`). Falta
validar na prática, com cookies quando o site pedir, um link de cada: Instagram (reel e story),
X, TikTok, Facebook, Reddit e Vimeo.

Trecho em partes paralelas: funciona só no YouTube (`baixador_ytdlp/parallel_section.py`).
Para os outros sites e para o áudio (`-x`) é preciso medir antes se o teto por conexão também
é baixo; sem medição, fica como está.

## Melhorias por plataforma

Feitos: QSV/VAAPI, decodificação por hardware e, na 1.13.2, o diagnóstico de permissão do VAAPI.
Restam, em `docs/PLANO-OTIMIZACAO-PLATAFORMAS.md`: P4 (vários cortes em paralelo), P5 (Whisper
com Vulkan para AMD/Intel) e o resto do P6 (VideoToolbox com `-allow_sw 0`, GPU dedicada em
notebook híbrido no Windows).

## Arquivos grandes

`tools.py` (1.076), `ui/home_page.py` (1.173) e `ui/main_window.py`
(1.069) são cada um uma classe só: dividir exige mixins e mexe nos pontos de patch dos testes
(`baixador_ytdlp.tools.IS_WINDOWS`, `...tools.urllib...`), então fica para uma rodada própria,
começando por `ToolManager` (yt-dlp / FFmpeg / Deno em módulos separados).

## Pacotes atualizados à mão

Atualizados na 1.13.2: PySide6, faster-whisper, huggingface-hub (0.36.2), certifi, send2trash e
setuptools; a suíte passa com o lock do Linux. Ficaram de fora:

- huggingface-hub 1.x/2.x: muda a API de cache usada em `models.py`.
- torch, mlx e mlx-metal (só macOS, transitivos do mlx-whisper): sem Mac para testar.
- Falta rodar o autoteste com GPU e abrir o app no Windows com o PySide6 6.11.

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
