# Changelog

Todas as mudanças relevantes deste projeto serão registradas aqui, seguindo o
formato Keep a Changelog.

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
