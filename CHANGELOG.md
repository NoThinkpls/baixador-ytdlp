# Changelog

Todas as mudanças relevantes deste projeto serão registradas aqui, seguindo o
formato Keep a Changelog.

## [1.15.1] - 2026-10-26

### Corrigido

- **Plano da IA** com título entre aspas dava "JSON inválido". A IA escreve as aspas do
  título curvas, como as outras; o app troca todas por retas e as de dentro fechavam o
  texto no meio. Agora uma aspa só fecha o texto quando vem seguida de `,` `]` `}` ou
  `:`, e as outras ficam no título.

### Alterado

- Nome do arquivo de cada corte: o título vem primeiro, para achar o corte na pasta.
  Era `video_corte01_TITULO.mp4`; agora é `TITULO - video - corte01.mp4` (sem título,
  `video - corte01.mp4`), com espaços em vez de sublinhados.

## [1.15.0] - 2026-10-26

### Adicionado

- Cortes, **Título fixo no topo**: uma faixa escura no alto com o título num cartão na cor
  de destaque, do começo ao fim do corte, e o vídeo embaixo (seguindo a pessoa, com fundo
  desfocado ou cortado no centro), no formato dos canais de cortes de podcast. Uma linha
  menor opcional vai acima do título (nome do podcast, convidado, episódio). O título
  diminui sozinho para caber em até 3 linhas; a legenda não sobe para dentro da faixa e os
  zooms mexem só no vídeo. "Seguir a pessoa" mede a janela pela área do vídeo, mais larga
  que 9:16.
- **Plano da IA**: dois campos opcionais, `t` (tipo de título: `"f"` fixo no topo ou
  `"a"` animado) e `l` (a linha de cima do título fixo). Ao aplicar um plano com eles, a
  página troca o tipo de título e preenche a linha; planos antigos continuam iguais. O
  texto pronto para a IA em docs/PLANO-DA-IA.md explica os dois tamanhos de título.

### Alterado

- Página **Cortes** mais fácil de entender: enquadramento e tipo de título viraram cartões
  com miniatura (o bonequinho da prévia, ou um quadro do vídeo) em vez de listas, cada um
  mostrando o resultado com a legenda e as cores escolhidas. A prévia grande mostra o
  título do primeiro corte em vez de "Título do corte", quebra o título em linhas como o
  vídeo final e acompanha a rolagem da página. Tudo o que muda a imagem ficou junto em
  **Visual do corte**; remoção de pausas e efeitos foram para **Ritmo e efeitos**; barra
  de progresso, volume, .srt, idioma e modelo para **Saída e transcrição**. Opções que
  não valem no momento (pausa mínima sem remover pausas, pasta de sons sem efeitos,
  campos do outro tipo de título) ficam escondidas.
- Rótulos de seção em caixa alta agora são traduzidos no idioma inglês.

## [1.14.5] - 2026-10-26

### Corrigido

- Cortes, **Seguir a pessoa**: numa live com várias câmeras, a janela largava quem falava
  (andando com o microfone) e ia para quem estava parado atrás, ida e volta, ou para o
  tecladista e nucas detectadas por engano nas cenas da plateia. Agora quem fala é decidido
  pelo LR-ASD (IJCV 2025, licença MIT, 3,4 MB, na CPU), um modelo treinado para isso que
  olha a boca de cada rosto junto com o áudio, quadro a quadro. No vídeo de exemplo do
  TalkNet, quem fala ficou com nota +3,0 e os outros abaixo de -3. As trocas de câmera
  são detectadas pela cor (como o PySceneDetect) e cada cena é decidida sozinha; rosto
  que aparece menos de 0,5 s não conta; a troca de pessoa corta no momento em que a outra
  começa a falar. Cena em que ninguém fala: um rosto é seguido, um grupo que cabe na
  janela fica junto e pessoas espalhadas aparecem no quadro inteiro com fundo desfocado.
- Cortes, **Efeitos sonoros**: os sons não combinavam com o vídeo. O impacto tinha um grave
  quase no volume máximo, acima da própria voz, e a subida era um tom de ficção científica.
  Agora o volume de cada som (do app ou da sua pasta) é medido e fica de 8 a 14 dB abaixo
  da voz do corte, o impacto tem corpo audível no celular sem ronco, a subida virou um
  chiado que cresce (prato ao contrário) e o pop um toque seco. Todo som vem junto de algo
  na imagem, como num editor: o whoosh só numa emenda e os outros com o zoom rápido; com o
  zoom na ênfase desligado, só o whoosh fica. Dois sons nunca a menos de 3 s, e o texto
  pronto do plano da IA pede de 1 a 3 efeitos por corte.

## [1.14.4] - 2026-10-26

### Alterado

- Cortes, **Seguir a pessoa**: com mais de uma pessoa em cena, a câmera segue quem está falando,
  não o maior rosto. Cada rosto é acompanhado entre os quadros e o movimento da boca dele é
  comparado com o volume da voz; a boca que mexe no ritmo da fala vence. Vale quem mais falou
  no corte inteiro (a pessoa principal) somado a quem fala nos segundos em volta, então num
  diálogo a câmera troca de pessoa. A troca é um corte seco (sem panorâmica atravessando o
  quadro), só acontece quando a outra pessoa vence por 0,8 s e nunca antes de 2 s na atual.
  Num vídeo de teste com duas pessoas e a maior delas mexendo a boca fora do ritmo, a câmera
  ficou em quem falava em 93–97% do tempo (antes, 55–59%); num diálogo, 83% (antes, 33%).
  Continua tudo em CPU e sem modelo novo. O modelo Light-ASD também foi avaliado e, nestes
  vídeos, errou mais e deixava a análise duas vezes mais lenta.

### Corrigido

- Cortes, **Remover pausas**: o fim da fala era cortado (a última sílaba, o "s", a voz morrendo).
  O Whisper marca o fim da palavra cedo; agora o trecho só termina depois que o volume realmente
  cai (até 0,7 s além do fim marcado), com folga mínima de 0,28 s no fim (0,12 s no começo), sem
  invadir a fala seguinte. Cada emenda ganha uma rampa de volume de 25 ms, sem estalo.

## [1.14.3] - 2026-10-26

### Corrigido

- Plano da IA: colado do celular, do Word ou do chat da IA com aspas curvas (“ ”), o plano era
  recusado com "Não encontrei o plano". As aspas curvas agora viram retas antes da leitura.

## [1.14.2] - 2026-10-25

### Adicionado

