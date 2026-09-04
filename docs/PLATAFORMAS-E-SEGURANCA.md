# Plataformas, desempenho e segurança

## Windows

O instalador é por usuário e não exige UAC. A edição portable não instala atalhos nem altera a lista de aplicativos: basta descompactar o ZIP e executar `baixador-ytdlp.exe`.

O Windows pode exibir SmartScreen enquanto o instalador não tiver assinatura digital e reputação suficientes. Cada Release inclui `SHA256SUMS.txt`; confira-o com:

```powershell
Get-FileHash .\\baixador-ytdlp-setup.exe -Algorithm SHA256
```

## macOS Apple Silicon

A compilação para macOS é arm64 e destina-se a Macs M1, M2, M3 e M4 com macOS 14 ou mais recente. Descompacte o arquivo, mova `baixador-ytdlp.app` para **Aplicativos** e abra-o.

Enquanto a assinatura Developer ID e a notarização não estiverem configuradas, o macOS pode pedir uma confirmação adicional em **Privacidade e Segurança**. A atualização automática do aplicativo permanece exclusiva do instalador Windows; no macOS, baixe a nova versão manualmente pela Release.

## Desempenho

Downloads dependem sobretudo da rede. Para transcrição, o aplicativo usa CUDA quando uma NVIDIA compatível está disponível e CPU/int8 como fallback. No Apple Silicon, a transcrição usa CPU com instruções NEON; CTranslate2 não possui backend Metal/MPS para Whisper. A conversão de vídeo pode usar NVENC no Windows ou VideoToolbox no macOS quando o FFmpeg disponível oferecer suporte.

## Medidas de segurança

- Dependências e instaladores são baixados por HTTPS; o instalador do aplicativo é validado com SHA-256.
- Subprocessos são iniciados sem shell e com configurações externas do yt-dlp ignoradas.
- Cookies, histórico e configurações permanecem locais. Nunca publique `cookies.txt` ou `settings.json`.
- Em máquinas corporativas, a execução de um aplicativo que baixa binários no perfil do usuário pode ser bloqueada por políticas de segurança.
