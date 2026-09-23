# Avisos de terceiros

O baixador-ytdlp é distribuído sob a licença MIT. A distribuição também contém
componentes de terceiros sob suas próprias licenças. Os **textos integrais**
de cada pacote empacotado estão em `THIRD_PARTY_LICENSES.md`, gerado no CI por
`pip-licenses` a partir do ambiente real de build (exigência da LGPL).

## Incluídos no instalador

- Qt / PySide6 / shiboken6 — LGPL-3.0; módulos separados na distribuição *onedir*,
  substituíveis pelo usuário.
- PySideSix-Frameless-Window — LGPL-3.0.
- pywin32 (Windows) — PSF-2.0.
- faster-whisper e CTranslate2 — MIT.
- PyAV — BSD-3-Clause. **O wheel do PyAV embute as próprias bibliotecas do
  FFmpeg** (`av.libs`/DLLs `avcodec-*`, `avformat-*`…), distribuídas sob a
  licença da build do FFmpeg feita pelo projeto PyAV (LGPL); consulte o texto
  em `THIRD_PARTY_LICENSES.md`.
- onnxruntime (VAD Silero do faster-whisper) — MIT.
- tokenizers e huggingface-hub — Apache-2.0.
- NumPy — BSD-3-Clause.
- CUDA Runtime, cuBLAS e cuDNN (Windows) — termos de redistribuição da NVIDIA.
- MLX e mlx-whisper (macOS) — MIT.
- certifi — MPL-2.0.
- Send2Trash — BSD-3-Clause.

## Obtidos em runtime (não acompanham o instalador)

- yt-dlp — Unlicense; SHA-256 conferido contra o `SHA2-256SUMS` oficial.
- FFmpeg (builds GPL do BtbN no Windows/Linux e do Tyrrrz/FFmpegBin no macOS) —
  GPL; SHA-256 conferido pelo digest da API de Releases.
- Deno — MIT; SHA-256 conferido.
- Pesos do Whisper (Systran, mobiuslabsgmbh, mlx-community) — MIT; revisões fixadas.
