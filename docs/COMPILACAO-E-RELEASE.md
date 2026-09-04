# Compilação e publicação de Releases

As builds oficiais são geradas pelo GitHub Actions. Um push em `main` valida os pacotes; uma tag `vX.Y.Z` compila Windows e macOS e, ao final, cria ou atualiza a Release correspondente.

## Arquivos de cada Release

| Plataforma | Arquivo versionado | Link estável para o README |
| --- | --- | --- |
| Windows instalador | `BaixadorYtdlp-X.Y.Z-setup.exe` | `baixador-ytdlp-setup.exe` |
| Windows portable | `BaixadorYtdlp-X.Y.Z-portable-windows.zip` | `baixador-ytdlp-portable-windows.zip` |
| macOS Apple Silicon | `BaixadorYtdlp-X.Y.Z-macos-arm64.zip` | `baixador-ytdlp-macos-arm64.zip` |

Os arquivos `SHA256SUMS.txt` e `SHA256SUMS-macos.txt` acompanham os pacotes. Os aliases estáveis fazem os links `/releases/latest/download/...` continuarem válidos mesmo com uma versão nova.

## Como publicar

1. Atualize a versão do aplicativo quando houver mudança distribuída.
2. Envie o commit para `main`.
3. Crie e envie a tag correspondente: `git tag vX.Y.Z` e `git push origin vX.Y.Z`.
4. Acompanhe a execução no [GitHub Actions](../../actions).
5. Só divulgue a Release depois que os jobs **Compilar no Windows**, **Compilar no macOS Apple Silicon** e **Publicar release** concluírem com sucesso.

Não é necessário criar uma Release vazia manualmente: a automação a cria ou a atualiza quando os dois pacotes terminam. Enquanto a etapa final está em andamento, os links de download ainda podem retornar arquivo não encontrado.

## Desenvolvimento local

Os scripts `build.ps1` e `build.cmd` existem apenas como apoio ao desenvolvimento. Para distribuição, use os artefatos produzidos pelo GitHub Actions.
