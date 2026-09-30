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

Validado em 30/09/2026 na 1.13.2 (RTX 4060, driver 616.92, lock do Windows, PySide6 6.11.2,
faster-whisper 1.2.1, huggingface-hub 0.36.2, CTranslate2 4.8.2, cuDNN 9.10.2):

- [x] Transcrever um vídeo curto: log "Modelo pronto: CUDA", 2,1 s para 19 s de áudio (modelo
      `small`), VRAM 1654 -> 2426 MiB e o processo Python listado no `nvidia-smi`. O autoteste com
      GPU (`BAIXADOR_YTDLP_VALIDATE_GPU=1 python main.py`, o mesmo do `build.ps1 -ValidateGpu`,
      sem compilar) também passou (`cudnn_version` 91002).
- [x] Trecho longo de uma live do YouTube (30 min, 1080p H.264 + AAC, MP4): 74-83 s em partes
      paralelas, **65-66 s em um processo só**. Nesta rede uma conexão já chega a ~20 MB/s, então
      as partes paralelas não ajudam (ver "Outros sites"). Duração final exata (1800,01 s).
- [ ] Atualizar pelo app de uma versão anterior: só a janela de progresso do
      instalador e o app reabrindo sozinho.
- [x] Exclusão de `cudnn_adv64_9.dll` (282 MB, não usado pelo Whisper): sem ela o Whisper com CUDA
      (`small`) e o autoteste com GPU continuam passando. Testado só com `small` e sem o modo em
      lote; o empacotamento não foi alterado.
- [ ] Abrir o pacote Nuitka em máquina limpa sem Python nem VC++ instalado (o
      `scripts/refresh_vc_runtime.ps1` embute o runtime C++ mais novo).
- [ ] QSV/AMF e conversão pós-download: sem hardware Intel/AMD disponível (só NVIDIA).

## Outros sites além do YouTube

O yt-dlp tem extrator para Instagram, X, TikTok, Facebook, Reddit, Vimeo, Twitch, Kick e outros;
o app já os aceita, e desde a 1.13.2 os avisos de erro citam o site certo (`sites.py`).

Validado em 30/09/2026 (yt-dlp 2026.08.19, Deno 2.9.7, `probe()` + `DownloadRunner` do app):

| Site | Sem login | Resultado |
| --- | --- | --- |
| X | sim | MP4 H.264 640p; o vídeo do teste é mudo na origem (nenhum formato tem áudio) |
| TikTok | sim | MP4 HEVC 1080p + AAC (o mais alto da lista é H.265; ver `prefer_h264`) |
| SoundCloud | sim (link curto `on.soundcloud.com`) | MP3 128 kbps |
| Twitch (VOD, 30 min) | sim | MP4 H.264 1080p + AAC, 15x o tempo real em uma conexão |
| Vimeo | não | aviso correto: "Vimeo pediu login…". Com o cookies.txt indicado seguiu igual, porque ele só tem 1 cookie de vimeo.com (sem sessão logada) |
| Instagram (reel) | sim | MP4 VP9 640x640 + AAC |
| Facebook (`/share/r/`) | sim | MP4 AV1 1152x2048 + AAC |
| Reddit (post e `packaged-media.redd.it`) | sim | MP4 H.264 360x640 + AAC pelo post; 270x480 + AAC pelo link direto (título e nome de arquivo ruins, veja abaixo) |
| Instagram story | não (exige login) | corrigido em 30/09/2026: sem cookies o app avisa na hora; com cookies baixa pela linha da tabela (MP4 com áudio) |

Bug do story (corrigido): a URL do story é uma playlist de todos os stories da pessoa; a análise mostrava os formatos do item 1 e o download baixava o do link. A análise agora usa `--no-playlist` nesse caso (`sites.is_single_story`).

Achados menores: o link direto `packaged-media.redd.it` gera o arquivo `m2-res_480p [m2-res_480p.mp4？m=DASHPlaylist].mp4` (título vazio e a query entra no id); no Facebook o título do post inteiro vira nome de arquivo (`122K views · 3.4K reactions ｜ …`).

Trecho em partes paralelas: funciona só no YouTube (`baixador_ytdlp/parallel_section.py`).
Medição em 30/09/2026 (mesma live de 30 min, 1080p): YouTube 74-83 s em partes paralelas contra
65-66 s em um processo, ou seja, o paralelo não compensa quando a rede já é o limite (~20 MB/s
aqui). Em HLS de outro site (Twitch, mesmo trecho de 30 min) uma conexão fez 120 s (~11,5 MB/s) e
três partes simultâneas fizeram ~65 s (1,85x), de novo no teto da rede. Conclusão: o teto por
conexão de ~5 MB/s medido na nuvem não se repete aqui no YouTube; em HLS de outros sites existe e
o paralelo ajuda. Decidir entre limitar as partes paralelas a redes lentas, estendê-las a HLS
não-YouTube ou deixar como está.

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
- O autoteste com GPU e a abertura do app no Windows com o PySide6 6.11.2 foram validados em 30/09/2026.

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
