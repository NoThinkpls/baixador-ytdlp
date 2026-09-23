# Plataformas, desempenho e segurança

## Windows

O instalador é por usuário e não exige UAC. A edição portable não instala atalhos nem altera a lista de aplicativos: basta descompactar o ZIP e executar `baixador-ytdlp.exe`. Configurações, logs e binários ficam na pasta `data` ao lado do executável.

O Windows pode exibir SmartScreen enquanto o instalador não tiver assinatura digital e reputação suficientes. Cada Release inclui `SHA256SUMS.txt`; confira-o com:

```powershell
Get-FileHash .\\baixador-ytdlp-setup.exe -Algorithm SHA256
```

## macOS Apple Silicon

A compilação para macOS é arm64 e destina-se a Macs M1, M2, M3 e M4 com macOS 14 ou mais recente.

- **DMG (instalação normal):** abra o arquivo, arraste `baixador-ytdlp.app` para o atalho **Applications** e ejete o disco.
- **ZIP portable:** descompacte e abra `baixador-ytdlp.app` de qualquer pasta, sem instalar; os dados ficam dentro do próprio pacote.

Enquanto a assinatura Developer ID e a notarização não estiverem configuradas, o macOS pode pedir uma confirmação adicional em **Privacidade e Segurança**. A atualização automática do aplicativo permanece exclusiva do instalador Windows; no macOS, baixe a nova versão manualmente pela Release. A interface usa a SF Pro já presente no macOS, sem incluir ou redistribuir fontes da Apple.

## Linux (Ubuntu/Debian)

A distribuição oficial inicial é x86_64 e atende Ubuntu 22.04 ou superior e Debian 12 ou superior.

- **`.deb`:** baixe o pacote e instale com `sudo apt install ./baixador-ytdlp-linux-amd64.deb`.
- **Portable:** descompacte o `.tar.gz`, entre na pasta criada e execute `./baixador-ytdlp`; os dados ficam na subpasta `data`.

Na primeira abertura, yt-dlp, FFmpeg e Deno são obtidos das fontes oficiais para `~/.local/share/BaixadorYtdlp/bin`. Ferramentas presentes no `PATH` só são usadas quando a opção avançada correspondente é ligada. A atualização do aplicativo no Linux é manual pela Release.

## Desempenho

Downloads dependem sobretudo da rede. Para transcrição, o aplicativo usa CUDA quando uma NVIDIA compatível está disponível e CPU/int8 como fallback. No Apple Silicon, usa **MLX Whisper** na GPU integrada; se esse backend não puder iniciar, cai automaticamente para CPU/NEON, usando somente os núcleos de desempenho que o macOS informa. O CTranslate2 não possui backend Metal/MPS para Whisper, por isso o MLX é o caminho acelerado no Mac. A conversão de vídeo pode usar NVENC ou AMD AMF no Windows e VideoToolbox no macOS quando o FFmpeg disponível oferecer suporte. No Linux, a primeira distribuição prioriza CPU/int8 e o mesmo fallback seguro.

O primeiro uso de cada modelo baixa os pesos para os dados locais do aplicativo; o gerenciador permite antecipar o download, acompanhar o progresso e liberar o espaço depois. Não há envio de áudio ou vídeo a um serviço remoto.

## Medidas de segurança

- Downloads HTTPS sempre validam o certificado; não existe fallback TLS inseguro.
- yt-dlp, FFmpeg e Deno só são instalados quando há um SHA-256 válido publicado pelo fornecedor. O hash verificado é guardado e conferido antes das execuções futuras.
- Pesos Whisper e MLX são baixados de revisões imutáveis, nunca diretamente de uma branch mutável.
- O instalador do aplicativo é validado com SHA-256 e os artefatos oficiais recebem atestados de proveniência do GitHub Actions. A assinatura Authenticode/Developer ID ainda depende da obtenção dos certificados próprios do projeto.
- Subprocessos são iniciados sem shell e com configurações externas do yt-dlp ignoradas.
- Links, proxy e caminhos de cookies são redigidos antes de entrar nos logs. Cookies, histórico e configurações permanecem locais. Nunca publique `cookies.txt` ou `settings.json`.
- Em máquinas corporativas, a execução de um aplicativo que baixa binários no perfil do usuário pode ser bloqueada por políticas de segurança.
