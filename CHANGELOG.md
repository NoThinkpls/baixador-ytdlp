# Changelog

Todas as mudanças relevantes deste projeto serão registradas aqui, seguindo o
formato Keep a Changelog.

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