- Cortes: campo **Plano da IA**. Uma linha de JSON compacto (`{"bx":1,"c":[…]}`) que uma IA de
  texto entrega depois de ler a transcrição preenche os cortes, os títulos e onde entra cada som e
  zoom. O app procura a palavra indicada no tempo exato do Whisper (o SRT só tem o tempo da frase),
  leva o whoosh para a emenda mais próxima e converte tudo para o vídeo já sem pausas. Formato e
  texto pronto para qualquer IA em `docs/PLANO-DA-IA.md`.
- Cortes: cinco sons (whoosh, pop, impacto, ding e subida), refeitos em estéreo com filtro que
  varia no tempo e reverb curto, e a opção **Seus sons**: uma pasta com arquivos chamados pelo
  tipo substitui os sons padrão.
- Cortes: **Altura do título**, no campo ou arrastando o título na prévia.

### Alterado

- A regra automática (sem plano) ficou mais contida: whoosh a cada 6 s no mínimo e uma ênfase a
  cada 8 s.

## [1.14.1] - 2026-10-25

### Adicionado

- Cortes: **Efeitos sonoros automáticos** (em Acabamento). Um "whoosh" entra nas emendas em que a
  fala muda de assunto (pausa removida de 1 s ou mais) e um "pop" nas palavras ditas com mais força
  (6 dB acima da mediana do corte, ou terminadas em "!"). Nunca dois whooshes a menos de 4 s, no
  máximo uma ênfase a cada 7 s e nada colado no começo ou no fim. Os sons são sintetizados pelo
  próprio app: nenhum arquivo de terceiros nem licença extra.
- Cortes: **Zoom na ênfase**, uma aproximação rápida (115%) na palavra enfatizada, que pode ser
  ligada junto ou separada dos sons.
- Atualização: a release passa a publicar no `SHA256SUMS.txt` o hash do executável principal de
  cada plataforma. Na mesma versão, se o executável instalado não conferir (corrompido, alterado ou
  de outra compilação), a faixa inferior oferece **Reinstalar** a versão oficial do GitHub, sem a
  opção de pular.

### Corrigido

- macOS: o `Info.plist` do app dizia versão 0.0.0 (visível em "Obter Informações"); agora traz a
  versão real.

### Observação

- Cópias do app no Mac até a 1.13.7 tinham a checagem de atualização desligada no código e sempre
  respondem "já está na versão mais recente". Nelas é preciso instalar a versão nova manualmente
  uma vez (DMG da página de releases); a partir da 1.13.8 a atualização pelo app funciona.

## [1.14.0] - 2026-10-25

Nova página **Cortes**: vídeos verticais com legenda palavra a palavra.

### Adicionado

- Página **Cortes** na barra lateral (Ctrl+5). A partir de um arquivo local ou de um link do
  YouTube, cada intervalo informado (início, fim e título opcional) vira um MP4 1080x1920. Num link,
  só os trechos são baixados.
- Remoção de pausas: o Whisper marca o tempo de cada palavra e os silêncios acima do limite
  escolhido (0,4 s a 1,2 s) saem do vídeo, emendando imagem e som juntos.
- Legenda de 1 a 4 palavras por vez com a palavra falada em destaque (maior e na cor escolhida) e
  título animado nos 2 primeiros segundos, gerados em ASS e gravados pelo próprio FFmpeg.
- Estilo da legenda na própria página: fonte, tamanho, cor do texto, cor de destaque, altura na
  tela e maiúsculas, com prévia em que dá para arrastar a legenda. As escolhas ficam salvas.
- Enquadramento **Seguir a pessoa (automático)**: num vídeo horizontal, a janela 9:16 aproxima e
  acompanha quem está em cena, como o reenquadrar do CapCut. Usa o detector de rostos YuNet
  (OpenCV Zoo, MIT, 230 KB, no onnxruntime que o app já leva) e, sem rosto, o movimento entre
  quadros; uma câmera virtual fica parada enquanto a pessoa está perto do centro, acompanha com
  aceleração e frenagem suaves quando ela anda e assenta quando ela para (mesma ideia do AutoFlip
  do Google). A posição muda a cada quadro, de pixel em pixel, sem trancos. Se a análise falhar, o corte sai centralizado. Continuam disponíveis o fundo
  desfocado e o corte no centro.
- Legenda com seis animações (destaque, só cor, karaokê, uma palavra por vez, grupo com pulo e
  sem destaque) e caixa escura opcional atrás do texto. A prévia usa um quadro do próprio vídeo.
- Acabamento opcional: duração do título (2, 3, 5 s ou o corte inteiro), zoom alternado nas
  emendas das pausas removidas, barra de progresso, volume em -14 LUFS e legenda também em `.srt`.
- A pasta de destino fica logo abaixo do vídeo de origem, e cada corte mostra a duração (ou o que
  está errado) enquanto é digitado.
- Arquivos só de áudio e vídeos sem som são recusados antes da transcrição, com o motivo; vídeos
  de celular com marca de rotação são tratados como verticais no "seguir a pessoa"; um corte
  cancelado não deixa MP4 pela metade; o título desce quando a legenda está no alto.
- Histórico: cada corte pronto, cada resultado da aba Ferramentas e cada vídeo com legenda
  incorporada entram na aba **Histórico**, com ações para abrir, legendar e fazer outros cortes do
  mesmo vídeo.
- Sem dependências novas além do modelo YuNet: usa o FFmpeg e o Whisper que o app já baixa. A transcrição roda no
  processo isolado do legendador (CUDA com volta para a CPU) e a montagem tenta a GPU antes da CPU.

### Alterado

- O atalho Ctrl+5 passa a abrir **Cortes**; **Histórico** foi para Ctrl+6.

## [1.13.10] - 2026-10-23

Falsos erros: combinações de formato que o yt-dlp e o FFmpeg recusam.

### Corrigido

- Download de áudio em WAV com "Embutir capa" ligado terminava com erro na fila
  ("Postprocessing: Supported filetypes for thumbnail embedding are: ..."): o WAV não tem onde
  guardar capa e o yt-dlp abortava o pós-processamento. A capa agora só é pedida nos formatos que
  a aceitam (MP3, M4A, Opus, FLAC, MP4 e MKV); em WAV, WebM e "Manter original" o download segue
  sem capa e sem falso erro.
- Ferramentas: **Remux** e **Corte rápido** falhavam em todo MP4 baixado pelo próprio app. Os capítulos
  embutidos viram uma faixa de dados e a legenda embutida é mov_text, e o MKV recusa as duas. Agora a
  faixa de dados fica de fora (os capítulos continuam) e a legenda vira SRT.
- Contêiner WebM: vídeo em H.264 (de outros sites, ou com "Preferir H.264") fazia a junção falhar. Agora
  vai para MKV.
- Contêiner MP4 e MKV: o `--remux-video mp4>mp4` só valia para origem MP4, então um vídeo que vinha
  como arquivo WebM único continuava WebM (e falhava ao embutir a capa). O WebM único agora vai para
  MKV, que aceita qualquer codec dele; os demais formatos vão para o contêiner escolhido.
