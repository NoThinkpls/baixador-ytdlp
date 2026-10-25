# Guia de uso

[Read this guide in English](USAGE-GUIDE.en.md)

## Baixar conteúdo

Cole o link, analise as qualidades disponíveis e escolha vídeo, áudio ou apenas um trecho. O aplicativo usa a melhor qualidade por padrão e permite selecionar contêiner, resolução, codec e pasta de saída.

A fila permite processar mais de um item, cancelar, tentar novamente os que falharam e acompanhar velocidade, progresso e previsão de término. Quedas transitórias de rede recebem retentativas automáticas; se o aplicativo fechar, a fila e os arquivos parciais voltam na próxima abertura. Também é possível importar uma lista de URLs e salvar perfis de saída para repetir uma configuração.

A análise mostra a miniatura, o nome final previsto, as combinações de imagem e áudio, tamanho aproximado, idiomas de áudio e as legendas manuais ou automáticas que o site disponibiliza. Em downloads de áudio, capa, metadados e capítulos usam as opções de **Conteúdo extra**; também é possível organizar por canal/artista.

Ative **Gerar legenda ao terminar** para enviar cada arquivo concluído à fila do Whisper. Em vídeo, **Incorporar legenda como faixa** também cria uma cópia legendada sem reencodar a imagem. Os próximos downloads continuam normalmente enquanto a transcrição trabalha.

## Conteúdo que exige login

Para vídeos privados, com idade restrita ou quando o YouTube pedir confirmação de acesso, use um arquivo `cookies.txt` no formato Netscape em **Configurações**. Não compartilhe esse arquivo: ele pode conceder acesso à sua conta.

O aplicativo instala o Deno automaticamente quando necessário para o desafio JavaScript do YouTube. Cookies não substituem esse requisito.

## Transcrição e legendas

Arraste um vídeo ou áudio para a área de transcrição, escolha idioma, tarefa e modelo, e exporte SRT, WebVTT, ASS, ASS karaoke, TXT ou JSON. É possível traduzir a fala para inglês, informar nomes e termos técnicos como contexto e ajustar largura e duração dos blocos. O Large v3 Turbo prioriza velocidade e precisão, mas não oferece tradução.

Em **Gerenciar modelos**, baixe os pesos antes do uso, acompanhe o progresso, confira o espaço ocupado ou remova um modelo. Em máquinas NVIDIA compatíveis, a transcrição pode usar CUDA; nas demais, usa CPU automaticamente. No Apple Silicon, usa MLX.

O processo protegido do Whisper permanece aberto entre itens consecutivos da fila e reaproveita o modelo que já está na memória. O carregamento só acontece de novo ao trocar o modelo ou o perfil de economia de memória da GPU.

## Idioma da interface

Em **Configurações → Aparência → Idioma da interface**, escolha **English** para usar o aplicativo em inglês. Feche e abra o aplicativo para aplicar a escolha: assim downloads, conversões e transcrições já em andamento não são interrompidos.

## Enviar um link do navegador

O instalador registra o protocolo `baixador://`. Crie um favorito no navegador
com o endereço abaixo; clicar nele numa página de vídeo abre o aplicativo e
**analisa** o link — o download só começa quando você confirma.

```text
javascript:location.href='baixador://baixar?url='+encodeURIComponent(location.href)
```

No Linux o protocolo é registrado pelo pacote `.deb`; no macOS, pelo `.app`.

## Playlists

Depois de analisar uma playlist, use **Escolher itens** para marcar só os vídeos
desejados (há busca por título). A seleção vira o `--playlist-items` do yt-dlp.
A qualidade escolhida vale por altura (ex.: até 1080p) para todos os itens.

## Ferramentas de mídia

A página **Ferramentas** trabalha localmente com FFmpeg. As tarefas ficam em grupos:

- **Cortar e ajustar:** recortar trecho (com corte rápido sem reencodar), ajustar velocidade (0,25x a 4x, som acompanhando), girar ou espelhar e criar versão vertical com fundo desfocado.
- **Áudio:** extrair em MP3, M4A, Opus, FLAC ou WAV; nivelar volume (EBU R128, com alvos de -16, -14 ou -23 LUFS, sem recodificar a imagem); remover áudio (cópia sem som, sem perda).
- **Converter e reduzir:** converter para MP4 (H.264) ou WebM (VP9), trocar contêiner sem recomprimir, reduzir tamanho e **fazer caber num limite** (Discord, WhatsApp, e-mail).
- **Imagem e animação:** criar GIF de até 30 s com paleta própria e capturar um quadro como PNG, JPG ou WebP.
- **Legendas e privacidade:** gravar legendas na imagem, extrair a legenda embutida (SRT, ASS ou VTT, salva ao lado do vídeo) e limpar metadados (localização, data, câmera e título) sem recodificar.

O formato ou a extensão do resultado vale pelo nome escolhido em "Onde salvar": trocar `.mp3` por `.flac` muda o codec junto. O percentual aparece na tela e, quando disponível, na barra de tarefas. Nenhum arquivo é enviado pelo aplicativo para executar essas operações.

