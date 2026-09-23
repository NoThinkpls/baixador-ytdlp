# Baixador YT-DLP

[Read this documentation in English](README.en.md)

Baixe vídeos e áudios, transcreva localmente e faça ajustes de mídia em uma interface Apple + Discord para Windows, macOS Apple Silicon e Linux.

[![Última versão](https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?display_name=tag&label=vers%C3%A3o)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![Windows, macOS e Linux](https://img.shields.io/badge/plataformas-Windows%20%7C%20macOS%20Apple%20Silicon%20%7C%20Linux-0078D4)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)](LICENSE)

## Download

| Seu caso | Escolha | Download |
| --- | --- | --- |
| Windows 10/11 | Instalação normal, com atalho e atualização pelo app | [Baixar instalador](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe) |
| Windows 10/11 | Usar sem instalar: dados e binários permanecem dentro da pasta extraída | [Baixar versão portable](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-windows.zip) |
| Mac com M1, M2, M3 ou M4 | Instalação normal: abra o DMG e arraste para Aplicativos | [Baixar instalador para macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.dmg) |
| Mac com M1, M2, M3 ou M4 | Usar sem instalar: descompacte e abra o app | [Baixar versão portable para macOS](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-macos-arm64.zip) |
| Ubuntu 22.04+/Debian 12+ (x86_64) | Instalação integrada ao sistema | [Baixar pacote `.deb`](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-linux-amd64.deb) |
| Linux x86_64 | Usar sem instalar: dados e binários permanecem dentro da pasta extraída | [Baixar versão portable](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-portable-linux-x86_64.tar.gz) |

> Os seis links acima usam os aliases estáveis da Release mais recente. A automação só cria ou atualiza a Release após validar todos os pacotes obrigatórios.

Se uma versão acabou de ser publicada, aguarde a etapa **Publicar release** no [GitHub Actions](../../actions) terminar antes de baixar: é ela que anexa os arquivos à Release.

## O que o aplicativo oferece

- Download de vídeo, áudio, playlists e trechos com escolha de qualidade e formato. Recortes exatos mostram o andamento e tentam NVENC, AMF ou VideoToolbox diretamente; NVIDIA e Apple também usam decodificação por hardware quando a mídia aceita. Se o decoder não for compatível, a codificação continua na GPU; só então há fallback seguro para CPU.
- Análise prévia com miniatura, nome final estimado, tamanhos aproximados, codecs, formatos, idiomas de áudio e legendas manuais/automáticas disponíveis.
- Entrada em lote pela própria tela: cole vários links, um por linha, e envie todos à fila.
- Envio direto do navegador pelo protocolo `baixador://` (favorito de um clique) e escolha dos itens de uma playlist.
- Canal *nightly* do yt-dlp opcional para receber correções de sites antes da versão estável.
- Compactação para caber num limite (Discord, WhatsApp, e-mail) e versão vertical com fundo desfocado.
- Exportação de diagnóstico já redigido, sem cookies, senhas ou tokens.
- Fila persistente, retomada de arquivos parciais e retentativas automáticas para falhas transitórias. Itens podem ser removidos mesmo durante a inicialização; solicitações repetidas só entram após confirmação.
- Capa, metadados e capítulos incorporados também em áudio; opção de organizar músicas por canal/artista.
- Transcrição local com modelos até Large v3 Turbo, tradução para inglês, vocabulário de contexto e legendas SRT, VTT, ASS, karaoke, TXT e JSON; no Apple Silicon ela usa MLX na GPU integrada. A fila reutiliza o processo e o modelo já carregado entre mídias compatíveis.
- Fluxo **Baixar e legendar**: ao concluir o download, o arquivo pode entrar automaticamente na fila do Whisper e receber uma faixa de legenda sem reencodificação.
- Conversão por GPU com NVIDIA NVENC, AMD AMF ou VideoToolbox no Apple Silicon.
- Ferramentas locais com progresso real para recortar, extrair áudio, compactar, criar Shorts e adicionar legendas ao vídeo.
- Gerenciador de modelos Whisper, notificações pela bandeja do sistema e opção de continuar tarefas em segundo plano.
- Atualização opcional no Windows, conferida por SHA-256 antes de abrir o instalador.
- Componentes de runtime só são instalados quando o fornecedor publica um SHA-256 válido; a conexão TLS nunca desliga a validação de certificado.
- Uma segunda abertura traz a janela existente para frente e encaminha o link recebido, em vez de descartá-lo.

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
- **Português e inglês.** Em **Configurações → Aparência**, escolha o idioma da
  interface; a troca entra na próxima abertura para não interromper tarefas.
- **Análise legível.** A prévia separa formatos, áudio e legendas em cartões curtos; a tabela deixa FPS junto da qualidade e destaca tamanhos aproximados.
- **Nome antes de baixar.** A tela mostra uma prévia do template configurado e oferece atalhos para inserir título, canal, data, ID e resolução.
- **Ferramentas guiadas.** As edições locais seguem quatro passos claros:
  escolher a tarefa, selecionar a origem, ajustar apenas o necessário e salvar.
- **Avisos que não atrapalham:** aparecem no alto do conteúdo, longe dos botões
  do cabeçalho, e somem sozinhos.
- **Barra de tarefas do Windows.** O ícone do aplicativo é mantido mesmo com a
  janela sem moldura; ele exibe o andamento dos downloads, transcrições e ferramentas.
  Ao concluir, o botão fica em 100% por instantes e pisca para avisar mesmo com
  a janela minimizada.
- **Bandeja do sistema.** Conclusões podem gerar avisos nativos; opcionalmente, fechar a janela mantém downloads, transcrições e edições em execução.
- **Cookies sem adivinhação:** o app mostra o passo a passo, abre o guia do
  yt-dlp e indica uma extensão de exportação que processa o arquivo localmente.

AMD é acelerada pelo AMF do FFmpeg na conversão no Windows. A transcrição usa CUDA
nas placas NVIDIA, MLX na GPU integrada de Macs Apple Silicon e CPU otimizada nas
placas AMD, pois o motor de transcrição atual não possui backend AMD para Windows.
No Linux da primeira versão, a transcrição usa CPU/int8 e a conversão por GPU fica
desativada quando o FFmpeg não oferecer um encoder compatível. No Mac, o primeiro
uso de cada modelo do Whisper precisa baixá-lo para o perfil local do usuário;
esse download pode ser antecipado e acompanhado no gerenciador de modelos, e os
usos seguintes reaproveitam o cache. A build do macOS inclui sua própria
cadeia atualizada de certificados para que a preparação do ambiente consiga baixar
o yt-dlp e o FFmpeg com validação TLS completa, sem aceitar certificados inválidos.

Os nomes de arquivos e os textos da interface usam UTF-8 de ponta a ponta,
preservando acentos e caracteres especiais compatíveis com o sistema de arquivos.

Downloads, análises, conversões e preparação de áudio rodam em grupos de processos
isolados. Ao cancelar ou fechar o aplicativo, o processo principal e seus filhos
(como FFmpeg e Deno) são encerrados juntos no Windows, macOS e Linux, evitando
processamento órfão em segundo plano.

No Windows, a tipografia usa Segoe UI Variable com hinting completo para manter
o texto nítido inclusive em telas de resolução mais baixa; no macOS, prioriza a
SF Pro nativa. O projeto não distribui fontes proprietárias. As cores, os raios
e a escala tipográfica ficam em `baixador_ytdlp/ui/theme.py`, que é a única
fonte de verdade visual do aplicativo.

## Documentação

- [Guia de uso](docs/GUIA-DE-USO.md)
- [Plataformas, desempenho e segurança](docs/PLATAFORMAS-E-SEGURANCA.md)
- [Compilação e publicação de Releases](docs/COMPILACAO-E-RELEASE.md)
- [Changelog](CHANGELOG.md)
- [Política de segurança](SECURITY.md)
- [Como contribuir](CONTRIBUTING.md)
- [Documentation in English](README.en.md)

## Licença e uso

O projeto usa [yt-dlp](https://github.com/yt-dlp/yt-dlp) e [FFmpeg](https://ffmpeg.org/). Baixe apenas conteúdo que você tenha direito de acessar e utilizar. O código deste repositório está sob a [licença MIT](LICENSE); as bibliotecas distribuídas mantêm suas próprias licenças, listadas em [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

