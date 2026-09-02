# baixador-ytdlp

Baixador de vídeo com interface Fluent (padrão Windows 11), construído sobre o
yt-dlp e o FFmpeg. Instala e atualiza as próprias dependências, analisa o link,
mostra todas as qualidades disponíveis e baixa na melhor por padrão.

## Como rodar durante o desenvolvimento

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Como gerar o executável

```powershell
.\build.ps1              # gera dist\baixador-ytdlp\baixador-ytdlp.exe
.\build.ps1 -Installer   # gera também dist\installer\BaixadorYtdlp-1.0.0-setup.exe
```

O `-Installer` precisa do [Inno Setup 6](https://jrsoftware.org/isdl.php).

Para compilar na nuvem em vez da própria máquina, o repositório já traz
`.github/workflows/build.yml`: qualquer push na `main` gera o `.exe` e o setup
como artefatos, e uma tag `v1.0.0` publica os dois numa release.
É o instalador que cria o atalho no Menu Iniciar — **é isso que faz o programa
aparecer quando você digita o nome na busca do Windows**. Um `.exe` solto numa
pasta qualquer não é indexado pela busca; o `%APPDATA%\Microsoft\Windows\Start Menu\Programs`
é.

## Estrutura

```
main.py                  ponto de entrada, instância única, ícone
baixador_ytdlp/
  config.py              caminhos e settings.json
  tools.py               instala/atualiza yt-dlp e FFmpeg
  gpu.py                 detecção de NVENC
  probe.py               yt-dlp -J e montagem da lista de qualidades
  downloader.py          linha de comando, leitura de progresso, NVENC
  workers.py             QThreads (nada de I/O na thread da UI)
  ui/                    setup_dialog, home_page, queue_page, settings_page, main_window
```

## Onde ficam as coisas

| O quê | Caminho |
|---|---|
| Binários (yt-dlp, ffmpeg) | `%LOCALAPPDATA%\BaixadorYtdlp\bin` |
| Configurações | `%LOCALAPPDATA%\BaixadorYtdlp\settings.json` |
| Log de erro fatal | `%LOCALAPPDATA%\BaixadorYtdlp\logs\crash.log` |
| Vídeos | `Vídeos\baixador-ytdlp` (configurável) |

Os binários ficam fora de `Program Files` de propósito: a atualização automática
não precisa de elevação nem de prompt de UAC.

## Sobre a GPU

O download em si é rede e cópia de arquivo — a GPU não participa e não existe
"baixar com mais qualidade usando a placa". A melhor qualidade possível é o
stream original remuxado, sem reencode, e é isso que o app faz por padrão.

A RTX 4060 entra na aba **GPU e conversão**, opcional e desligada por padrão:
reencoda o arquivo já baixado com NVENC (H.264, HEVC ou AV1 — a série 40 é a
primeira com encoder AV1 em hardware). Serve para compatibilidade com aparelhos
antigos ou para reduzir tamanho. Todo reencode perde qualidade em relação ao
original; se o objetivo é qualidade máxima, deixe desligado.

## Notas de segurança

- O `yt-dlp.exe` é conferido contra o `SHA2-256SUMS` do próprio release antes de
  substituir o binário local. Download que não bate no hash é descartado.
- O FFmpeg (builds do BtbN) não publica checksums; o app grava o `id` e o
  `updated_at` do asset retornado pela API do GitHub e só troca o binário quando
  o GitHub informa um asset novo, sempre por HTTPS.
- Um app que baixa e executa binários em `%LOCALAPPDATA%` tem exatamente a
  assinatura comportamental que um EDR marca como suspeita. Se a sua estação tem
  agente corporativo, é esperado gerar detecção — instale numa máquina pessoal ou
  crie a exclusão consciente.
- Todo subprocesso roda com `CREATE_NO_WINDOW` e sem `shell=True`; a URL entra
  como argumento de lista, nunca concatenada em string de shell.
- `--ignore-config` é passado sempre, para o app não herdar um `yt-dlp.conf`
  do sistema que mudaria o comportamento sem você saber.

## Ideias já implementadas além do pedido

- Fila com downloads simultâneos configuráveis e cancelamento por item.
- Detecção de link na área de transferência ao focar a janela.
- Suporte a playlist (subpasta com numeração) e a `--download-archive`.
- SponsorBlock, legendas embutidas, capa, metadados e capítulos.
- Cookies do navegador para conteúdo com login ou restrição de idade.
- Aceita uma URL como argumento de linha de comando (`"baixador-ytdlp.exe" <link>`),
  o que permite usar como alvo de "Abrir com" ou de um atalho.
- Instância única, ícone próprio na barra de tarefas e log de crash.