- Conversão na GPU de um `.webm` para H.264/HEVC sempre "falhava" (o WebM não aceita esses codecs). A
  saída agora é `.mkv`.
- Playlist com um item privado ou removido aparecia inteira como erro, e os arquivos baixados não iam
  para o histórico nem para a transcrição. Agora ela termina com aviso e lista o último erro.

## [1.13.9] - 2026-10-20

Auditoria de paridade entre Windows, macOS e Linux.

### Corrigido

- Linux: o `.deb` e a versão portable eram compilados no Ubuntu 24.04 e exigiam glibc 2.38/2.39;
  no Ubuntu 22.04 e no Debian 12, que o README cita como suportados, o app não abria. A build passa
  a ser feita no Ubuntu 22.04, e o CI falha se alguma biblioteca do pacote pedir glibc mais nova que
  a do Debian 12. O pacote empacotado também passa pelo mesmo autoteste do Windows e do Mac.
- Linux: navegador e gerenciador de arquivos abertos pelo app ("Abrir pasta", links) herdavam as
  bibliotecas e os plugins Qt de dentro do pacote (`LD_LIBRARY_PATH`, `QT_PLUGIN_PATH`) e podiam
  fechar ao abrir. Os programas externos passam a receber o ambiente original do sistema.
- Linux: "Verificar atualizações" dizia "você já está usando a versão mais recente" mesmo com versão
  nova. O app agora avisa e o botão **Abrir download** leva à página da versão (o `.deb` continua
  instalado pela pessoa).
- macOS e Linux: o `cookies.txt` importado nascia legível por outros usuários da máquina até ser
  restringido; agora a pasta de cookies é `0700` e o arquivo é criado `0600`.
- macOS e Linux: a pasta padrão de downloads era sempre `~/Videos`. No Mac passa a ser `~/Movies`
  e no Linux a pasta de vídeos do sistema (`~/Vídeos` em português), lida do `user-dirs.dirs`.
  Só vale para quem ainda não escolheu uma pasta.

### Segurança

- certifi 2026.7.22 → 2026.10.19 nas três plataformas (alerta GHSA-6q48-6c7w-9gw2, apontado pelo
  `pip-audit` do CI). É o pacote de autoridades certificadoras usado para baixar yt-dlp, FFmpeg,
  Deno e as atualizações do app.

### Alterado

- macOS e Linux: o yt-dlp passa a ser a distribuição oficial em pasta (`yt-dlp_macos.zip`,
  `yt-dlp_linux.zip`), como no Windows. Cada análise e download abre o yt-dlp cerca de 2x mais
  rápido (0,6 s contra 1,2 s medidos no Linux), porque ele não se descompacta mais a cada chamada.
  No Linux ele deixa de depender do Python do sistema e ganha curl_cffi (imitação de navegador),
  mutagen (capa em áudio opus/m4a/flac) e secretstorage (cookies do Chrome pelo chaveiro). A troca
  é automática na próxima checagem; sem rede, o executável antigo continua valendo.
- Todas as plataformas: a pasta do yt-dlp (45 a 90 MB) não é mais re-hasheada inteira a cada
  abertura. Tamanho e data são conferidos sempre e o SHA-256 completo a cada 24 h, como já era com
  FFmpeg e Deno.
- CI: as três plataformas instalam o yt-dlp como o app faz e confirmam que ele abre com as
  dependências opcionais (`scripts/check_runtime_tools.py`).

## [1.13.8] - 2026-10-18

### Corrigido

- Mac: a verificação de atualização dizia "você já está na versão mais recente" mesmo com versão
  nova publicada, porque o atualizador só existia para o Windows. Agora o app do Mac encontra a
  versão nova, baixa o `.zip`, confere o SHA-256 e a assinatura do `.app` (`codesign`) e, ao
  fechar, troca o aplicativo e o reabre. Se a troca falhar, a versão anterior volta para o lugar.
  Quem está na 1.13.7 ou anterior precisa baixar esta versão manualmente uma única vez; dela em
  diante a atualização é automática.
- Mac: quando o app não pode ser substituído (aberto direto da imagem de disco ou da pasta de
  Downloads, sem permissão de escrita), o aviso explica o motivo antes de baixar.
- Windows: o "X" da tela de preparação era maior e mais grosso que os botões de minimizar e
  maximizar. Ela passa a usar os mesmos três botões da janela principal.

### Alterado

- Mac: as janelas usam os botões nativos do sistema (fechar, minimizar e zoom coloridos), no lugar
  dos botões no estilo Windows.
- Releases: os hashes dos pacotes do Mac e do Linux entram no `SHA256SUMS.txt` assinado.

## [1.13.7] - 2026-10-18

### Corrigido

- Mac (Apple Silicon): a barra do legendador ficava parada em 14% até o fim da transcrição, que
  parecia travada. O `mlx_whisper` só devolve o resultado depois de processar o áudio inteiro; o app
  agora acompanha o avanço real dele a cada janela de 30 s, de 16% a 90%. Pausar e cancelar passam a
  valer no meio da transcrição, e não só no fim.
- Mac: os pesos do modelo MLX são carregados na etapa "Carregando Whisper", e não dentro da
  transcrição, para a barra começar a andar logo no início.

### Alterado

