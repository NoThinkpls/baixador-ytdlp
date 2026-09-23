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
    "Nome previsto": "Estimated name", "Gerar legenda ao terminar": "Create captions when finished",
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
    "Atualizar": "Update", "Atualização disponível": "Update available",
    "Baixar legendas": "Download subtitles", "Canal": "Channel",
    "Canal do yt-dlp": "yt-dlp channel", "Caracteres por linha": "Characters per line",
    "Caber em um limite": "Fit within a size limit", "Container do vídeo final. MKV nunca reconverte.":
        "Final video container. MKV is never re-encoded.",
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
    "Trocar container": "Change container",
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
}


def set_language(value: str) -> None:
    global _language
    _language = "en" if str(value).casefold().startswith("en") else "pt"


def language() -> str:
    return _language


def tr(text: str) -> str:
    """Traduz um texto visível da UI, preservando mensagens ainda não catalogadas."""
    return EN.get(text, text) if _language == "en" else text

