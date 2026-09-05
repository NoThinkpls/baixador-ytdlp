# Baixador YT-DLP

Baixe vídeos e áudios, transcreva localmente e faça ajustes de mídia em uma interface Apple + Discord para Windows e macOS Apple Silicon.

[![Última versão](https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?display_name=tag&label=vers%C3%A3o)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![Windows e macOS Apple Silicon](https://img.shields.io/badge/plataformas-Windows%20%7C%20macOS%20Apple%20Silicon-0078D4)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)](LICENSE)

## Download

| Seu caso | Escolha | Download |
| --- | --- | --- |
| Windows 10/11 | Instalação normal, com atalho e atualização pelo app | [Baixar instalador](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Usar sem instalar: descompacte o ZIP e abra o executável | [Baixar versão portable](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| Mac com M1, M2, M3 ou M4 | Instalação normal: abra o DMG e arraste para Aplicativos | [Baixar instalador para macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| Mac com M1, M2, M3 ou M4 | Usar sem instalar: descompacte e abra o app | [Baixar versão portable para macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |

> Os quatro links acima usam os aliases estáveis da Release mais recente. A automação bloqueia uma publicação de tag se algum link ou arquivo obrigatório estiver ausente.

Se uma versão acabou de ser publicada, aguarde a etapa **Publicar release** no [GitHub Actions](../../actions) terminar antes de baixar: é ela que anexa os arquivos à Release.

## O que o aplicativo oferece

- Download de vídeo, áudio, playlists e trechos com escolha de qualidade e formato.
- Entrada em lote pela própria tela: cole vários links, um por linha, e envie todos à fila.
- Fila, perfis de saída, histórico, retomativa de falhas e organização por pasta.
- Transcrição local com legendas SRT, VTT, ASS, karaoke, TXT e JSON; no Apple
  Silicon ela usa MLX na GPU integrada.
- Conversão por GPU com NVIDIA NVENC, AMD AMF ou VideoToolbox no Apple Silicon.
- Ferramentas locais para recortar, extrair áudio, compactar, criar Shorts e queimar legendas.
- Atualização opcional no Windows, conferida por SHA-256 antes de abrir o instalador.

## Interface

A partir da versão 1.4.5 a interface tem linguagem visual própria, sem o Fluent
Design da Microsoft — inclusive no Windows.

- **Estrutura Discord.** Barra lateral com seções em caixa alta, indicador do
  item ativo na borda e modo compacto com ícones e tooltips.
- **Controles Apple.** Interruptores em cápsula, listas agrupadas (um bloco
  arredondado por assunto, com fios finos entre as linhas) e a hierarquia
  tipográfica das Human Interface Guidelines.
- **Ícones próprios.** Conjunto de traço fino desenhado para o projeto e
  colorido em tempo de execução, então nada some no tema claro ou no escuro.
- **Tema claro e escuro** com troca imediata, acompanhando o sistema quando a
  opção é “Seguir o sistema”.
- **Ferramentas guiadas.** As edições locais seguem quatro passos claros:
  escolher a tarefa, selecionar a origem, ajustar apenas o necessário e salvar.
- **Avisos que não atrapalham:** aparecem no alto do conteúdo, longe dos botões
  do cabeçalho, e somem sozinhos.
- **Cookies sem adivinhação:** o app mostra o passo a passo, abre o guia do
  yt-dlp e indica uma extensão de exportação que processa o arquivo localmente.

AMD é acelerada pelo AMF do FFmpeg na conversão. A transcrição usa CUDA nas
placas NVIDIA, MLX na GPU integrada de Macs Apple Silicon e CPU otimizada nas
placas AMD, pois o motor de transcrição atual não possui backend AMD para
Windows. No Mac, o primeiro uso de cada modelo do Whisper ainda precisa baixá-lo
para o perfil local do usuário; os usos seguintes reaproveitam esse cache.

Os nomes de arquivos e os textos da interface usam UTF-8 de ponta a ponta,
preservando acentos e caracteres especiais compatíveis com o sistema de arquivos.

A tipografia pede SF Pro quando ela existe na máquina e cai em Inter e Segoe UI
quando não existe — o projeto não distribui fontes proprietárias. As cores, os
raios e a escala tipográfica ficam em `baixador_ytdlp/ui/theme.py`, que é a
única fonte de verdade visual do aplicativo.

## Documentação

- [Guia de uso](docs/GUIA-DE-USO.md)
- [Plataformas, desempenho e segurança](docs/PLATAFORMAS-E-SEGURANCA.md)
- [Compilação e publicação de Releases](docs/COMPILACAO-E-RELEASE.md)

## Licença e uso

O projeto usa [yt-dlp](https://github.com/yt-dlp/yt-dlp) e [FFmpeg](https://ffmpeg.org/). Baixe apenas conteúdo que você tenha direito de acessar e utilizar. O código deste repositório está sob a [licença MIT](LICENSE).
