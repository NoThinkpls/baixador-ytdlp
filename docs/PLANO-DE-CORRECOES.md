# Plano de correções — auditoria da v1.10.10

Auditoria feita em 28/09/2026 sobre o commit `1704090` (v1.10.10): leitura do
código, testes, ruff e renderização offscreen de todas as páginas (temas claro e
escuro, 1160×780 e 800×600). Este arquivo é a fonte de verdade do que falta:
marque cada item ao concluir e registre o commit.

Prioridade: **C** crítico · **A** alto · **M** médio · **U** UI/UX · **F** função
nova · **H** manutenção.

## Rodada 1 — concluída (v1.10.11, ainda não publicada)

| Item | Commit | Resumo |
|---|---|---|
| C1 | `c74646a` | CTranslate2 4.8.2 exige cuDNN 9; a build embutia cuDNN 8 e a transcrição caía para CPU. Fixado `nvidia-cudnn-cu12==9.10.2.21` (mesma versão do `cudnn64_9.dll` dentro do wheel do CT2), cuBLAS/cudart 12.8. Runtime exige a variante certa; autoteste carrega o cuDNN e cria handle com GPU; `tests/test_cuda_stack.py`. |
| C3 | `422c84d` | Download usa a URL analisada (`_analyzed_url`); editar o link invalida a análise; resultado atrasado de outro link é ignorado. `tests/test_home_analysis.py`. |
| A1, A2 | `a95e898` | `max_duration` vale no caminho por palavra; `_normalize_text` preserva `% $ / & @ # +` e aspas. `tests/test_subtitle_shaping.py`. |
| A3 | `f68811b` | `friendly_error`: idade antes de robô, região e HTTP 5xx antes de "removido". `tests/test_friendly_errors.py`. |
| C2 | `58f2977` | Atualização pergunta com tarefas ativas (instalar ao fechar / agora), fecha pelo `closeEvent` salvando tudo e só então abre o instalador; não fica presa na bandeja; fechar avisa sobre legendas/ferramentas; limpa instaladores antigos. `tests/test_update_flow.py`. |
| H1 | `5112d8c` | Versão 1.10.11 e CHANGELOG de 1.10.9 a 1.10.11. |

### Validação pendente (só na máquina do Nathan, com NVIDIA)

- [ ] `build.ps1` passa, incluindo o autoteste com `cudnn_smoke`.
- [ ] Transcrição real: log com "Modelo pronto: CUDA" e processo no `nvidia-smi`.
- [ ] Testar remover `cudnn_adv64_9.dll` (282 MB, não usado pelo Whisper) para
      reduzir o instalador. Só depois de o item acima passar.

## Rodada 2 — próxima

- [ ] **A4** `workers.DownloadWorker`: falha no transcode depois de download bem
      sucedido marca o job como erro. Deve concluir com aviso e manter o original.
- [ ] **A5** `transcription.transcription_server_main`: `active_job` é definido
      antes de limpar `cancel_event` (cancelamento perdido). Inverter a ordem.
      `PersistentTranscriptionWorker` não drena eventos após o processo sair.
- [ ] **A6** `main_window._shortcut_cancel`: Esc cancela transcrição e
      ferramenta sem confirmar. Confirmar como a Fila faz.
- [ ] **A7** Banner de atualização: "Agora não" grava `update_dismissed_version`
      e pula a versão para sempre → separar "Lembrar depois" / "Pular esta
      versão"; mostrar tamanho e notas (`body` da release, hoje ignorado em
      `ReleaseInfo`); nova checagem periódica com o app aberto na bandeja.
- [ ] **A8** Ativar assinatura Ed25519 do `SHA256SUMS` (`RELEASE_PUBLIC_KEYS`
      vazio hoje). Gratuita; `scripts/release_signing.py` já existe; assinar no
      build local.
- [ ] **U1** Toasts empilham no topo central e cobrem cabeçalho/link/Analisar.
      Agrupar ("3 downloads falharam"), mover para baixo à direita, limitar.
- [ ] **U2** Em 800 px o campo de link vira "Cole o lin…". Link em largura total;
      botões quebram de linha ou viram ícone.
