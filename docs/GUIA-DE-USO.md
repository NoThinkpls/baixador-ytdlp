# Guia de uso

## Baixar conteúdo

Cole o link, analise as qualidades disponíveis e escolha vídeo, áudio ou apenas um trecho. O aplicativo usa a melhor qualidade por padrão e permite selecionar contêiner, resolução, codec e pasta de saída.

A fila permite processar mais de um item, cancelar, tentar novamente os que falharam e acompanhar velocidade, progresso e previsão de término. Quedas transitórias de rede recebem retentativas automáticas; se o aplicativo fechar, a fila e os arquivos parciais voltam na próxima abertura. Também é possível importar uma lista de URLs e salvar perfis de saída para repetir uma configuração.

A análise mostra as combinações de imagem e áudio, tamanho aproximado, idiomas de áudio e as legendas manuais ou automáticas que o site disponibiliza. Em downloads de áudio, capa, metadados e capítulos usam as opções de **Conteúdo extra**; também é possível organizar por canal/artista.

## Conteúdo que exige login

Para vídeos privados, com idade restrita ou quando o YouTube pedir confirmação de acesso, use um arquivo `cookies.txt` no formato Netscape em **Configurações**. Não compartilhe esse arquivo: ele pode conceder acesso à sua conta.

O aplicativo instala o Deno automaticamente quando necessário para o desafio JavaScript do YouTube. Cookies não substituem esse requisito.

## Transcrição e legendas

Arraste um vídeo ou áudio para a área de transcrição, escolha o idioma e o modelo, e exporte SRT, WebVTT, ASS, ASS karaoke, TXT ou JSON. Em máquinas NVIDIA compatíveis, a transcrição pode usar CUDA; nas demais, usa CPU automaticamente.

## Ferramentas de mídia

A página **Ferramentas** trabalha localmente com FFmpeg: recorte, extraia MP3, remuxe sem recomprimir, compacte, converta para vertical e incorpore legendas. Nenhum arquivo é enviado pelo aplicativo para executar essas operações.

## Atualizações

Em **Configurações → Atualizações do aplicativo**, você pode desligar a checagem ao abrir ou verificar manualmente. No Windows, quando há uma versão nova, a faixa inferior oferece atualizar ou dispensar o aviso. O instalador é conferido com SHA-256 antes de ser aberto.

## Onde ficam os dados

No Windows, configurações, histórico, fila, modelos e dependências ficam em `%LOCALAPPDATA%\\BaixadorYtdlp`. No macOS, ficam em `~/Library/Application Support/BaixadorYtdlp`. No Linux, ficam em `~/.local/share/BaixadorYtdlp` (ou no diretório definido em `XDG_DATA_HOME`). A pasta dos downloads é configurável.
