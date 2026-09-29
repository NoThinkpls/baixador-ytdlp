# Otimização por plataforma — análise (29/09/2026)

Foco: usar o melhor de cada equipamento. Este documento é só a análise; nada
aqui foi implementado ainda. Cada item traz o que existe hoje, a lacuna e o risco.

## O que existe hoje

| Área | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Codificar (Ferramentas, conversão pós-download) | NVENC e AMF (`gpu.py`) | VideoToolbox | NVENC e AMF (a lista é a mesma do Windows) |
| Decodificar | detecta `cuda` e `d3d11va`, mas não usa | detecta `videotoolbox`, não usa | detecta, não usa |
| Transcrição (Whisper) | CUDA via CTranslate2; senão CPU | MLX na GPU integrada; senão CPU | CUDA; senão CPU |
| Download | `--concurrent-fragments` por núcleos/RAM | idem | idem |

Lacunas principais: **Intel (QSV) não existe em lugar nenhum; VAAPI (AMD e Intel no
Linux) não existe; Whisper só acelera em NVIDIA (Windows/Linux) e no Apple Silicon (MLX)**; decodificação por hardware é
detectada e ignorada; recortes/conversões rodam um por vez.

## Prioridades

### P1 — Download de trecho (feito, mais possível)
Medido em 29/09: DASH via FFmpeg ~2× o tempo real; HLS ~9× (82 min em ~10,5 min).
Já publicado como preferência para YouTube. Próximo passo, se ainda importar:
dividir o intervalo em N partes com N FFmpeg e juntar com `-c copy` (cada conexão
tem o mesmo teto, então N partes ≈ N×). Risco: emendas em quadros-chave; precisa de
teste de continuidade. Alternativa a testar (bloqueada por captcha do IP hoje): se o
downloader HLS nativo do yt-dlp aceita `--download-sections` com
`--concurrent-fragments`.

### P2 — Encoders por vendor (Windows e Linux)
- **Intel QSV** (`h264_qsv`, `hevc_qsv`, `av1_qsv`): iGPU Intel e Arc. Windows e Linux.
- **VAAPI** (`h264_vaapi`, `hevc_vaapi`, `av1_vaapi`): AMD e Intel no Linux; é o
  caminho de AMD no Linux (AMF só existe no driver proprietário).
- **AMF** continua para AMD no Windows.
- Escolha automática por prioridade e teste real de 1 quadro (já existe para
  NVENC/AMF em `_usable_encoders`); mostrar o backend real nas Configurações.
- Os builds do BtbN usados no Windows/Linux já incluem qsv/vaapi/amf/nvenc; conferir
  com `-encoders` na primeira execução.
- Risco: cada driver tem quirks de rate-control; manter fallback em camadas
  (GPU → outro backend → x264) como hoje.

### P3 — Decodificação por hardware
Hoje só o encoder usa GPU; decodificar 4K/HEVC na CPU limita a conversão.
Usar `-hwaccel cuda|d3d11va|qsv|vaapi|videotoolbox` conforme o backend do encoder,
com fallback sem `-hwaccel` se o filtro falhar. Ganho maior em vídeos grandes e em
conversão em lote. Risco: filtros de legenda queimada exigem `hwdownload`.

### P4 — Vários trechos/arquivos em paralelo
NVENC em GPU de consumo aceita até 5 sessões simultâneas
([Tom's Hardware](https://tomshardware.com/news/nvidia-increases-concurrent-nvenc-sessions-on-consumer-gpus));
AMF/QSV/VAAPI não têm limite documentado equivalente. Proposta: fila de Ferramentas
com `N = min(sessões, núcleos/2)` trabalhos simultâneos por GPU (NVENC: 3 por
padrão), e várias faixas do mesmo vídeo lado a lado. Ganho grande em lote (vários
cortes de uma live). Risco: VRAM e I/O de disco; expor o número em Configurações.

### P5 — Whisper em AMD e Intel
O macOS já usa MLX na GPU do Apple Silicon. Falta AMD e Intel no Windows/Linux:
CTranslate2 só tem CUDA e CPU (sem ROCm). Caminho: whisper.cpp com Vulkan (ou HIP no
AMD) como segundo motor. Custo: empacotamento e testes por plataforma; a interface do
legendador já isola o motor. Ganho real só para quem não tem NVIDIA.

### P6 — Ajustes finos por plataforma
- macOS: `--concurrent-fragments` e threads do Whisper usando só núcleos de
  desempenho (já existe `apple_performance_cores`); VideoToolbox com `-allow_sw 0`
  para não cair em software sem avisar; priorizar HEVC/H.264 de hardware.
- Linux: detectar `/dev/dri/renderD*` e permissão do usuário (grupo `render`) e
  explicar na interface quando o VAAPI está indisponível.
- Windows: preferir a GPU dedicada em notebooks híbridos (Optimus/PowerXpress):
  escolher o adaptador do encoder (`-gpu` no NVENC/AMF) em vez do padrão do sistema.
- yt-dlp: manter Deno atualizado só quando a versão suportada muda (mesma regra do
  FFmpeg, já aplicada).

## Ordem sugerida

1. P2 (QSV + VAAPI) e P3 (decodificação): amplia a cobertura sem mexer no Whisper.
2. P4 (paralelismo): maior ganho para quem faz lotes.
3. P5 (Whisper com Vulkan para AMD/Intel).
4. P6 e a divisão paralela do trecho (P1) conforme a necessidade.

Cada item entra como um commit com testes que falham no código antigo, como no plano
de correções.

Fontes: [whisper.cpp e alternativas por plataforma](https://forum.shotcut.org/t/support-gpu-accelerated-whisper-on-more-platforms/51218),
[Whisper em GPU AMD](https://medium.com/@abhshk/running-gpu-accelerated-whisper-on-an-amd-gpu-no-nvidia-required-e27ea20b2ccd),
[limite de sessões NVENC](https://tomshardware.com/news/nvidia-increases-concurrent-nvenc-sessions-on-consumer-gpus).
