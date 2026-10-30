"""Traduções leves da interface, sem depender de arquivos .qm na build."""
from __future__ import annotations

_language = "pt"

# A interface original continua sendo a fonte em português. Componentes visuais
# passam por ``tr`` ao serem criados; textos sem entrada ficam inteligíveis em
# português em vez de virar uma chave técnica quebrada.
EN: dict[str, str] = {
    "Navegação": "Navigation", "Baixar": "Download", "Fila": "Queue",
    "Legendar": "Captions", "Ferramentas": "Tools", "Histórico": "History",
    "Configurações": "Settings", "Minimizar": "Minimize", "Maximizar": "Maximize",
    "Fechar": "Close", "Recolher navegação": "Collapse navigation",
    "Expandir navegação": "Expand navigation",
    "Cole o link de um vídeo ou de uma playlist e escolha como quer o arquivo.":
        "Paste a video or playlist link and choose how you want the file.",
    "Cole o link do vídeo ou da playlist": "Paste the video or playlist link",
    "Colar": "Paste", "Importar lista": "Import list", "Vários links": "Multiple links",
    "Analisar": "Analyze", "Saída": "Output", "Formato do arquivo": "File format",
    "Somente áudio": "Audio only", "Formato do áudio": "Audio format",
    "Nome previsto": "Estimated name", "Nome personalizado": "Custom name",
    "Nome do arquivo sem a extensão. Não vale para playlists.":
        "File name without the extension. Does not apply to playlists.",
    "Deixe vazio para usar o nome previsto": "Leave empty to use the estimated name", "Gerar legenda ao terminar": "Create captions when finished",
    "Incorporar legenda como faixa": "Embed captions as a track",
    "Baixar só um trecho": "Download a clip",
    "Qualidade": "Quality", "Arquivos": "Files", "Modelo": "Model",
    "Andamento": "Progress", "Iniciar transcrição": "Start transcription",
    "Pausar": "Pause", "Continuar": "Resume", "Cancelar": "Cancel",
    "Abrir pasta": "Open folder", "Selecionar": "Select", "Salvar como": "Save as",
    "Idioma": "Language", "Modelo Whisper": "Whisper model",
    "Gerenciar modelos": "Manage models", "Modelos no disco": "Models on disk",
    "Formato da legenda": "Caption format", "Filtro anti-alucinação agressivo":
        "Aggressive anti-hallucination filter", "Modo rápido na GPU NVIDIA": "Fast NVIDIA GPU mode",
    "Economizar memória de vídeo": "Save video memory",
    "Transcrição local com faster-whisper. Usa CUDA quando dá, e CPU quando não dá.":
        "Local transcription with faster-whisper. Uses CUDA when available and CPU otherwise.",
    "Selecione ou arraste um vídeo ou áudio para cá": "Select or drag a video or audio file here",
    "A legenda será criada ao lado da mídia": "Captions will be created next to the media file",
    "Arquivo de mídia": "Media file", "Arquivo de saída": "Output file",
    "Pronto para transcrever": "Ready to transcribe", "Iniciando…": "Starting…",
    "O andamento da transcrição aparecerá aqui.": "Transcription progress will appear here.",
    "Português": "Portuguese", "Inglês": "English", "Espanhol": "Spanish",
    "Francês": "French", "Alemão": "German", "Italiano": "Italian",
    "Japonês": "Japanese", "Coreano": "Korean", "Chinês": "Chinese",
    "Detectar automaticamente": "Detect automatically",
    "tiny — mais rápido": "tiny — fastest", "base — rápido": "base — fast",
    "small — equilibrado": "small — balanced", "medium — recomendado": "medium — recommended",
    "large-v3-turbo — rápido e preciso": "large-v3-turbo — fast and accurate",
    "large-v3 — mais preciso": "large-v3 — most accurate",
    "Transcrever no idioma original": "Transcribe in the original language",
    "Traduzir para inglês": "Translate into English",
    "Tudo fica salvo nesta máquina, no seu perfil de usuário.":
        "Everything is saved on this computer, in your user profile.",
    "Legendas e extras": "Captions and extras",
    "Conversão por GPU": "GPU conversion", "Aparência e notificações": "Appearance and notifications",
    "Rede e desempenho": "Network and performance", "Contas e cookies": "Accounts and cookies",
    "Atualizações e sobre": "Updates and about", "Avançado": "Advanced",
    "Onde salvar": "Save location", "Arquivo": "File",
    "Extras do arquivo": "File extras", "Legendas e cortes": "Captions and cuts",
    "Placa de vídeo": "Graphics card", "Conversão": "Conversion",
    "Velocidade": "Speed", "Quando a conexão falhar": "When the connection fails",
    "Extrator e ferramentas": "Extractor and tools",
    "O que acontece com cada arquivo que você baixa.": "What happens to each file you download.",
    "Velocidade, limites e falhas de conexão.": "Speed, limits and connection failures.",
    "Capas, metadados e legendas.": "Artwork, metadata and captions.",
    "Acesso a conteúdo restrito.": "Restricted content access.",
    "Muda codec e tamanho, sem melhorar a fonte.": "Changes codec and size without improving the source.",
    "Visual e avisos do aplicativo.": "Appearance and notifications.",
    "Componentes e novas versões.": "Components and new versions.",
    "Extrator, histórico e ferramentas.": "Extractor, history and tools.",
    "Buscar uma opção — ex.: proxy, legendas, tema": "Search settings — e.g. proxy, captions, theme",
    "Nenhuma opção encontrada.": "No settings found.",
    "Área": "Area", "Arquivos e formato": "Files and format",
    "Fila e conexão": "Queue and connection", "Conteúdo": "Content",
    "Acesso": "Access", "Interface": "Interface", "Aplicativo": "Application",
    "Ajustes da conversão": "Conversion settings",
    "Destino, nome e formato dos downloads.": "Download folder, names and format.",
    "Concorrência, rede e retomada das tarefas.": "Concurrency, network and resuming tasks.",
    "Capas, legendas e trechos patrocinados.": "Artwork, captions and sponsored segments.",
    "Cookies e ajustes para conteúdo restrito.": "Cookies and restricted content settings.",
    "Placa detectada e opções de conversão.": "Detected GPU and conversion options.",
    "Aparência, comportamento e atalhos.": "Appearance, behavior and shortcuts.",
    "Histórico, componentes e atualizações.": "History, components and updates.",
    "Downloads": "Downloads", "Conteúdo extra": "Extra content",
    "Acesso a conteúdo restrito": "Restricted content access", "GPU e conversão": "GPU and conversion",
    "Aparência": "Appearance", "Atalhos de teclado": "Keyboard shortcuts",
    "Componentes e atualizações": "Components and updates", "Tema": "Theme",
    "Seguir o sistema": "Follow system", "Claro": "Light", "Escuro": "Dark",
    "Idioma da interface": "Interface language",
    "Português (Brasil)": "Portuguese (Brazil)",
    "Reinicie o aplicativo para aplicar o novo idioma.": "Restart the app to apply the new language.",
    "Pasta de destino": "Destination folder", "Escolher": "Choose",
    "Nome do arquivo": "File name", "Prévia": "Preview", "Placa detectada": "Detected GPU",
    "Componentes": "Components", "Verificar componentes": "Check components",
    "Diagnóstico": "Diagnostics", "Exportar diagnóstico": "Export diagnostics",
    "Nova versão do aplicativo": "New app version", "Verificar agora": "Check now",
    "Arquivo cookies.txt (recomendado)": "cookies.txt file (recommended)",
    "Como exportar": "How to export", "Ocultar ajuda": "Hide help",
    "Modelos Whisper": "Whisper models", "Remover": "Remove",
    "Verificando…": "Checking…", "Não baixado": "Not downloaded",
    "Baixado": "Downloaded", "em uso": "in use",
    "Atenção": "Attention", "Atualização": "Update", "Erro": "Error",
    "Sucesso": "Success", "Fila de legendas": "Caption queue",
    "Download concluído": "Download complete", "Legenda concluída": "Captions complete",
    # Página de downloads e fila.
    "0 links encontrados": "0 links found", "Adicionar à fila": "Add to queue",
    "Adicionar vários links": "Add multiple links", "Analise um link na página Baixar e ele aparece aqui com o progresso.":
        "Analyze a link on the Download page and it will appear here with its progress.",
    "A fila está vazia": "The queue is empty", "Agora não": "Not now",
    "Arquivo de legenda": "Caption file", "Arquivo de origem": "Source file",
    "Atualizar": "Update", "Reinstalar": "Reinstall", "Atualização disponível": "Update available",
    "Baixar legendas": "Download subtitles", "Canal": "Channel",
    "Canal do yt-dlp": "yt-dlp channel", "Caracteres por linha": "Characters per line",
    "Caber em um limite": "Fit within a size limit", "MP4 abre em qualquer lugar; MKV nunca reconverte o vídeo.":
        "MP4 opens anywhere; MKV never re-encodes the video.",
    "Criar versão vertical": "Create vertical version", "Data": "Date", "DESTINO": "DESTINATION",
    "Desligado, o arquivo vai direto para a pasta padrão das configurações.":
        "When off, the file goes directly to the default folder in Settings.",
    "Escolher a pasta deste download": "Choose this download's folder",
    "Escolher arquivo": "Choose file", "Escolher itens": "Choose items",
    "Escolher legenda": "Choose captions", "Escolher local": "Choose location",
    "Excluir": "Delete", "Extrair áudio": "Extract audio", "FORMATOS": "FORMATS",
    "Fundo desfocado": "Blurred background", "Início e fim": "Start and end",
    "Intervalo": "Interval", "Limpar": "Clear", "Limpar concluídos": "Clear completed",
    "Limpar tudo": "Clear all", "Nada guardado ainda": "Nothing saved yet",
    "O que você baixar ou transcrever aparece nesta lista, só na sua máquina.":
        "Everything you download or transcribe appears in this local-only list.",
    "Pasta de saída": "Output folder", "Perfil salvo": "Saved profile",
    "PERFIS": "PROFILES", "Procurar": "Browse", "Recortar": "Trim",
    "Recortar trecho": "Trim clip", "Reduzir tamanho": "Reduce size",
    "Resolução": "Resolution", "Salvar perfil": "Save profile", "Salvar resultado": "Save result",
    "Tamanho máximo": "Maximum size", "Tarefa": "Task", "Título": "Title",
    "Trocar contêiner": "Change container",
    "Vídeo legendado concluído": "Captioned video complete", "ÁUDIO": "AUDIO",
    "LEGENDAS": "SUBTITLES", "QUALIDADE": "QUALITY", "SAÍDA": "OUTPUT",
    # Configurações: títulos de controles e seções que aparecem sem contexto.
    "Abrir a pasta ao terminar": "Open folder when finished",
    "Ajustes do extrator (avançado)": "Extractor settings (advanced)",
    "Cookies do navegador": "Browser cookies", "Codec da conversão": "Conversion codec",
    "Converter após baixar (GPU)": "Convert after downloading (GPU)",
    "Detectar link na área de transferência": "Detect links in the clipboard",
    "Downloads simultâneos": "Simultaneous downloads", "Duração dos blocos": "Caption duration",
    "Efeito Mica na janela": "Mica window effect", "Embutir as legendas no vídeo": "Embed subtitles in video",
    "Embutir capa": "Embed cover art", "Embutir capítulos": "Embed chapters",
    "Embutir metadados": "Embed metadata", "Espera entre retentativas (segundos)":
        "Delay between retries (seconds)", "Evitar baixar a mesma mídia novamente":
        "Avoid downloading the same media again", "Fechar para a bandeja": "Close to tray",
    "Formato padrão do vídeo": "Default video format", "Fragmentos simultâneos": "Simultaneous fragments",
    "Guardar o que foi baixado": "Keep download history", "Idiomas das legendas": "Subtitle languages",
    "Intervalo entre checagens de atualização (horas)": "Update check interval (hours)",
    "Itens guardados": "Saved items", "Limite de banda": "Bandwidth limit",
    "Notificações na bandeja": "Tray notifications", "Organizar áudio por canal": "Organize audio by channel",
    "Perguntar a pasta em cada download": "Ask for a folder for every download",
    "Preset NVIDIA": "NVIDIA preset",
    "Priorizar compatibilidade (H.264)": "Prioritize compatibility (H.264)",
    "Qualidade (CQ)": "Quality (CQ)", "Remover trechos patrocinados": "Remove sponsored segments",
    "Retentativas automáticas": "Automatic retries", "Retomar a fila ao reabrir": "Resume queue at startup",
    "Substituir o arquivo original": "Replace the original file",
    "Usar ferramentas instaladas no sistema": "Use tools installed on the system",
    "Verificar novas versões ao abrir": "Check for new versions at startup",
    "Vocabulário de contexto": "Context vocabulary",
    # Estados e ações secundárias mais frequentes.
    "Hardware será detectado ao iniciar": "Hardware will be detected when transcription starts",
    "Não usar cookies": "Do not use cookies", "Nenhum encoder de GPU disponível": "No GPU encoder available",
    "Nenhum arquivo selecionado": "No file selected", "Prévia do nome do arquivo": "File name preview",
    "Revisão fixada e verificada pelo aplicativo.": "Revision pinned and verified by the app.",
    "Separados por vírgula.": "Comma-separated.", "Todos os arquivos (*.*)": "All files (*.*)",
    "Usar a pasta padrão": "Use default folder", "Verificando componentes": "Checking components",
    # Mensagens exibidas depois da criação dos widgets.
    "Baixar + legendar + incorporar": "Download + caption + embed",
    "Escolha um capítulo": "Choose a chapter", "Capítulo": "Chapter",
    "Pausar tudo": "Pause all", "Pausado": "Paused", "Na fila": "Queued",
    "Iniciando": "Starting", "Baixando": "Downloading", "Processando": "Processing",
    "Tentando novamente": "Retrying", "Concluído": "Completed",
    "Concluído com aviso": "Completed with warning", "Cancelado": "Cancelled",
    "Falha no download": "Download failed", "Aguardando nova tentativa…": "Waiting to retry…",
    "A mudança será aplicada na próxima verificação dos componentes.":
        "The change will apply at the next component check.",
    "Você já está usando a versão mais recente.": "You already have the latest version.",
    "Não foi possível verificar atualizações": "Could not check for updates",
    "Não foi possível exportar": "Could not export",
    "Diagnóstico exportado": "Diagnostics exported",
    "Lista importada": "List imported", "Perfil excluído": "Profile deleted",
    "Processamento concluído": "Processing completed",
    "Não foi possível processar a mídia": "Could not process the media",
    "Não foi possível adicionar as legendas": "Could not add the captions",
    "Arquivo interno do motor de transcrição ausente ({file}). A instalação está incompleta — reinstale a versão mais recente.":
        "Internal transcription engine file is missing ({file}). The installation is incomplete — reinstall the latest version.",
    "Vídeo com restrição de idade. É preciso fornecer cookies de uma conta logada.":
        "Age restricted video. Provide cookies from a signed-in account.",
    "Vídeo privado ou exclusivo para membros. Só com cookies de uma conta com acesso.":
        "Private or members-only video. Provide cookies from an account with access.",
    "Esse site não é suportado pelo yt-dlp.": "This site is not supported by yt-dlp.",
    "O disco ou a pasta de destino está sem espaço. Libere espaço ou escolha outra pasta em "
    "Configurações e tente de novo.":
        "The disk or destination folder is out of space. Free some space or pick another "
        "folder in Settings and try again.",
    "O caminho do arquivo ficou longo demais para o sistema. Escolha uma pasta mais curta ou "
    "simplifique o modelo do nome do arquivo em Configurações.":
        "The file path is too long for the system. Pick a shorter folder or simplify the "
        "file name template in Settings.",
    "Sem permissão para gravar na pasta de destino. Escolha outra pasta ou feche o programa "
    "que está usando o arquivo.":
        "No permission to write to the destination folder. Pick another folder or close the "
        "program using the file.",
    "O FFmpeg encontrou dados inválidos no arquivo (parte danificada ou download incompleto). "
    "Baixe de novo ou escolha outro formato.":
        "FFmpeg found invalid data in the file (damaged part or incomplete download). "
        "Download it again or pick another format.",
    "Vídeo bloqueado na sua região. Um proxy em outro país resolveria.":
        "This video is blocked in your region. A proxy in another country may help.",
    "A transmissão ainda não começou. Tente novamente quando o evento estiver ao vivo.":
        "The stream has not started. Try again when it goes live.",
    "O site está instável ou fora do ar agora. Tente novamente em alguns minutos.":
        "The site is unstable or offline. Try again in a few minutes.",
    "O formato escolhido não existe para este vídeo. Selecione Automático e tente novamente.":
        "The selected format is unavailable for this video. Select Automatic and try again.",
    "O vídeo está indisponível, foi removido ou o canal foi encerrado.":
        "The video is unavailable, was removed, or the channel was closed.",
    "Sem conexão com a internet, ou a rede bloqueou o acesso.":
        "No internet connection, or the network blocked access.",
    "Não foi possível ler os cookies do Chrome ou do Edge. Desde o Chrome 127 esses navegadores criptografam os cookies de um jeito que só o próprio navegador consegue abrir, e isso não tem solução do lado do yt-dlp. Em Configurações, use o Firefox ou aponte um arquivo cookies.txt.":
        "Could not read Chrome or Edge cookies. These browsers encrypt cookies so only the browser can open them. In Settings, use Firefox or provide a cookies.txt file.",
    "O YouTube exigiu um desafio JavaScript que o yt-dlp não conseguiu resolver. Isso acontece quando falta o runtime JavaScript (Deno) — apesar da mensagem, não é problema de cookies. Vá em Configurações → Dependências → Verificar agora para instalá-lo.":
        "YouTube required a JavaScript challenge that yt-dlp could not solve. Install the JavaScript runtime (Deno) through Settings → Components → Check now.",
    "O YouTube pediu confirmação de que você não é um robô. É preciso fornecer cookies de uma conta logada: em Configurações, aponte um arquivo cookies.txt exportado por uma janela anônima, ou selecione o Firefox.":
        "YouTube asked you to confirm you are not a bot. In Settings, provide cookies.txt from a signed-in account or select Firefox.",
    "O YouTube limitou as requisições deste IP. Espere alguns minutos antes de tentar de novo, ou configure um proxy.":
        "YouTube rate limited this IP. Wait a few minutes before retrying, or configure a proxy.",
    "O site recusou o acesso (HTTP 403). Verifique os componentes em Configurações e tente novamente; cookies só são necessários se o site pedir login ou confirmar que você não é um robô.":
        "The site denied access (HTTP 403). Check components in Settings and retry; cookies are needed only when the site requires sign-in or bot confirmation.",
    # Ferramentas: cartões, ajustes e mensagens de cada tarefa.
    "Preparando": "Preparing",
    "Comprimir": "Compress", "Comprimir para o limite": "Compress to the limit",
    "Criar MKV": "Create MKV",
    "Cortar e ajustar": "Trim and adjust", "Áudio": "Audio",
    "Converter e reduzir": "Convert and shrink", "Imagem e animação": "Image and animation",
    "Legendas e privacidade": "Captions and privacy",
    "Crie um novo vídeo apenas com o intervalo escolhido.":
        "Create a new video with only the chosen interval.",
    "Use mm:ss ou hh:mm:ss. O vídeo será recodificado para começar e terminar nos pontos escolhidos.":
        "Use mm:ss or hh:mm:ss. The video is re-encoded to start and end at the chosen points.",
    "Ajustar velocidade": "Adjust speed",
    "Deixe o vídeo em câmera lenta ou acelerado, com o som junto.":
        "Slow the video down or speed it up, with the sound following.",
    "Vale para imagem e som. Abaixo de 1x é câmera lenta.":
        "Applies to picture and sound. Below 1x is slow motion.",
    "0,25x — muito lento": "0.25x — very slow", "0,5x — câmera lenta": "0.5x — slow motion",
    "0,75x — um pouco mais lento": "0.75x — a bit slower",
    "1,25x — um pouco mais rápido": "1.25x — a bit faster", "1,5x — rápido": "1.5x — fast",
    "2x — o dobro": "2x — double", "3x — três vezes": "3x — triple", "4x — timelapse": "4x — timelapse",
    "Girar ou espelhar": "Rotate or flip",
    "Corrija vídeos de celular tortos ou espelhe a imagem.":
        "Fix sideways phone videos or mirror the picture.",
    "Girar vídeo": "Rotate video", "Transformação": "Transformation",
    "A imagem é recodificada; o som é mantido.": "The picture is re-encoded; the sound is kept.",
    "Girar 90° para a direita": "Rotate 90° clockwise",
    "Girar 90° para a esquerda": "Rotate 90° counterclockwise", "Girar 180°": "Rotate 180°",
    "Espelhar na horizontal": "Flip horizontally", "Espelhar na vertical": "Flip vertically",
    "Prepare um vídeo vertical para Shorts, Reels ou TikTok.":
        "Prepare a vertical video for Shorts, Reels or TikTok.",
    "Salve só o som de um vídeo ou converta entre formatos de áudio.":
        "Save just the sound of a video or convert between audio formats.",
    "MP3 toca em tudo; M4A e Opus rendem mais por megabyte; FLAC e WAV não perdem qualidade.":
        "MP3 plays everywhere; M4A and Opus give more per megabyte; FLAC and WAV lose no quality.",
    "MP3 — compatível com tudo": "MP3 — plays everywhere",
    "M4A (AAC) — celulares e Apple": "M4A (AAC) — phones and Apple",
    "Opus — menor tamanho": "Opus — smallest size", "FLAC — sem perda": "FLAC — lossless",
    "WAV — sem compressão": "WAV — uncompressed",
    "Nivelar volume": "Normalize volume",
    "Iguale o volume de vídeos e músicas sem recodificar a imagem.":
        "Even out the volume of videos and music without re-encoding the picture.",
    "Volume alvo": "Target volume",
    "Medido em LUFS. -16 serve para a maioria dos casos; -14 é o padrão do YouTube e do Spotify.":
        "Measured in LUFS. -16 suits most cases; -14 is the YouTube and Spotify standard.",
    "-16 LUFS — web e podcast": "-16 LUFS — web and podcasts",
    "-14 LUFS — YouTube e Spotify": "-14 LUFS — YouTube and Spotify",
    "-23 LUFS — TV (EBU R128)": "-23 LUFS — TV (EBU R128)",
    "Remover áudio": "Remove audio",
    "Crie uma cópia do vídeo sem som, sem recodificar a imagem.":
        "Create a copy of the video without sound, without re-encoding the picture.",
    "Converter formato": "Convert format",
    "Converta vídeo, áudio, imagem ou legenda para outro formato.":
        "Convert video, audio, images or subtitles to another format.",
    "Converter": "Convert", "Formato de saída": "Output format",
    "Arquivo de vídeo, áudio, imagem ou legenda": "Video, audio, image or subtitle file",
    "Arquivo de vídeo ou áudio de origem": "Source video or audio file",
    "Vídeo vira outro vídeo ou só o áudio. MP4 abre em qualquer lugar; WebM costuma ficar "
    "menor, mas demora mais.":
        "Video becomes another video or just the audio. MP4 opens anywhere; WebM is often "
        "smaller, but takes longer.",
    "MP3 toca em tudo; M4A e Opus rendem mais por megabyte; FLAC, WAV e AIFF não perdem "
    "qualidade.":
        "MP3 plays everywhere; M4A and Opus give more per megabyte; FLAC, WAV and AIFF are "
        "lossless.",
    "PNG não perde qualidade; JPG e WebP ficam bem menores. JPG e BMP não têm transparência.":
        "PNG is lossless; JPG and WebP are much smaller. JPG and BMP have no transparency.",
    "SRT é o mais aceito; ASS guarda estilo; VTT é o da web. Converter de ASS para SRT ou VTT "
    "perde cores e posições.":
        "SRT is the most widely accepted; ASS keeps styling; VTT is for the web. Converting ASS "
        "to SRT or VTT loses colors and positions.",
    "MP4 — H.264, abre em tudo": "MP4 — H.264, opens anywhere",
    "MKV — H.264, guarda várias faixas": "MKV — H.264, keeps several tracks",
    "WebM — VP9, para sites (mais lento)": "WebM — VP9, for websites (slower)",
    "MOV — H.264, Apple e editores": "MOV — H.264, Apple and editors",
    "AVI — Xvid e MP3, TVs e players antigos": "AVI — Xvid and MP3, TVs and older players",
    "MP3 — áudio compatível com tudo": "MP3 — audio that plays everywhere",
    "Opus — áudio menor": "Opus — smaller audio", "OGG (Vorbis) — áudio livre": "OGG (Vorbis) — open audio",
    "FLAC — áudio sem perda": "FLAC — lossless audio", "WAV — áudio sem compressão": "WAV — uncompressed audio",
    "AIFF — sem compressão, Mac": "AIFF — uncompressed, Mac",
    "BMP — sem compressão": "BMP — uncompressed", "TIFF — impressão e edição": "TIFF — print and editing",
    "ASS — com estilo": "ASS — with styling",
    "Converta para MKV sem mexer em imagem ou som.": "Convert to MKV without touching picture or sound.",
    "Crie um MP4 menor, equilibrando tamanho e qualidade.": "Create a smaller MP4, balancing size and quality.",
    "Comprima para caber no limite do Discord, WhatsApp ou e-mail.":
        "Compress to fit the Discord, WhatsApp or email limit.",
    "Criar GIF animado": "Create animated GIF", "Criar GIF": "Create GIF",
    "Transforme um trecho curto em GIF leve, com as cores otimizadas.":
        "Turn a short clip into a light GIF with optimized colors.",
    "Trecho do GIF": "GIF clip",
    "Use mm:ss ou hh:mm:ss, com até 30 s. Em branco, começa do zero.":
        "Use mm:ss or hh:mm:ss, up to 30 s. Blank starts from zero.",
    "Tamanho": "Size",
    "Quanto maior a largura, maior o arquivo. O GIF nunca passa da largura original do vídeo.":
        "The wider it is, the larger the file. The GIF never exceeds the video's original width.",
    "Pequeno — 480 px, 12 quadros/s": "Small — 480 px, 12 frames/s",
    "Médio — 640 px, 15 quadros/s": "Medium — 640 px, 15 frames/s",
    "Grande — 800 px, 20 quadros/s": "Large — 800 px, 20 frames/s",
    "Capturar imagem": "Capture image",
    "Salve um quadro do vídeo como imagem, no momento que você escolher.":
        "Save a video frame as an image, at the moment you choose.",
    "Momento do quadro": "Frame time",
    "Use mm:ss ou hh:mm:ss. Em branco, captura o primeiro quadro.":
        "Use mm:ss or hh:mm:ss. Blank captures the first frame.",
    "Formato da imagem": "Image format",
    "PNG não perde qualidade; JPG e WebP ficam bem menores.":
        "PNG loses no quality; JPG and WebP are much smaller.",
    "PNG — sem perda": "PNG — lossless", "JPG — leve e compatível": "JPG — light and compatible",
    "WebP — leve e moderno": "WebP — light and modern",
    "Grave uma legenda SRT, VTT ou ASS na imagem do vídeo.":
        "Burn an SRT, VTT or ASS caption into the video picture.",
    "Adicionar legendas ao vídeo": "Add captions to the video", "Adicionar legendas": "Add captions",
    "Extrair legendas": "Extract captions",
    "Salve como arquivo a legenda que já vem dentro do vídeo.":
        "Save the caption track already inside the video as a file.",
    "Usa a primeira faixa de legenda em texto. O arquivo é salvo ao lado do vídeo, com o mesmo nome.":
        "Uses the first text caption track. The file is saved next to the video, with the same name.",
    "SRT — o mais compatível": "SRT — most compatible", "ASS — mantém o estilo": "ASS — keeps the style",
    "VTT — para a web": "VTT — for the web",
    "Limpar metadados": "Clean metadata",
    "Apague localização, data, câmera e título do arquivo, sem recodificar.":
        "Erase location, date, camera and title from the file, without re-encoding.",
    "Este arquivo não tem legendas embutidas.": "This file has no embedded captions.",
    "As legendas deste arquivo são imagens (PGS/DVD) e não podem virar texto.":
        "This file's captions are images (PGS/DVD) and cannot become text.",
    "Este arquivo não tem a faixa que a ferramenta precisa (por exemplo, imagem em um arquivo só de áudio). Escolha outro arquivo ou outra ferramenta.":
        "This file lacks the track the tool needs (for example, picture in an audio-only file). Pick another file or tool.",
    "Use .mp3, .m4a, .opus, .flac ou .wav como extensão de saída.":
        "Use .mp3, .m4a, .opus, .flac or .wav as the output extension.",
    "Use .mp4, .mkv ou .webm como extensão de saída.": "Use .mp4, .mkv or .webm as the output extension.",
    "Use .png, .jpg ou .webp como extensão de saída.": "Use .png, .jpg or .webp as the output extension.",
    "Use .srt, .ass ou .vtt como extensão de saída.": "Use .srt, .ass or .vtt as the output extension.",
    # Cortes verticais
    "Cortes": "Clips", "Corte": "Clip", "cortes": "clips",
    "Gere vídeos verticais com legenda palavra a palavra, sem as pausas.":
        "Create vertical videos with word-by-word captions, without the pauses.",
    "Arquivo de vídeo ou link do YouTube": "Video file or YouTube link",
    "Vídeo de origem": "Source video",
    "Use um arquivo do computador ou cole um link: só os trechos escolhidos são baixados.":
        "Use a file from your computer or paste a link: only the chosen parts are downloaded.",
    "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título aparece animado nos primeiros segundos.":
        "Enter the start and end of each clip as mm:ss or hh:mm:ss. The title appears animated in the first seconds.",
    "início 01:30": "start 01:30", "fim 02:15": "end 02:15",
    "Título animado (opcional)": "Animated title (optional)", "Remover corte": "Remove clip",
    "Adicionar corte": "Add clip", "Estilo": "Style", "Transcrição": "Transcription",
    "Enquadramento 9:16": "9:16 framing",
    "Fundo desfocado — vídeo inteiro": "Blurred background — whole video",
    "Cortar no centro — tela cheia": "Crop the center — full screen",
    "O desfoque mostra o quadro todo; o corte no centro preenche a tela, mas perde as laterais.":
        "The blur shows the whole frame; cropping the center fills the screen but loses the sides.",
    "Remover pausas": "Remove pauses",
    "Corta os silêncios entre as falas usando o tempo de cada palavra.":
        "Cuts the silences between lines using the timing of each word.",
    "Pausa mínima": "Minimum pause",
    "Silêncios menores que isso ficam no vídeo.": "Silences shorter than this stay in the video.",
    "0,4 s — ritmo acelerado": "0.4 s — fast pace", "0,6 s — recomendado": "0.6 s — recommended",
    "0,8 s — mais natural": "0.8 s — more natural", "1,2 s — só pausas longas": "1.2 s — long pauses only",
    "Palavras por legenda": "Words per caption", "2 palavras": "2 words", "3 palavras": "3 words",
    "A palavra falada aparece em amarelo e um pouco maior.":
        "The spoken word appears in yellow and slightly larger.",
    "Legenda em maiúsculas": "Uppercase captions",
    "Mais fácil de ler na tela do celular.": "Easier to read on a phone screen.",
    "Idioma da fala": "Spoken language",
    "O mesmo da aba Legendar. Usa a GPU NVIDIA quando disponível e a CPU nos demais casos.":
        "Same as the Captions tab. Uses the NVIDIA GPU when available and the CPU otherwise.",
    "Pasta onde os cortes serão salvos": "Folder where clips will be saved",
    "Escolher pasta": "Choose folder", "Salvar cortes em": "Save clips to",
    "Cada corte vira um MP4 1080x1920 separado. O original nunca é alterado.":
        "Each clip becomes a separate 1080x1920 MP4. The original is never changed.",
    "Escolha um vídeo e informe os cortes para começar.": "Choose a video and enter the clips to start.",
    "Criar cortes": "Create clips", "Preparando 1 corte…": "Preparing 1 clip…",
    "Cortes prontos": "Clips ready", "Cortes concluídos": "Clips finished",
    "corte(s) salvos em": "clip(s) saved to", "Limite de cortes": "Clip limit",
    "Não foi possível criar os cortes": "Could not create the clips",
    "Cortes cancelados.": "Clips cancelled.", "Cancelar os cortes?": "Cancel the clips?",
    "Adicione pelo menos um corte com início e fim.": "Add at least one clip with a start and end.",
    "Use mm:ss ou hh:mm:ss para o início e o fim de cada corte.":
        "Use mm:ss or hh:mm:ss for the start and end of each clip.",
    "O fim de cada corte precisa ser posterior ao início.": "Each clip must end after it starts.",
    "Cada corte precisa ter pelo menos 1 segundo.": "Each clip must be at least 1 second long.",
    "Selecione um arquivo de vídeo existente ou cole um link.":
        "Select an existing video file or paste a link.",
    "Enquadramento": "Framing", "Legenda": "Caption",
    "Seguir a pessoa — automático": "Follow the person — automatic",
    "Aproxima e acompanha quem está em cena, como o reenquadrar do CapCut. Procura rostos e, sem rosto, segue o movimento. Vídeos já verticais ficam como estão.":
        "Zooms in and follows whoever is on screen, like CapCut's auto reframe. It looks for faces "
        "and, without one, follows the motion. Videos that are already vertical stay as they are.",
    "Mostra o quadro todo, com o próprio vídeo desfocado atrás.":
        "Shows the whole frame, with the video itself blurred behind it.",
    "Preenche a tela com o centro do vídeo; as laterais ficam de fora.":
        "Fills the screen with the center of the video; the sides are left out.",
    "Fonte": "Font", "Cores": "Colors", "Altura": "Height",
    "Palavras": "Words", "Maiúsculas": "Uppercase", "Texto": "Text",
    "Palavra falada": "Spoken word", "Pequena": "Small", "Média": "Medium", "Grande": "Large",
    "Muito grande": "Very large", "Enorme": "Huge", "1 palavra": "1 word", "palavras": "words",
    "% da altura; arraste na prévia": "% of the height; drag it in the preview",
    "A fonte precisa estar instalada no computador. A prévia é aproximada; o título usa a cor da palavra falada.":
        "The font must be installed on the computer. The preview is approximate; the title uses "
        "the spoken word color.",
    "Cor do texto": "Text color", "Cor da palavra falada": "Spoken word color",
    "Arraste para cima ou para baixo para posicionar a legenda":
        "Drag up or down to position the caption",
    "Prévia da legenda": "Caption preview", "Título do corte": "Clip title",
    "Fazer outros cortes deste vídeo": "Make more clips from this video",
    "O vídeo de origem não está mais no lugar": "The source video is no longer there",
    "Abrir o arquivo": "Open the file",
    "Tudo o que você baixou, legendou, cortou e converteu nesta máquina.":
        "Everything you downloaded, captioned, clipped and converted on this computer.",
    "O que você baixar, transcrever, cortar ou converter aparece nesta lista, só na sua máquina.":
        "What you download, transcribe, clip or convert shows up in this list, only on your computer.",
    "Acabamento": "Finishing",
    "Efeitos sonoros": "Sound effects",
    "Com plano da IA, cada som entra na palavra que ela indicou (whoosh, pop, impacto, ding ou subida). Sem plano, uma regra simples: whoosh nas pausas longas cortadas e pop nas palavras ditas bem mais alto.":
        "With an AI plan, each sound lands on the word it chose (whoosh, pop, impact, ding or riser). "
        "Without a plan, a simple rule: a whoosh on long pauses that were cut and a pop on words said much louder.",
    "Zoom na ênfase": "Zoom on emphasis",
    "Aproxima rápido a imagem nos pontos do plano da IA ou, sem plano, na palavra dita com mais força.":
        "Quickly punches in at the AI plan's points or, without a plan, on the word said loudest.",
    "Seus sons (opcional)": "Your sounds (optional)",
    "Uma pasta com arquivos chamados whoosh, pop, impacto, ding e subida (WAV, MP3, OGG…) troca os sons padrão pelos seus. O que faltar continua com o som do app.":
        "A folder with files named whoosh, pop, impacto, ding and subida (WAV, MP3, OGG…) replaces "
        "the default sounds with yours. Anything missing keeps the app's sound.",
    "Sons do próprio app": "The app's own sounds",
    "Plano da IA": "AI plan",
    "Cole a linha {\"bx\":1,…} que a IA entrega no fim da resposta (veja docs/PLANO-DA-IA.md): ela preenche os cortes, os títulos e onde entra cada som e zoom. Com o campo vazio, o botão lê a área de transferência (pode ser a resposta inteira).":
        "Paste the {\"bx\":1,…} line the AI returns at the end of its answer (see docs/AI-PLAN.en.md): it fills in the clips, "
        "the titles and where each sound and zoom goes. With the field empty, the button reads the "
        "clipboard (it can be the whole answer).",
    "Aplicar plano": "Apply plan",
    "Efeitos do plano da IA": "Effects from the AI plan",
    "Altura do título": "Title height",
    "% da altura; arraste o título na prévia": "% of the height; drag the title in the preview",
    "Arraste a legenda ou o título para cima ou para baixo": "Drag the caption or the title up or down",
    "corte(s)": "clip(s)",
    "ponto(s) de efeito carregados.": "effect point(s) loaded.",
    "Animação": "Animation",
    "Caixa atrás": "Box behind",
    "Destaque — cor e maior": "Highlight — color and larger",
    "Só a cor muda": "Color only",
    "Karaokê — pinta ao falar": "Karaoke — fills as spoken",
    "Uma palavra por vez": "One word at a time",
    "Grupo entra com pulo": "Group pops in",
    "Sem destaque — legenda simples": "No highlight — plain caption",
    "2 segundos": "2 seconds",
    "3 segundos": "3 seconds",
    "5 segundos": "5 seconds",
    "O corte inteiro": "The whole clip",
    "Título na tela": "Title on screen",
    "Quanto tempo o título de cada corte fica visível.": "How long each clip's title stays visible.",
    "Zoom nas emendas": "Zoom on cuts",
    "Alterna uma leve aproximação a cada pausa removida: o salto vira um corte de câmera, como nos vídeos de quem edita à mão.": "Alternates a slight zoom at each removed pause: the jump becomes a camera cut, like hand-edited videos.",
    "Barra de progresso": "Progress bar",
    "Uma linha fina no rodapé, na cor de destaque, mostrando quanto falta.": "A thin line at the bottom, in the highlight color, showing how much is left.",
    "Volume equilibrado": "Balanced volume",
    "Ajusta o som para -14 LUFS, o padrão do YouTube, TikTok e Reels.": "Sets the sound to -14 LUFS, the YouTube, TikTok and Reels standard.",
    "Salvar a legenda em .srt": "Save the caption as .srt",
    "Um arquivo ao lado de cada corte, para enviar como legenda separada.": "A file next to each clip, to upload as a separate caption.",
    "inválido": "invalid",
    "Vídeos": "Videos",
    "Este arquivo só tem áudio. Os cortes verticais precisam de vídeo; para legendar só o áudio, use a aba Legendar.": "This file only has audio. Vertical clips need video; to caption audio only, use the Captions tab.",
    "Este vídeo não tem som: sem fala não há legenda nem pausas para tirar. Para só deixá-lo vertical, use Ferramentas → Criar versão vertical.": "This video has no sound: without speech there are no captions or pauses to remove. To just make it vertical, use Tools → Create vertical version.",
    "Não foi possível ler este arquivo como vídeo.": "Could not read this file as a video.",
    # Página Cortes 1.15.0: escolhas com miniatura e título fixo no topo
    "Seguir a pessoa": "Follow the person", "automático": "automatic",
    "vídeo inteiro": "whole video", "Cortar no centro": "Center crop",
    "tela cheia": "full screen", "Título animado": "Animated title",
    "entra e some": "pops in and out", "Título fixo no topo": "Fixed title on top",
    "faixa com cartão": "banner with card",
    "Aproxima e acompanha quem está falando, como o reenquadrar do CapCut. Procura rostos e, sem rosto, segue o movimento. Vídeos já verticais ficam como estão.": "Zooms in and follows whoever is speaking, like CapCut's auto reframe. It looks for faces and, without one, follows the motion. Videos that are already vertical stay as they are.",
    "O título de cada corte entra com um pulo e some depois do tempo escolhido.": "Each clip's title pops in and disappears after the chosen time.",
    "Uma faixa escura no alto com o título num cartão na cor de destaque, do começo ao fim; o vídeo fica embaixo, como nos canais de cortes de podcast.": "A dark band at the top with the title on a card in the highlight color, from start to end; the video sits below, like podcast clip channels.",
    "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título fica no cartão do topo durante todo o corte.": "Enter the start and end of each clip as mm:ss or hh:mm:ss. The title stays on the top card for the whole clip.",
    "Título no cartão (opcional)": "Title on the card (optional)",
    "Visual do corte": "Clip look", "Ritmo e efeitos": "Pacing and effects",
    "Saída e transcrição": "Output and transcription", "Tempo na tela": "Time on screen",
    "Linha de cima": "Top line",
    "Ex.: nome do podcast, convidado ou episódio": "E.g. podcast name, guest or episode",
    "Arraste a legenda na prévia. A imagem é aproximada.": "Drag the caption in the preview. The image is approximate.",
    "Palavra falada e título": "Spoken word and title",
    "A fonte precisa estar instalada no computador. O título usa a fonte da legenda e a cor da palavra falada.": "The font must be installed on the computer. The title uses the caption font and the spoken word color.",
    "Prévia do corte": "Clip preview",
    "Arraste a legenda para cima ou para baixo": "Drag the caption up or down",
    "Use um arquivo do computador ou cole um link: só os trechos escolhidos são baixados. Com um arquivo, a prévia mostra um quadro dele.": "Use a file from your computer or paste a link: only the chosen parts are downloaded. With a file, the preview shows a frame from it.",
}


def set_language(value: str) -> None:
    global _language
    _language = "en" if str(value).casefold().startswith("en") else "pt"


def language() -> str:
    return _language


def tr(text: str) -> str:
    """Traduz um texto visível da UI, preservando mensagens ainda não catalogadas."""
    return EN.get(text, text) if _language == "en" else text
