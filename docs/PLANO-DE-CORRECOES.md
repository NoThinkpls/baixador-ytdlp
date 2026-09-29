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

- [ ] `build.ps1 -Installer -ValidateGpu` passa com Nuitka, incluindo
      `cudnn_smoke` e o processo filho do VAD.
- [ ] Transcrição real: log com "Modelo pronto: CUDA" e processo no `nvidia-smi`.
- [ ] Testar remover `cudnn_adv64_9.dll` (282 MB, não usado pelo Whisper) para
      reduzir o instalador. Só depois de o item acima passar.

## Rodada 2 — concluída (também na v1.10.11)

| Item | Commit | Resumo |
|---|---|---|
| A4, U4 | `29b321a` | Conversão com falha conclui com aviso e mantém o original. Fila FIFO, tipo/formato/pasta no cartão, remover item finalizado, barra some no erro, "Limpar finalizados" só habilitado com o que limpar, "Tentar de novo as falhas". `tests/test_queue_actions.py`. |
| A5 | `32b07b5` | Trava única para troca de item e cancelar/pausar no servidor Whisper; worker drena eventos após o processo sair. `tests/test_transcription_server.py`. |
| A6 | `c94e9ee` | Esc pede confirmação em Legendar e Ferramentas. |
| A7 | `d7f02f6` | Banner com tamanho, Novidades, "Lembrar depois" x "Pular versão", checagem a cada 3 h, botões em 2ª linha quando estreito. |
| U2 | `7054caf` | Link em largura total abaixo de 900 px. |
| U1 | `8fe6f88` | Toasts agrupados com contador, canto inferior direito acima do rodapé e do banner, máx. 3. `tests/test_toasts.py`. |
| U3 | `21047fe` | Página Baixar esconde opções que não valem no modo atual. |
| U6 | `b7b044f` | Instalador com `/SILENT` (progresso visível) e reabertura via `[Run] Check: WizardSilent`. |
| A8 | `b4e64be` | `scripts/prepare_release.py` + chave privada em arquivo. |

### Pendências manuais da rodada 2

- [ ] A8: `python scripts\release_signing.py generate`, backup da chave, colar a
      pública em `RELEASE_PUBLIC_KEYS` e publicar essa versão.
- [ ] U6: conferir no Windows que a atualização pelo app mostra só o progresso
      e reabre o aplicativo (o `.iss` não foi compilado aqui).

## Rodada 3 — em andamento

### Concluído

| Item | Commit | Resumo |
|---|---|---|
| M6, M7, M8 | `de93b50` | Espaço soma áudio e itens da playlist; "ssl"/"tls" só como palavra; % em trecho sem fim e sem voltar a 0% na 2ª passada. `tests/test_download_estimates.py`. |
| M4 | `892f84a` | Cache de 10 min para "nenhum encoder de GPU funciona"; detecção manual sempre testa de novo. |
| M3 | `a3d75f6` | Análise sem `--simulate` extra de cookies; itens da playlist vêm da contagem. `tests/test_probe_calls.py`. |
| M5 | `3330aa9` | Whisper descarregado após 10 min ocioso + botão "Liberar memória". `tests/test_whisper_idle.py`. |
| U9, F2 | `e8a62d2` | Legendar aceita vários arquivos/pasta (sem subpastas) + "Esvaziar fila". |
| F1 | `ff1cce7` | Corte rápido (stream copy) nas Ferramentas; "Caber em um limite" sempre na CPU. |
| M2 | `25fd062` | FFmpeg instala apenas ffmpeg e ffprobe e limpa ffplay antigo. |
| U5 | `7077ab9` | Configurações com singular, ícones distintos, checagem unificada e estado real CUDA/CPU. |
| F5 | `27f0cf1` | Perfil pronto para baixar, legendar e incorporar faixa. |
| F4 | `8158ca0` | Capítulos da análise preenchem o intervalo do trecho. |
| F3 | `13aab50` | Pausa e retomada por item ou de toda a fila, com estado persistente. |
| U7 | `b3ad1b3` | Ferramentas compactas com seleção do arquivo no topo. |
| U8 | `876d575` | Avisos, estados e erros amigáveis respeitam o idioma inglês. |
| M1 | `0e3b629` | Windows instala yt-dlp do ZIP oficial em pasta, com hashes do ZIP e de cada arquivo. |

Ver `PENDENCIAS.md` na raiz para H2, validação final e publicação da 1.12.0.

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
