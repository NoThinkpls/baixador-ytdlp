# Compilação e publicação de Releases

> As releases Windows usam Nuitka. A comparação de desempenho e segurança, a
> rota de contingência com PyInstaller e as pendências de validação estão em
> [Avaliação do Nuitka](AVALIACAO-NUITKA.md).

[Read this guide in English](BUILD-AND-RELEASE.en.md)

As builds oficiais são geradas pelo GitHub Actions. Um push em `main` valida e
compila Windows, macOS e Linux e, somente se todas passarem, cria a tag `vX.Y.Z`
compatível com `APP_VERSION` e publica a Release. Uma tag enviada manualmente
continua compatível com o mesmo fluxo de validação.

## Arquivos de cada Release

| Plataforma | Arquivo versionado | Link estável para o README |
| --- | --- | --- |
| Windows instalador | `BaixadorYtdlp-X.Y.Z-setup.exe` | `baixador-ytdlp-setup.exe` |
| Windows portable | `BaixadorYtdlp-X.Y.Z-portable-windows.zip` | `baixador-ytdlp-portable-windows.zip` |
| macOS Apple Silicon — instalador | `BaixadorYtdlp-X.Y.Z-macos-arm64.dmg` | `baixador-ytdlp-macos-arm64.dmg` |
| macOS Apple Silicon — portable | `BaixadorYtdlp-X.Y.Z-macos-arm64.zip` | `baixador-ytdlp-macos-arm64.zip` |
| Linux Ubuntu/Debian x86_64 — pacote | `BaixadorYtdlp-X.Y.Z-linux-amd64.deb` | `baixador-ytdlp-linux-amd64.deb` |
| Linux x86_64 — portable | `BaixadorYtdlp-X.Y.Z-portable-linux-x86_64.tar.gz` | `baixador-ytdlp-portable-linux-x86_64.tar.gz` |

Os arquivos `SHA256SUMS.txt`, `SHA256SUMS-macos.txt` e `SHA256SUMS-linux.txt`,
os inventários CycloneDX (`sbom-*.cdx.json`) e os atestados de proveniência
acompanham os pacotes. Os aliases estáveis fazem os links
`/releases/latest/download/...` continuarem válidos mesmo com uma versão nova.

O workflow confere se os seis aliases aparecem no README e se todos os pacotes e hashes chegaram à etapa de Release. Assim, um erro de empacotamento impede a publicação de uma Release sem downloads. Se já houver uma Release sem ativos para a versão, ela é atualizada com os pacotes do build aprovado.

## Como publicar

1. Atualize a versão do aplicativo quando houver mudança distribuída.
2. Execute os testes e envie o commit para `main`.
3. Acompanhe a execução no [GitHub Actions](../../actions): a automação valida os três sistemas, cria a tag correspondente e publica a Release.
4. Só divulgue a Release depois que os jobs **Compilar no Windows**, **Compilar no macOS Apple Silicon**, **Compilar no Linux (Ubuntu/Debian)** e **Publicar release** concluírem com sucesso.

Não crie a tag nem a Release manualmente no fluxo normal: a automação cria ou
atualiza ambas quando os três pacotes terminam. Enquanto a etapa final está em
andamento, os links de download ainda podem retornar arquivo não encontrado.

## Desenvolvimento local

Os scripts `build.ps1` e `build.cmd` existem apenas como apoio ao desenvolvimento.
No Windows, `build.ps1` usa Nuitka por padrão; passe `-Packager PyInstaller`
para a rota de contingência. Para distribuição, use os artefatos produzidos
pelo GitHub Actions.