- [ ] **U3** Página Baixar: "Saída" domina antes da análise. Ordem: link → card
      da mídia + qualidade → saída recolhida. Linhas dependentes desabilitadas
      (Formato do áudio, Incorporar legenda) devem sumir ou explicar a dependência.
- [ ] **U4** Fila: mais novo no topo mas processamento FIFO; concluídos/falhos não
      saem um a um; barra vazia no erro; "Limpar concluídos" visível com fila
      vazia; faltam "Pausar tudo" e "Tentar de novo as falhas"; card sem tipo,
      formato e destino.
- [ ] **U6** Instalador abre o assistente completo; avaliar `/SILENT` com
      progresso e reabertura automática.

## Rodada 3

- [ ] **M1** `yt-dlp.exe` é PyInstaller onefile (descompacta a cada chamada; a
      análise chama 2–3 vezes). Avaliar a build onedir oficial para Windows
      (confirmar nome do asset no release e presença no `SHA2-256SUMS`).
- [ ] **M2** `tools.ensure_ffmpeg` extrai `ffplay.exe` sem uso. Avaliar os
      builds yt-dlp/FFmpeg-Builds (confirmar checksums publicados).
- [ ] **M3** `probe._resolve_cookies` faz um `--simulate` extra antes do `-J`;
      playlist faz `-J` + contagem + seletor. Rodar `-J` com cookies e só repetir
      sem eles se a fonte falhar; cachear o `--flat-playlist`.
- [ ] **M4** `MediaToolWorker` → `select_section_encoder` → `detect(verify=True)`
      testa até 6 encoders por operação, sem cache de negativos.
- [ ] **M5** Modelo Whisper fica na VRAM indefinidamente. Descarregar após
      inatividade (~10 min) + botão "Liberar memória da GPU".
- [ ] **M6** Estimativa de disco: playlist usa só o 1º item; linha só-vídeo não
      soma o áudio.
- [ ] **M7** `downloader._RETRYABLE_FAILURES`: "tls"/"ssl" soltos casam demais.
- [ ] **M8** Progresso de trecho: sem fim → duração 0 (usar duração da mídia);
      `bv*+ba` roda duas passadas e a barra reinicia.
- [ ] **U5** Configurações: "Até 1 downloads" (plural); ícone de sliders repetido
      em Rede, Avançado e duas ferramentas; dois botões "Verificar" → unificar com
      hora da última checagem; trocar canal do yt-dlp abre setup modal na hora;
      card de Componentes deve mostrar o estado real do Whisper (CUDA ok / CPU
      porque…).
- [ ] **U7** Ferramentas: 7 cards ocupam a primeira tela; arquivo abaixo da dobra;
      botão "Recortar" sem arquivo. Lista à esquerda + formulário à direita.
- [ ] **U8** i18n: ~104 `tr()`; erros, toasts, status e `friendly_error` só em
      pt-BR.
- [ ] **U9** Legendar aceita só o 1º arquivo arrastado; fila pendente invisível.
- [ ] **F1** Corte rápido sem reencodar (stream copy) ao lado do preciso.
- [ ] **F2** Legendar em lote (vários arquivos/pasta), lista editável.
- [ ] **F3** Pausar/retomar por item e fila inteira.
- [ ] **F4** Trecho por capítulo (capítulos já vêm no `-J`).
- [ ] **F5** Perfil "Baixar + legendar + incorporar".
- [ ] **H2** CRLF e LF misturados no mesmo arquivo (`config.py`, `workers.py`,
      `transcription.py`, `main_window.py`…). Adicionar `.gitattributes` e
      normalizar num commit separado, só de quebras de linha.

## Uso de GPU por etapa (decisão)

| Etapa | Onde |
|---|---|
| Download, junção, remux | CPU (rede é o gargalo) |
| Trecho no download | CPU (decisão da 1.10.10 mantida) |
| Whisper | GPU CUDA fp16; sugerir `large-v3-turbo` como padrão em NVIDIA |
| Converter após baixar | GPU, `hevc_nvenc` como padrão |
| Shorts, legenda gravada | GPU (filtros na CPU, codificação no NVENC) |
| Reduzir tamanho | Evitar H.264 NVENC (arquivo maior no mesmo CQ); x264 CPU ou `hevc_nvenc` |
| Caber em um limite | CPU x264 em duas passadas |
| Extração de áudio, VAD | CPU |
