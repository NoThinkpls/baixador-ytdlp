# Changelog

Todas as mudanças relevantes deste projeto serão registradas aqui, seguindo o
formato Keep a Changelog.

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
