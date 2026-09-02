<div align="center">

<img src="assets/icon.png" width="96" alt="">

# baixador-ytdlp

**Baixador de vídeo para Windows 11, com interface Fluent, construído sobre o yt-dlp e o FFmpeg.**

Instala e atualiza as próprias dependências, analisa o link, mostra todas as qualidades
disponíveis e baixa na melhor por padrão.

[![build](https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml/badge.svg)](https://github.com/NoThinkpls/baixador-ytdlp/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?label=vers%C3%A3o)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![downloads](https://img.shields.io/github/downloads/NoThinkpls/baixador-ytdlp/total?label=downloads)](https://github.com/NoThinkpls/baixador-ytdlp/releases)
![Windows](https://img.shields.io/badge/plataforma-Windows%2010%2F11-0078D4)

### [⬇ Baixar o instalador](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe)

</div>

<!--
  Dica: para colocar o print da janela aqui, abra uma issue nova no próprio
  repositório, arraste a imagem para dentro da caixa de comentário e copie a URL
  que o GitHub gera. Cole abaixo e feche a issue sem publicar.

  <p align="center"><img src="URL_DA_IMAGEM" width="820" alt="Tela principal"></p>
-->

---

## O que ele faz

- **Cuida das dependências sozinho.** Na primeira execução baixa o `yt-dlp` e o `FFmpeg`;
  nas seguintes verifica atualização e instala sem perguntar, com barra de progresso.
- **Mostra todas as qualidades.** Depois de analisar o link, uma tabela lista resolução,
  FPS, codec, tamanho e HDR de cada variante. A melhor já vem selecionada.
- **Formato à sua escolha.** MP4 por padrão; também MKV, WebM ou "manter original".
  Modo só-áudio com MP3, M4A, Opus, FLAC ou WAV.
- **Fila com downloads paralelos**, progresso, velocidade, ETA e cancelamento por item.
- **Playlists** em subpasta numerada, com histórico opcional para não rebaixar o que já veio.
- **Extras:** SponsorBlock, legendas embutidas, capa, metadados, capítulos, cookies do
  navegador para conteúdo com login, detecção de link na área de transferência.
- **Conversão por GPU (opcional).** NVENC em H.264, HEVC ou AV1 — leia a seção sobre GPU
  antes de ligar.

## Instalação

Baixe o instalador mais recente em **[Releases](../../releases)** e execute.

A instalação é por usuário, sem UAC, e cria o atalho no Menu Iniciar — é isso que faz o
programa aparecer quando você digita o nome na busca do Windows. Também existe a versão
portátil (a pasta inteira) nos artefatos de cada build.

> O executável não é assinado, então o SmartScreen mostra "Windows protegeu o seu
> computador" na primeira execução: **Mais informações → Executar assim mesmo**. Binários
> feitos com PyInstaller também costumam gerar falso positivo em antivírus menores, por
> causa do bootloader compartilhado. O `SHA256SUMS.txt` publicado junto de cada release
> permite conferir que o arquivo é o mesmo que saiu do build.

## Rodando a partir do código

```powershell
git clone https://github.com/NoThinkpls/baixador-ytdlp.git
cd baixador-ytdlp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Requer Python 3.11 ou superior.

## Compilando

Na sua máquina:

```powershell
.\build.ps1              # gera dist\baixador-ytdlp\baixador-ytdlp.exe
.\build.ps1 -Installer   # gera também dist\installer\baixador-ytdlp-1.0.0-setup.exe
```

O `-Installer` precisa do [Inno Setup 6](https://jrsoftware.org/isdl.php).

Ou pelo GitHub Actions, sem instalar nada: qualquer push na `main` compila e publica o
`.exe` e o setup como artefatos do run. Uma tag `v1.0.0` gera uma release com o instalador
e os hashes anexados.

## Sobre a GPU

**O download não usa a GPU.** Baixar vídeo é rede e cópia de arquivo — não existe "baixar
com mais qualidade usando a placa". A melhor qualidade possível é o stream original
remuxado, sem reencode, e é o que o programa faz por padrão.

A placa entra na aba **GPU e conversão**, opcional e desligada por padrão: reencoda o
arquivo já baixado com NVENC em H.264, HEVC ou AV1 (a série RTX 40 é a primeira com
encoder AV1 em hardware). Serve para compatibilidade com aparelhos antigos ou para reduzir
o tamanho do arquivo. Toda conversão perde qualidade em relação ao original — se o objetivo
é qualidade máxima, deixe desligada.

A detecção é automática: sem driver NVIDIA ou sem encoder NVENC no FFmpeg, a seção aparece
desabilitada em vez de falhar no meio do processo.

## Notas de segurança

- O `yt-dlp.exe` é conferido contra o `SHA2-256SUMS` publicado no próprio release antes de
  substituir o binário local. Download que não bate no hash é descartado.
- As builds do FFmpeg (BtbN) não publicam checksums; o programa grava o `id` e o
  `updated_at` do asset retornado pela API do GitHub e só troca o binário quando o GitHub
  informa um asset novo, sempre por HTTPS.
- Todo subprocesso roda com `CREATE_NO_WINDOW` e sem `shell=True`; a URL entra como
  argumento de lista, nunca concatenada em string de shell.
- `--ignore-config` é passado sempre, para o programa não herdar um `yt-dlp.conf` do
  sistema que mudaria o comportamento sem você perceber.
- **Um aplicativo que baixa e executa binários em `%LOCALAPPDATA%` tem exatamente a
  assinatura comportamental que um EDR marca como suspeita.** Em máquina pessoal, tudo
  bem; em estação com agente corporativo, espere detecção — instale com consciência disso
  ou não instale.

## Estrutura

```
main.py                     ponto de entrada, instância única, ícone
baixador_ytdlp/
├── config.py               caminhos e settings.json
├── tools.py                instala e atualiza yt-dlp e FFmpeg
├── gpu.py                  detecção de NVENC
├── probe.py                yt-dlp -J e montagem da lista de qualidades
├── downloader.py           linha de comando, leitura de progresso, NVENC
├── workers.py              QThreads (nada de I/O na thread da interface)
└── ui/                     setup_dialog, home_page, queue_page, settings_page, main_window
.github/workflows/build.yml compilação e release automáticas
installer.iss               receita do Inno Setup
baixador_ytdlp.spec         receita do PyInstaller
```

O progresso do download é lido pelo `--progress-template` do yt-dlp, com campos separados
por `\x1f`, em vez de regex sobre a barra colorida — parsing determinístico e imune a
mudança de layout da saída.

## Onde ficam as coisas

| O quê | Caminho |
|---|---|
| Binários (yt-dlp, ffmpeg) | `%LOCALAPPDATA%\BaixadorYtdlp\bin` |
| Configurações | `%LOCALAPPDATA%\BaixadorYtdlp\settings.json` |
| Log de erro fatal | `%LOCALAPPDATA%\BaixadorYtdlp\logs\crash.log` |
| Vídeos | `Vídeos\baixador-ytdlp` (configurável) |

Os binários ficam fora de `Program Files` de propósito: a atualização automática não
precisa de elevação nem de prompt de UAC.

## Uso responsável

Esta é uma interface para o [yt-dlp](https://github.com/yt-dlp/yt-dlp). Baixar conteúdo
pode violar os termos de uso da plataforma ou a legislação de direito autoral, dependendo
do que se baixa e do que se faz com o arquivo. A responsabilidade é de quem usa.

## Créditos e licenças

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — Unlicense
- [FFmpeg](https://ffmpeg.org/) — builds GPL do [BtbN](https://github.com/BtbN/FFmpeg-Builds)
- [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) — GPLv3 na
  versão comunitária

O yt-dlp e o FFmpeg **não são distribuídos junto** do instalador: são baixados na primeira
execução, direto dos repositórios oficiais. O código deste repositório está sob a licença
MIT (veja [LICENSE](LICENSE)).
