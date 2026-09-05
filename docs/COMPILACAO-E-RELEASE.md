# Compilação e publicação de Releases

As builds oficiais são geradas pelo GitHub Actions. Um push em `main` compila Windows e macOS; quando ambos terminam com sucesso, o workflow cria (ou recupera) a tag `vX.Y.Z` e publica a Release da versão definida em `APP_VERSION`.

## Arquivos de cada Release

| Plataforma | Arquivo versionado | Link estável para o README |
| --- | --- | --- |
| Windows instalador | `BaixadorYtdlp-X.Y.Z-setup.exe` | `baixador-ytdlp-setup.exe` |
| Windows portable | `BaixadorYtdlp-X.Y.Z-portable-windows.zip` | `baixador-ytdlp-portable-windows.zip` |
| macOS Apple Silicon — instalador | `BaixadorYtdlp-X.Y.Z-macos-arm64.dmg` | `baixador-ytdlp-macos-arm64.dmg` |
| macOS Apple Silicon — portable | `BaixadorYtdlp-X.Y.Z-macos-arm64.zip` | `baixador-ytdlp-macos-arm64.zip` |

Os arquivos `SHA256SUMS.txt` e `SHA256SUMS-macos.txt` acompanham os pacotes. Os aliases estáveis fazem os links `/releases/latest/download/...` continuarem válidos mesmo com uma versão nova.

O workflow confere se os quatro aliases aparecem no README e se todos os pacotes e hashes chegaram à etapa de Release. Assim, um erro de empacotamento impede a publicação de uma Release sem downloads. Se já houver uma Release sem ativos para a versão, ela é atualizada com os pacotes do build aprovado.

## Como publicar

1. Atualize a versão do aplicativo quando houver mudança distribuída.
2. Envie o commit para `main`.
3. Acompanhe a execução no [GitHub Actions](../../actions).
4. Só divulgue a Release depois que os jobs **Compilar no Windows**, **Compilar no macOS Apple Silicon** e **Publicar release** concluírem com sucesso.

Não crie tag nem Release manualmente: a automação as cria ou atualiza quando os dois pacotes terminam. Enquanto a etapa final está em andamento, os links de download ainda podem retornar arquivo não encontrado.

## Desenvolvimento local

Os scripts `build.ps1` e `build.cmd` existem apenas como apoio ao desenvolvimento. Para distribuição, use os artefatos produzidos pelo GitHub Actions.