## Cortes verticais

A página **Cortes** transforma trechos de um vídeo em vídeos verticais prontos para Shorts, Reels e TikTok:

1. Em **Vídeo de origem**, escolha um arquivo ou cole um link do YouTube (só os trechos são baixados). Logo abaixo, em **Salvar cortes em**, confira a pasta de destino.
2. Em **Cortes**, informe início e fim de cada corte (`mm:ss` ou `hh:mm:ss`) e, se quiser, um título. Use **Adicionar corte** para vários de uma vez (até 20).
3. Em **Enquadramento**, escolha como o vídeo horizontal vira vertical:
   - **Seguir a pessoa — automático**: aproxima e acompanha quem está em cena, como o reenquadrar do CapCut. O app procura rostos alguns quadros por segundo e, quando não acha (pessoa de costas ou longe), segue o movimento. A câmera só se mexe quando a pessoa sai do centro e anda devagar, sem tremer.
   - **Fundo desfocado**: mostra o quadro inteiro com o próprio vídeo desfocado atrás.
   - **Cortar no centro**: preenche a tela com o meio do vídeo.

   Ali também ficam a remoção de pausas e a pausa mínima.
4. Em **Legenda**, escolha a animação (destaque, só cor, karaokê, uma palavra por vez, grupo com pulo ou sem destaque), fonte, tamanho, cor do texto, cor da palavra falada, altura (em % da tela), quantas palavras aparecem por vez (1 a 4) se ficam em maiúsculas e se ganham uma caixa escura atrás. A prévia ao lado mostra o resultado sobre um quadro do próprio vídeo; arraste a legenda ou o título nela para subir ou descer (a altura do título também tem campo próprio). As escolhas ficam salvas para os próximos cortes.
5. Em **Acabamento**, escolha quanto tempo o título fica na tela e, se quiser, ligue o zoom nas emendas, os efeitos sonoros (whoosh, pop, impacto, ding e subida; com a opção de usar uma pasta com os seus sons), o zoom na ênfase, a barra de progresso, o volume equilibrado e a cópia da legenda em `.srt`.
Para deixar uma IA de texto escolher os cortes, os títulos e onde entra cada som, cole a linha do plano dela no campo **Plano da IA**, logo abaixo da lista de cortes. Formato e texto pronto para qualquer IA em [PLANO-DA-IA.md](PLANO-DA-IA.md).
6. Em **Transcrição**, confira o idioma e o modelo Whisper (os mesmos da aba Legendar) e clique em **Criar cortes**.

Cada corte é salvo como `nome_corte01_titulo.mp4` na pasta escolhida. Os cortes prontos ficam salvos mesmo se você cancelar ou se um corte seguinte falhar. O título aparece animado nos 2 primeiros segundos, numa caixa da cor de destaque.

Cada corte pronto aparece no **Histórico**, com botões para abrir o arquivo, mostrar na pasta, gerar legenda e fazer outros cortes do mesmo vídeo. O que sai da aba **Ferramentas** (converter, extrair áudio, recortar etc.) e os vídeos com legenda incorporada também vão para o Histórico.

## Bandeja e segundo plano

Em **Configurações → Comportamento**, escolha se conclusões devem gerar notificações do sistema. A opção de fechar para a bandeja mantém trabalhos ativos; use **Sair** no menu do ícone para encerrar o aplicativo de verdade.

## Atualizações

Em **Configurações → Nova versão do aplicativo**, você vê a última checagem e pode verificar manualmente (a checagem ao abrir pode ser desligada). O botão **Verificar componentes** consulta yt-dlp, FFmpeg e Deno: o FFmpeg só é baixado de novo quando sai um ramo estável mais novo, não a cada checagem. No Windows, quando há uma versão nova, a faixa inferior oferece atualizar ou dispensar o aviso. O instalador é conferido com SHA-256 antes de ser aberto. A checagem também confere o hash do próprio executável com o publicado na release: se a versão for a mesma mas o arquivo não conferir (corrompido ou alterado), a faixa oferece **Reinstalar** a versão oficial.

## Quando um site para de funcionar

Em **Configurações → Downloads**, troque o **Canal do yt-dlp** para *Nightly*:
as correções para mudanças do YouTube saem ali dias antes da versão estável.
Para relatar um problema, use **Configurações → Diagnóstico → Exportar
diagnóstico**: o ZIP sai sem cookies, senhas de proxy, tokens de URL e sem o
nome da sua pasta de usuário.

## Onde ficam os dados

No Windows, configurações, histórico, fila, modelos e dependências ficam em `%LOCALAPPDATA%\\BaixadorYtdlp`. No macOS, ficam em `~/Library/Application Support/BaixadorYtdlp`. No Linux, ficam em `~/.local/share/BaixadorYtdlp` (ou no diretório definido em `XDG_DATA_HOME`). A pasta dos downloads é configurável.

