# Changelog

Todas as mudanças relevantes deste projeto serão registradas aqui, seguindo o
formato Keep a Changelog.

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
