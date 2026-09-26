<p align="center">
  <img src="assets/icon.png" width="96" alt="Ícone do Baixador YT-DLP">
</p>

<h1 align="center">Baixador YT-DLP</h1>

<p align="center">
  Baixe mídia, transcreva áudio localmente e faça ajustes de vídeo — em um aplicativo para Windows, macOS Apple Silicon e Linux.
</p>

<p align="center">
  <a href="README.en.md">Read in English</a> ·
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/releases/latest">Baixar a versão mais recente</a> ·
  <a href="docs/README.md">Documentação</a>
</p>

<p align="center">
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/releases/latest"><img src="https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?display_name=tag&label=release" alt="Última release"></a>
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml"><img src="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml/badge.svg?branch=main" alt="Build"></a>
  <a href="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/security.yml"><img src="https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/security.yml/badge.svg?branch=main" alt="Segurança"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/licen%C3%A7a-MIT-2ea44f" alt="Licença MIT"></a>
</p>

## Baixe para sua plataforma

| Plataforma | Opção recomendada | Download |
| --- | --- | --- |
| Windows 10/11 | Instalador com atalho e atualização pelo app | [Baixar instalador](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Usar sem instalar | [Versão portátil](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| macOS em M1/M2/M3/M4 | Arraste o app do DMG para Aplicativos | [Baixar para macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| macOS em M1/M2/M3/M4 | Usar sem instalar | [Versão portátil](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |
| Ubuntu 22.04+/Debian 12+ x86_64 | Pacote integrado ao sistema | [Baixar `.deb`](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-linux-amd64.deb) |
| Linux x86_64 | Usar sem instalar | [Versão portátil](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-linux-x86_64.tar.gz) |

Os links usam nomes estáveis da última release aprovada. Verifique os hashes SHA-256 publicados junto aos instaladores quando precisar comprovar a integridade.

## O que você pode fazer

- **Baixar com controle.** Vídeos, áudios, playlists e trechos, com prévia de formatos, idiomas, tamanho estimado e nome final antes de iniciar.
- **Transcrever no seu computador.** Legendas SRT, VTT, ASS, karaoke, TXT ou JSON com Whisper; tradução para inglês e vocabulário de contexto são opcionais.
- **Editar sem sair do app.** Recorte, extraia áudio, compacte para um limite, crie vídeo vertical, remuxe e incorpore legendas com progresso real.
- **Aproveitar o hardware disponível.** CUDA para NVIDIA, MLX no Apple Silicon, NVENC/AMF/VideoToolbox quando suportados e fallback seguro para CPU.
- **Trabalhar em fila.** Cole vários links, retome downloads parciais, receba retentativas para falhas transitórias e mantenha tarefas em segundo plano.
- **Manter seus dados sob controle.** Diagnósticos removem dados sensíveis; cookies não são enviados pelo aplicativo e a transcrição é local.

## Primeiros passos

1. Baixe o pacote recomendado para sua plataforma e abra o aplicativo.
2. Cole um link, analise as opções disponíveis e escolha formato e destino.
3. Para gerar legendas, abra **Transcrição**, selecione o modelo e adicione a mídia à fila. O primeiro uso de cada modelo pode baixá-lo para seu perfil.

Veja o [guia de uso](docs/GUIA-DE-USO.md) para playlists, sites que exigem login, protocolo `baixador://`, ferramentas de mídia e solução de problemas.

## Plataformas e segurança

| Sistema | Arquitetura | Transcrição | Aceleração de vídeo |
| --- | --- | --- | --- |
| Windows 10/11 | x86_64 | CUDA NVIDIA ou CPU/int8 | NVENC e AMD AMF |
| macOS 14+ | Apple Silicon | MLX ou CPU | VideoToolbox |
| Ubuntu/Debian | x86_64 | CPU/int8 | Conforme o FFmpeg disponível |

As releases oficiais são compiladas e verificadas nos três sistemas antes de serem publicadas. Cada uma inclui hashes SHA-256, inventários de dependências (SBOM) e atestado de proveniência. Detalhes estão em [Plataformas, desempenho e segurança](docs/PLATAFORMAS-E-SEGURANCA.md).

## Documentação

- [Central de documentação](docs/README.md)
- [Guia de uso](docs/GUIA-DE-USO.md) · [Usage guide](docs/USAGE-GUIDE.en.md)
- [Plataformas e segurança](docs/PLATAFORMAS-E-SEGURANCA.md) · [Platforms and security](docs/PLATFORMS-AND-SECURITY.en.md)
- [Build e releases](docs/COMPILACAO-E-RELEASE.md) · [Build and releases](docs/BUILD-AND-RELEASE.en.md)
- [Changelog](CHANGELOG.md)

## Comunidade e desenvolvimento

Encontrou um problema? Abra uma [issue](https://github.com/NoThinkpls/baixador-ytdlp/issues/new/choose) sem publicar cookies, tokens ou links privados. Quer contribuir? Leia o [guia de contribuição](CONTRIBUTING.md) e a [política de segurança](SECURITY.md).

## Licença e uso responsável

O código é distribuído sob a [licença MIT](LICENSE). O aplicativo usa [yt-dlp](https://github.com/yt-dlp/yt-dlp) e [FFmpeg](https://ffmpeg.org/); suas licenças e avisos estão em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Baixe apenas conteúdo que você tenha direito de acessar e utilizar.