- Legendar: o texto de andamento mostra a posição no áudio ("Transcrevendo: 12:30 de 47:26 do
  áudio") e, depois do primeiro minuto de áudio, o tempo restante estimado pelo ritmo real da
  máquina. Vale para MLX, CUDA e CPU.

## [1.13.6] - 2026-10-13

### Adicionado

- Baixar → "Nome personalizado": define o nome do arquivo (sem a extensão) antes de iniciar o
  download. Vazio, vale o modelo das Configurações; não vale para playlists. Caracteres inválidos
  viram `_` e o "Nome previsto" já mostra o resultado.

### Alterado

- Legendas: o ponto final que o Whisper coloca onde a fala continua (pausa curta, frase que
  começa com "se"/"quando" sem fechar, palavra que não termina a ideia) vira vírgula ou some.
  A palavra seguinte volta a minúscula quando é comum ("mas", "eu", "para"…); nomes próprios
  não são alterados. Ponto em pausa longa, `?`, `!` e reticências ficam como estavam.

## [1.13.5] - 2026-10-04

### Corrigido

- macOS: o app abria como "está danificado e não pode ser aberto". O passo que registra o protocolo
  `baixador://` altera o `Info.plist` depois que o PyInstaller assinou o bundle, o que invalidava a
  assinatura. O workflow agora assina o `.app` em ad-hoc (gratuito) depois dessa edição e valida com
  `codesign --verify --deep --strict` antes de empacotar. Sem notarização, o macOS ainda mostra o aviso
  comum de desenvolvedor não identificado.
- macOS: no app empacotado o legendador caía sempre no CPU com `[load_npz] Input must be a zip file`:
  os arquivos de dados do `mlx_whisper` (`mel_filters.npz` e os vocabulários) não entravam no `.app`.
  O build agora usa `--collect-all mlx_whisper` e falha se algum deles faltar no bundle.

## [1.13.4] - 2026-10-04

### Corrigido

- Mac (Apple Silicon): o legendador caía sempre no fallback CPU int8 porque o `mlx_whisper` chama
  `ffmpeg` pelo PATH e o FFmpeg do app fica na pasta de binários. O WAV 16 kHz mono já gerado pelo
  app agora é lido em memória e entregue ao MLX, que volta a usar a GPU integrada.
- Mac: o MLX recebia `beam_size`/`patience` do perfil de qualidade e abortava com "Beam search decoder
  is not yet implemented"; essas opções agora são removidas só para o MLX.
- Mac: o fallback em CPU falhava com `open() got an unexpected keyword argument 'metadata_errors'`
  (PyAV antigo no ambiente, chamado pelo faster-whisper); no macOS o WAV do app é entregue em memória.
- Legendador: o processo auxiliar passa a enxergar o FFmpeg do app no PATH, o faster-whisper recebe o
  áudio já preparado em memória (sem redecodificar com o PyAV) e as falhas comuns (FFmpeg ausente,
  disco cheio, sem rede/certificado, componente desatualizado, pouca memória) viram mensagens claras,
  mantendo o detalhe técnico entre parênteses.
- Dependências: `av==18.1.0` agora é fixado nos `requirements*.txt` (e o comentário nos locks). O
  faster-whisper exige um PyAV recente; instalar pelo `.txt` sem a versão podia trazer um `av` antigo.
- O fallback MLX → CPU passou a registrar no log o tipo da exceção e o rastreio (antes só a
  mensagem da interface, que não chegava ao pacote de diagnóstico).

## [1.13.3] - 2026-10-02

### Corrigido

- Legenda queimada (Ferramentas → Legendas no vídeo) falhava quando o caminho tinha aspa simples
  (`It's.srt`, pasta `João's`): o caminho agora segue os dois níveis de escape do FFmpeg, sem aspas.
- Logs: a redação de segredos deixava passar o token depois de `Bearer`/`Basic`, os pares seguintes
  de `Cookie: A=1; B=2`, o valor de `--add-headers`, `access_token`/`refresh_token`/`password`/
  `client_secret` na URL e `po_token`/`visitor_data` em `--extractor-args`.
- Miniatura: um redirecionamento (302) para `127.0.0.1` ou rede local contornava a checagem de
  endereço privado, que só valia para a primeira URL. Cada redirecionamento é conferido de novo.
- Atualizador: conexão cortada no meio (`IncompleteRead`, reset) escapava como erro cru; agora vira
  o aviso normal e o `.part` é apagado.
- Configurações: `null` em campos de texto virava a string `"None"` (`--proxy None`) e `true` em
  campo numérico virava 1.
- Trecho: `1:30,5` (vírgula do teclado brasileiro) valia 0 s; `nan`, `inf` e negativos agora valem 0.
  `out_time=N/A` do FFmpeg deixava de ser ignorado e podia contar como nova passada na barra de progresso.
- Cookies: importar um site `.co.uk`/`.com.br`-like apagava os cookies de todos os outros do mesmo sufixo.
- Histórico: um item com tipo errado (`"when": "ontem"`) derrubava a página; `history_limit` negativo
  apagava a lista inteira.
- Legendas: com palavras longas, o grupo cabia em 2×o limite de caracteres mas o quebrador gerava 3
  linhas e a terceira era cortada (texto perdido no SRT/VTT/ASS). O grupo agora fecha antes de estourar.
- Filtro de alucinações: "musical", "precisos" e "compartilhei" eram descartados por conterem
  "music", "risos" e "compartilhe"; a comparação agora é por palavra inteira.
- Fila: o mesmo link como vídeo único e como playlist (ou com outros itens da playlist) era tratado
  como repetição e recusado.
- Lote e importação de lista: `)` que faz parte do link (`…/Foo_(bar)`) era cortado; a extração
  ficou num só lugar (`security.extract_urls`).
- Processo de transcrição avulso devolvia a mensagem crua do motor em vez da amigável.
- Mensagens de erro: `[WinError 53]` (caminho de rede) aparecia como "sem permissão" e `[Errno 360]`
  como "caminho longo demais", porque o código era procurado como prefixo de texto; agora o número é
  comparado inteiro (5, 28, 36, 112, 206).
- Tamanhos: 1023,6 KB aparecia como "1024 KB" (e 1 GB menos 1 byte como "1024.00 MB").
- Limite de banda: um valor que o yt-dlp recusa (`abc`) fazia todo download falhar com "invalid rate
  limit". Configurações agora recusa o valor com aviso e o download ignora um valor inválido já salvo.
- Preparação do ambiente: `tools_state.json` com JSON válido que não é objeto (`[]`, `null`) derrubava
  a preparação com `AttributeError` em toda abertura; agora o estado volta vazio e é regravado.
- Argumentos do extrator: um valor que o yt-dlp recusa (`lixo`, sem `extrator:`) fazia toda análise e
  todo download falhar com "wrong --extractor-args form". Configurações recusa o valor com aviso e
  análise/download ignoram um valor inválido já salvo.

### Testes

- `tests/test_integracao_real.py`: valida toda combinação de opções de `build_args` com o parser do
  próprio yt-dlp e executa cada ferramenta de mídia com o FFmpeg real (caminhos com `'`, `[ ]`, `,`, `;`).
- `tests/test_bugs_caca_1132.py` e `tests/test_bugs_rodada2.py`, `tests/test_bugs_rodada3.py`, `tests/test_bugs_rodada4.py`: regressões dos itens acima.

## [1.13.2] - 2026-09-30

### Adicionado

- Avisos de erro por plataforma (`sites.py`): Instagram, X, TikTok, Facebook, Reddit, Vimeo e
  outros. Pedido de login e limite de requisições citam o site certo em vez de falar do YouTube.

### Alterado

- Configurações → Rede e desempenho → "Partes simultâneas do trecho" (1 a 8, padrão 4; 1 desliga): 
  antes eram sempre até 6. Do 5 em diante a tela avisa que o YouTube pode bloquear o IP por um tempo.
- Nome do arquivo: seletor de modelos (Título [id], Plataforma - data - título [id] e Só o título) 
  e título do Facebook sem o contador de views.
- Story do Instagram: avisa na hora que exige login (cookies.txt ou Firefox) e a análise usa o story do link, 
  em vez de mostrar formatos de outro story.
- Configurações → cookies.txt vale para vários sites: a validação lista quais o arquivo cobre, o passo a passo
  inclui o Instagram e importar outro site mescla com o que já estava no app.
- PySide6 6.11.2, faster-whisper 1.2.1, huggingface-hub 0.36.2, certifi, send2trash 2.1.0 e
  setuptools 84; locks regenerados. `update_locks.sh` passou a resolver o macOS 14 (o mlx não
  tem wheels para o 13) e o manylinux_2_34 do PySide6 no Linux.
- VAAPI escolhe o primeiro `/dev/dri/renderD*` que o usuário consegue abrir e, sem permissão,
  orienta a entrar no grupo `render`.

## [1.13.1] - 2026-09-30

### Alterado

- A aba Ferramentas agora é um hub como Configurações: os cartões abrem a página de cada
  ferramenta (`Ferramentas › Nome`) com o arquivo, os ajustes e o botão de processar. Ferramentas
  sem ajustes (remover áudio, limpar metadados) não mostram a seção vazia, e não dá para abrir
  outra ferramenta enquanto uma tarefa está rodando.

## [1.13.0] - 2026-09-30

### Adicionado

- Nove ferramentas novas na aba Ferramentas: **ajustar velocidade** (0,25x a 4x, com áudio
  corrigido por `atempo`), **girar ou espelhar**, **remover áudio**, **nivelar volume**
  (`loudnorm`, alvos -16/-14/-23 LUFS, imagem copiada sem recodificar), **converter formato**
  (MP4/H.264 ou WebM/VP9), **criar GIF** (paleta própria, até 30 s), **capturar imagem**
  (PNG/JPG/WebP), **extrair legendas** (SRT/ASS/VTT, primeira faixa de texto; recusa cedo
  arquivos sem legenda ou só com legenda em imagem) e **limpar metadados**.
- "Extrair áudio" ganhou M4A, Opus, FLAC e WAV além de MP3.
- Os cartões agora ficam em cinco grupos, e cada ferramenta é só dados (`OPERATIONS`): novas
  ferramentas não exigem mudar o layout.

### Alterado

- O codec das ferramentas de áudio, imagem, legenda e conversão vem da extensão do destino, então
  renomear o arquivo de saída nunca gera um comando incoerente.
- Ferramentas em arquivos sem a faixa necessária (imagem num MP3, por exemplo) mostram uma
  mensagem em português em vez do erro do FFmpeg.
- Linhas ocultas do bloco de ajustes levam o divisor junto (`InsetGroup.set_row_visible`), sem
  linhas soltas; a lista de opções acompanha a largura do item mais longo.
- Textos das Ferramentas (cartões, ajustes, botões) traduzidos para o inglês, incluindo três
  botões antigos que ficavam em português; um teste falha se surgir texto sem tradução.

## [1.12.8] - 2026-09-29

### Corrigido

- Erros do FFmpeg chegam em português: "ffmpeg exited with code 3199971767" (dados inválidos
  na entrada), disco cheio, caminho longo demais e falta de permissão têm mensagem própria; as
  Ferramentas e a conversão pós-download também passam pelo tradutor de erros.
- Falhas do servidor de transcrição sem traceback deixam a mensagem no `crash.log` (antes,
  uma linha em branco).
- Foco inicial no campo do link (antes, no botão de minimizar: Enter ou Espaço minimizava a
  janela). Botões de moldura não recebem foco.
- Descrições das Ferramentas quebram em até 3 linhas em vez de terminar em "…".
- Botões desabilitados ficam esmaecidos (Pausar tudo / Limpar finalizados com a fila vazia).
- "container" virou "contêiner" na interface; a página Baixar não repete mais o mesmo termo
  no título e no subtítulo.

### Alterado

- Configurações: o caminho da subpágina ("Configurações › Rede e desempenho") segue o estilo do
  Windows: pai em cinza, seta forte e item atual em negrito.
- Lint: ruff com as regras B (bugbear), UP e SIM, e pyright em modo básico no CI (só erros
  novos). O B023 apontou um caso real na transcrição (id do item lido da variável do laço).
- A cache do Nuitka saiu da pasta de dados do app para `%LOCALAPPDATA%\BaixadorYtdlp-build`.
- `transcription.py` dividido: pesos e cache em `models.py`, processos em `transcription_server.py`.
- Testes e scripts de captura rodam num perfil descartável (`BAIXADOR_YTDLP_DATA_DIR`).
- Actions do job de release atualizadas: `download-artifact` 8.0.1 e `attest-build-provenance` 4.2.2
  (esta é a primeira release que as usa).

## [1.12.7] - 2026-09-29

### Corrigido

- O problema no DaVinci era o **VP9 dentro de MP4**, não o codec (testado: VP9 em MKV, AV1 em
  MP4 e H.264 abrem inteiros; VP9 em MP4 abre com partes "Media Offline"). Por isso a 1.12.6
  limitar os trechos a H.264 1080p foi desnecessário e custava resolução. Agora o app volta a
  baixar a melhor qualidade (VP9 até 4K) e, quando o arquivo é VP9 em MP4, troca o contêiner
  para **MKV sem recodificar** (1 s para 20 min de vídeo; qualidade intacta). Nova opção em
  Configurações → "Trocar VP9 em MP4 por MKV" (ligada). "Priorizar compatibilidade (H.264)"
  volta a vir desligada. Medido: 20 min em 1440p, em partes paralelas, em 47 s, 36.000 quadros
  exatos e sem erro de decodificação.

## [1.12.6] - 2026-09-29

### Corrigido

- Trechos do YouTube abriam no DaVinci Resolve com partes "Media Offline". Os primeiros
  60 s do arquivo eram idênticos, pacote por pacote, a um download sem nenhuma emenda:
  o problema era o VP9 1440p do HLS (o app escolhia o melhor formato), não a junção.
  Confirmado no DaVinci: o VP9 falha; H.264 (HLS ou DASH, com ou sem emendas) abre.
  Trechos agora preferem H.264 (1080p, o formato que qualquer editor abre). "Priorizar
  compatibilidade (H.264)" passa a vir ligado em instalações novas, e o texto da opção
  cita os editores. Quem quiser VP9/AV1 desliga a opção nas Configurações.
- Nas emendas do trecho paralelo, o último quadro de cada parte deixou de se repetir.

### Adicionado

- Conversão e cortes acelerados também em **Intel Quick Sync** (H.264, HEVC e AV1; iGPU
  e Arc, Windows e Linux) e **VAAPI** (AMD e Intel no Linux). Um backend só aparece se
  uma codificação real de 1 quadro passar na sua máquina; senão, tudo segue na CPU.
- A conversão pós-download decodifica na GPU (`-hwaccel qsv`/`vaapi`, além do CUDA e do
  VideoToolbox que já existiam) e repete sem isso se a GPU recusar a mídia.
- Ferramentas de vídeo com VAAPI enviam os quadros à GPU depois dos filtros; o fundo
  desfocado dos Shorts (grafo complexo) continua na CPU nesse backend.
- O NVENC, o AMF e o VideoToolbox seguem como antes (verificado com uma compactação real).
  QSV e VAAPI não puderam ser testados em hardware: cobertos por testes dos argumentos.

## [1.12.5] - 2026-09-29

### Corrigido

- Legendar no Windows falhava com "O motor de transcrição encerrou inesperadamente"
  nas versões 1.12.3 e 1.12.4 (build Nuitka): o processo do servidor de transcrição
  usava `importlib.metadata` como atributo do pacote `importlib`, que não existe no
  processo filho do Nuitka. Agora o módulo é importado direto. Isso também quebrava o
  fluxo "Baixar e legendar". O autoteste da build passou a iniciar o servidor de
  transcrição como o app faz, então essa queda derruba a build em vez de chegar ao usuário.
- O instalador exige Windows 10 ou mais novo de 64 bits e diz isso com clareza, em vez
  de abrir uma instalação que não funcionaria em 32 bits.

### Alterado (CI e releases)

- A release deixou de incluir um `baixador-ytdlp.exe` solto (o job de publicação baixava
  a pasta inteira do app portátil, 1,4 GB, só para atestar e listar arquivos). O app
  portátil já sai no ZIP.
- Workflows: uma execução por ref (PR novo cancela o anterior, main/tag nunca), tempo
  máximo por job, commits só de documentação não disparam build, checkout sem credenciais
  persistidas, valores de etapas passados por variáveis de ambiente (sem injeção de
  template), artefatos com retenção de 7 dias, `actionlint` e `zizmor` no CI e
  análise CodeQL do Python (semanal e em cada push/PR).

## [1.12.4] - 2026-09-29

### Adicionado

- Trechos longos (10 min ou mais) de vídeos do YouTube são baixados em até 6 partes
  paralelas e emendados sem recodificar. Medido em uma live: 82 min em 2 min 25 s
  (1.12.3: 10,5 min; antes: mais de 40 min pelo formato comum). As emendas são
  alinhadas aos quadros-chave (uma sonda de 1 s por emenda), sem repetir nem pular
  imagem. Se qualquer parte falhar, o download volta ao processo único.
  Nesses trechos capa, metadados e capítulos não são embutidos, e o modo com
  SponsorBlock ou legendas junto continua no processo único.

## [1.12.3] - 2026-09-29

### Corrigido

- Baixar só um trecho no YouTube ficou muito mais rápido. O corte pelo formato
  DASH comum passa por uma única conexão do FFmpeg (~2x o tempo real: 82 min de
  live levariam mais de 40 min). Agora o app prefere o formato HLS equivalente,
  buscado por segmentos (~9x o tempo real medido: 82 min em ~10 min; 60 s em
  5 s). Com um formato escolhido na tabela, usa o HLS de mesma resolução, FPS e
  codec; sem HLS equivalente, cai para o formato escolhido.
- O botão "Verificar agora" da versão do aplicativo voltou; o card de componentes
  ficou com "Verificar componentes".
- O FFmpeg deixou de ser baixado a cada checagem: a release "latest" do BtbN é
  reenviada todo dia e o app comparava ID/data. Agora só um ramo estável mais
  novo (ex.: n9.0 → n9.1) conta como atualização.
- O texto do cookies.txt passou de "recomendado" para "só se o YouTube pedir": o
  bloqueio de robô é intermitente e temporário, e continua sendo o caminho
  recomendado pelo yt-dlp quando aparece.

### Alterado

- O Windows volta a ser compilado com Nuitka (1/70 detecções no VirusTotal contra
  3–4/71 do PyInstaller). O autoteste caía com falha de segmentação no
  `import onnxruntime` porque o pacote levava um `msvcp140.dll` 14.29, mais antigo
  que o exigido pelo onnxruntime 1.30; `scripts/refresh_vc_runtime.ps1` troca as
  DLLs do runtime C++ pelas mais novas antes do autoteste. PyInstaller segue como
  contingência (`build.ps1 -Packager PyInstaller`).
- Compilação bem mais rápida: 493 arquivos C em vez de 1.172 (sem o `pip`, usado só
  no modo de desenvolvimento, e sem as partes do `onnxruntime` que o app não usa),
  com a cache do ccache guardada entre execuções no GitHub Actions.
- README repaginado, com capturas de tela, e guias atualizados.

## [1.12.2] - 2026-09-29

### Corrigido

- Baixar só um trecho usa apenas o `--download-sections` do yt-dlp, sem o seletor HLS
  e o `-S proto:m3u8` da 1.12.1. O corte segue sem recodificar e sem
  `--force-keyframes-at-cuts`.
- Build do Windows com PyInstaller mantida nesta versão.

## [1.12.1] - 2026-09-28

### Correções

- Recortes de vídeo baixam apenas o intervalo solicitado sem recodificar todos
  os quadros. O início pode variar até o quadro-chave próximo.
- Recortes do YouTube dão preferência a HLS, com correspondência de resolução,
  taxa de quadros e codec quando o usuário escolhe um formato específico.

## [1.12.0] - 2026-09-28

### Novidades desta rodada

- Pausar e retomar cada download ou toda a fila, mantendo os arquivos `.part` e
  o estado pausado entre sessões.
- Perfil pronto para baixar, gerar legenda e incorporá-la como faixa; seleção
  de capítulo para preencher o intervalo do download.
- Ferramentas mais compactas, com arquivo de origem no topo e ação indisponível
  até escolher um arquivo.
- Configurações com checagem manual unificada, último horário visível, estado
  real do Whisper, ícones distintos e troca de canal do yt-dlp na próxima checagem.
- Mensagens de erro, avisos e estados da fila traduzidos para inglês.
- yt-dlp para Windows instalado a partir do ZIP oficial em pasta, com SHA-256
  do artefato e verificação de integridade dos arquivos extraídos.
- `ffplay.exe` removido da instalação e de versões anteriores.
- Validação de GPU separada da compilação; pode ser exigida com `-ValidateGpu`.

### Corrigido

- A transcrição volta a usar a GPU NVIDIA. O CTranslate2 4.8.2 exige cuDNN 9, mas
  o instalador embutia cuDNN 8 e a transcrição caía para CPU. Agora o cuDNN é o
  9.10.2.21, a mesma versão que acompanha o CTranslate2, e cuBLAS/cudart 12.8
  cobrem também as RTX 50.
- A interface não mostra mais "CUDA" quando o conjunto embutido é incompatível; o
  autoteste da build carrega o cuDNN de verdade e falha se ele não casar.
- Baixar usa sempre o link analisado. Editar ou colar outro link descarta a
  análise anterior em vez de baixar o novo endereço com o formato do antigo.
- Atualizar o aplicativo pergunta antes quando há tarefas ativas: instalar ao
  fechar ou agora, pausando os downloads. A instalação fecha pelo caminho normal,
  salvando fila e ajustes, e não fica mais presa na bandeja.
- Fechar o aplicativo também avisa sobre transcrições e ferramentas em andamento.
- A duração máxima dos blocos de legenda passa a valer no modo por palavra.
- A limpeza de texto das legendas preserva %, $, /, &, @, #, + e aspas
  tipográficas ("24/7" não vira mais "247").
- Mensagens de erro corretas para restrição de idade, bloqueio regional e
  servidor instável, que antes apareciam como pedido de robô ou vídeo removido.

- Se a conversão por GPU falhar depois de um download bem-sucedido, o item
  conclui com aviso e mantém o arquivo original, em vez de virar erro.
- Cancelar uma transcrição não se perde mais na troca de item, e um resultado
  enviado logo antes de o motor encerrar não vira mais falha.
- Esc pede confirmação antes de cancelar uma transcrição ou uma ferramenta.
- O campo de link ocupa a linha inteira em janelas estreitas.

### Alterado

- Instaladores baixados em sessões anteriores são apagados automaticamente.
- Aviso de atualização com tamanho, botão "Novidades", "Lembrar depois" (só
  nesta sessão) e "Pular versão"; antes "Agora não" pulava a versão para sempre.
  Com o app aberto por dias, uma nova checagem acontece a cada 3 horas.
- A atualização instala sem refazer o assistente (só a janela de progresso) e
  reabre o aplicativo ao terminar.
- Fila na ordem de chegada, com tipo, formato e pasta em cada item; itens
  finalizados saem um a um; botão para tentar de novo todas as falhas.
- Avisos iguais viram um só com contador e aparecem no canto inferior direito,
  sem cobrir o link e o botão Analisar.
- A página Baixar mostra só as opções que valem no modo atual.
- Releases locais com hashes, assinatura Ed25519 e notas extraídas do
  CHANGELOG (`scripts/prepare_release.py`).
- Análise mais rápida: sem a execução extra do yt-dlp para testar cookies, e a
  lista da playlist vem junto da análise ("Escolher itens" abre na hora).
- Em PCs sem GPU, as Ferramentas não testam os encoders de novo a cada uso.
- "Caber em um limite" usa sempre x264, com mais qualidade por byte.
- Checagem de espaço soma o áudio de qualidades só de vídeo e considera todos
  os itens da playlist.

### Adicionado

- O modelo do Whisper sai da memória da GPU após 10 minutos ocioso, e o botão
  "Liberar memória" faz isso na hora.
- Legendar aceita vários arquivos ou uma pasta de uma vez, com "Esvaziar fila".
- Ferramentas: "Corte rápido, sem reencodar" (instantâneo, sem perda, corta no
  quadro-chave).
- Progresso de trecho sem hora final e sem voltar a 0% na faixa de áudio.

## [1.10.10] - 2026-09-28

### Corrigido

- Baixar só um trecho usa o FFmpeg do yt-dlp sem forçar CUDA/NVENC, AMF ou
  VideoToolbox. O progresso do recorte continua aparecendo na fila.

## [1.10.9] - 2026-09-27

### Adicionado

- Ferramentas de vídeo (recortar, reduzir tamanho, caber em um limite, versão
  vertical e legenda gravada) usam NVENC, AMF ou VideoToolbox quando disponíveis,
  com nova tentativa automática na CPU.

### Alterado

- Um link já baixado pode ser baixado de novo após confirmação; a cópia recebe
  um número no nome. O arquivo de histórico de IDs do yt-dlp deixou de ser usado.

## [1.10.8] - 2026-09-27

### Corrigido

- Recortar trecho agora reencoda o intervalo com FFmpeg, começando no quadro
  selecionado e encerrando na duração solicitada, mesmo fora dos quadros-chave.
- Intervalos cujo fim não vem depois do início são rejeitados antes de processar.

### Alterado

- Na aba Legendar, pausar e cancelar aparecem durante a execução. O botão
  principal passa a indicar que adiciona outra mídia à fila.

## [1.10.7] - 2026-09-27

### Alterado

- Configurações agora abre em oito cartões com resumos dos valores atuais; cada
  assunto tem sua própria página, com retorno claro para a visão geral.
- Busca direta pelas opções, inclusive sem acentos, que abre a opção na seção
  correspondente. A grade passa para uma coluna em janelas mais estreitas.
- Download, rede, extras, cookies, GPU, aparência, atualizações e opções
  avançadas seguem a organização da referência visual fornecida.
- O modelo do nome do arquivo mostra uma prévia compacta na mesma linha.

## [1.10.6] - 2026-09-27

### Alterado

- Configurações divididas em sete áreas selecionáveis, com descrições curtas e
  posição de rolagem preservada durante a navegação.
- Ajustes de codec, preset, qualidade e substituição aparecem apenas quando
  a conversão após baixar está ligada.
- A interface parte integralmente do código da versão 1.10.4.

## [1.10.4] - 2026-09-25

### Corrigido

- A distribuição Nuitka inclui todos os dados do `faster-whisper`, incluindo os
  dois modelos ONNX do VAD; o build agora confere os arquivos reais instalados
  antes de gerar o instalador.
- Erros de arquivo, VAD ou ONNX não são mais tratados como indisponibilidade de
  CUDA. Arquivos internos ausentes orientam a reinstalação em vez de disparar
  um fallback enganoso para CPU.
- Download de modelos aquece a detecção de symlinks do Hugging Face e repete o
  caso transitório `WinError 1314` no Windows.
- Falta de memória na GPU tenta `int8_float16` antes da CPU; se ainda falhar,
  a GPU é tentada de novo no próximo item. Outras falhas CUDA passam a informar
  claramente que a sessão continuará em CPU até reiniciar.
- Caminhos de recursos, modo portátil, DLLs CUDA e ferramentas embarcadas usam
  uma única abstração compatível com PyInstaller e Nuitka.

### Adicionado

- Self-test oculto do executável, executado pelo build local e pelo CI: valida
  dependências, assets do VAD, PyAV, CUDA disponível e um processo `spawn`.

## [1.10.0] - 2026-09-23

Primeira parte da fase 2.0 do roadmap.

### Adicionado

- Protocolo `baixador://` (Windows, Linux e macOS) e favorito "Enviar para o
  baixador"; o link recebido só é analisado, nunca baixado sem confirmação.
- Seletor de itens de playlist com busca, marcação em massa e `--playlist-items`.
- Canal nightly do yt-dlp nas configurações, com a mesma verificação SHA-256.
- Ferramenta "Caber em um limite" (8 a 100 MB) com bitrate e resolução calculados.
- Versão vertical com fundo desfocado (padrão) ou barras pretas.
- Exportação de diagnóstico em ZIP com logs e configurações redigidos.

## [1.9.0] - 2026-09-23

### Segurança

- `SHA256SUMS.txt` das releases assinado com Ed25519 (`scripts/release_signing.py`);
  o atualizador confere a assinatura com as chaves públicas embutidas em
  `RELEASE_PUBLIC_KEYS` e recusa releases sem `.sig` quando há chave configurada.
  O segredo fica num *environment* protegido (`release`) do GitHub.
- Dependências instaladas por locks com hashes (`requirements-*.lock`,
  `--require-hashes`), inclusive as transitivas; job semanal confere a sincronia
  com os `requirements*.txt` e o `pip-audit` roda sobre os locks.
- SBOM CycloneDX gerado do ambiente real de cada build (em venv separado) e
  textos integrais das licenças (`THIRD_PARTY_LICENSES.md`) no instalador.
- Instância única com `QLockFile` e canal restrito ao usuário; no Linux, socket em
  `$XDG_RUNTIME_DIR`.
- Miniaturas só por HTTPS, sem rede local, e apenas JPEG/PNG/WebP; redação de
  logs cobre senhas de proxy com `/` e tracebacks.
- Telemetria do Hugging Face desligada.

### Adicionado

- Modo rápido do Whisper em GPU (`BatchedInferencePipeline`) e opção de economia
  de VRAM (`int8_float16`).
- Gerenciador de modelos migra os pesos de versões anteriores e mostra as sobras.
- Job semanal que confere os assets do FFmpeg (BtbN) e do Deno.

### Corrigido

- Legenda ASS/karaokê incorporada em MKV sem perder o estilo, com idioma e faixa
  padrão marcados.
- Deno fica na maior versão 2.x publicada, sem travar quando sair a 3.x.
- Consultas ao GitHub com `ETag` (respostas 304 não gastam o limite anônimo).

### Alterado

- Whisper volta a usar a sequência de temperaturas de fallback e blocos de VAD de 20 s.

## [1.8.1] - 2026-09-23

### Corrigido

- Faixas claras nas bordas da janela: a geometria salva passa a ser restaurada
  depois que a moldura nativa está pronta e a janela é redesenhada por inteiro
  após mudanças de moldura, estado ou monitor. O Mica fica desligado por padrão.
- Cancelar no Windows encerra a árvore inteira de processos (Job Object), sem
  deixar o yt-dlp, o FFmpeg ou o Deno rodando em segundo plano.
- Binário alterado fora do aplicativo é removido e baixado de novo, em vez de
  travar a preparação; o SHA-256 completo não roda mais a cada abertura.
- FFmpeg escolhe o maior ramo estável publicado, sem depender do nome `n8.1`.
- Portable do macOS mantém os dados ao lado do `.app`; pastas somente leitura
  caem para o perfil do usuário com aviso.
- A fila de legendas guarda as opções de cada item: mexer na aba durante a
  fila não troca mais o vídeo que recebe a legenda. A fila aparece na tela.
- Janelas de console não piscam mais nas Ferramentas nem na importação de cookies.
- Importação de cookies funciona com nomes de usuário acentuados (ACL por SID).
- Botão destrutivo volta a ter contraste AA (texto e fundo em tokens separados).

### Alterado

- Opção obsoleta "Intervalo entre checagens do legendador" removida.
- Seção "Componentes" com versões legíveis e botões alinhados.
- Fio sob o cabeçalho ao rolar e rolagem nativa em touchpads de precisão.
- Dependabot ignora atualizações de CTranslate2/cuDNN que desligariam a GPU.
- Downloads de componentes e do instalador aceitam somente HTTPS.

## [1.8.0] - 2026-09-23

### Adicionado

- Miniatura da mídia analisada e prévia local do nome final conforme o template do yt-dlp.
- Fluxo **Baixar e legendar**, com fila automática de transcrição e incorporação opcional da legenda como faixa sem reencodar o vídeo.
- Whisper Large v3 Turbo, tradução para inglês, vocabulário de contexto e limites de legibilidade das legendas.
- Gerenciador de modelos Whisper para baixar, acompanhar o progresso, conferir espaço ocupado e remover pesos locais.
- Ícone na bandeja, notificações nativas e opção de manter tarefas em segundo plano ao fechar a janela.

### Alterado

- Ferramentas de mídia agora exibem percentual real do FFmpeg na tela e na barra de tarefas.
- Configuração do nome de arquivo ganhou atalhos para campos comuns e prévia imediata.
- Contraste, foco de teclado e nomes acessíveis foram reforçados nos controles principais.
- Geometria e estado maximizado da janela continuam preservados entre sessões.

### Segurança

- Miniaturas respeitam proxy, validação TLS, limite de 8 MB e cancelamento no encerramento.
- Novos modelos Whisper continuam fixados por revisão imutável.

## [1.7.0] - 2026-09-22

### Segurança

- Removido o fallback TLS sem validação e tornada obrigatória a conferência SHA-256.
- Validação HTTP(S), terminador `--` para o yt-dlp e redação de segredos em logs.
- Verificação persistente dos binários locais e uso do PATH somente por opção explícita.
- Modelos Whisper/MLX fixados por revisão imutável e FFmpeg macOS obtido de pacote com digest.
- Cookies podem ser importados com permissão exclusiva do usuário e recebem alerta de validade.
- Actions fixadas por commit, auditoria de dependências, SBOM e atestados de proveniência.

### Corrigido

- Duração incorreta no recorte, streams incompatíveis em MP4 e formatos de playlist.
- Encerramento bloqueante, segunda instância silenciosa e sobrescrita de saídas.
- Configurações corrompidas/tipos inválidos, logs concorrentes e cancelamento forçado.

### Alterado

- Removida a dependência GPL PySide6-Fluent-Widgets; rolagem suave agora é nativa.
- CTranslate2 fixado na versão compatível com cuDNN 8 e FFmpeg alterado para release estável.
- PyInstaller e Ruff fixados; lint e testes gráficos passam a bloquear a publicação.
- Publicações agora partem de tags `v*` compatíveis com a versão do código.
- Portable de Windows/Linux passa a manter dados dentro da própria pasta.
