<div align="center">

<img src="assets/icon.png" width="96" alt="">

# baixador-ytdlp

**Baixador de vídeo para Windows 10/11, com interface Fluent, construído sobre o yt-dlp e o FFmpeg.**

Instala e atualiza as próprias dependências, analisa o link, mostra todas as qualidades
disponíveis e baixa na melhor por padrão.

[![versão](https://img.shields.io/github/v/release/NoThinkpls/baixador-ytdlp?label=vers%C3%A3o&color=0078D4)](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest)
[![downloads](https://img.shields.io/github/downloads/NoThinkpls/baixador-ytdlp/total?label=downloads&color=2EA043)](https://github.com/NoThinkpls/baixador-ytdlp/releases)
![plataforma](https://img.shields.io/badge/plataforma-Windows%2010%2F11-0078D4)
![licença](https://img.shields.io/badge/licen%C3%A7a-MIT-lightgrey)

### [⬇ Baixar o instalador](https://github.com/NoThinkpls/baixador-ytdlp/releases/latest/download/baixador-ytdlp-setup.exe)

</div>

<!-- Para colocar um print aqui: abra uma issue nova, arraste a imagem para a caixa de
     comentário, copie a URL que o GitHub gera e cole abaixo. Feche a issue sem publicar.
     <p align="center"><img src="URL_DA_IMAGEM" width="820" alt="Tela principal"></p> -->

---

<div align="center">

[O que ele faz](#o-que-ele-faz) ·
[Instalação](#instalação) ·
[Novidades](#novidades-da-120) ·
[Compilando](#compilando) ·
[GPU](#sobre-a-gpu) ·
[Assinatura](#assinatura-digital-e-o-aviso-do-windows) ·
[Segurança](#notas-de-segurança) ·
[Estrutura](#estrutura)

</div>

---

## O que ele faz

- **Cuida das dependências sozinho.** Na primeira execução baixa o `yt-dlp` e o `FFmpeg`;
  nas seguintes verifica atualização e instala sem perguntar, com barra de progresso.
- **Mostra todas as qualidades.** Depois de analisar o link, uma tabela lista resolução,
  FPS, codec, tamanho e HDR de cada variante. A melhor já vem selecionada.
- **Formato à sua escolha.** MP4 por padrão; também MKV, WebM ou "manter original".
  Modo só-áudio com MP3, M4A, Opus, FLAC ou WAV.
- **Pasta de saída por download.** Uma caixa de seleção na tela Baixar libera o campo de
  destino e o botão Procurar; desmarcada, o programa usa a pasta padrão e mostra qual é.
  A última pasta escolhida fica lembrada.
- **Recorte por tempo.** Baixa só o trecho pedido (`--download-sections`), com corte em
  keyframe — não baixa o vídeo inteiro para depois cortar.
- **Fila com downloads paralelos**, progresso, velocidade, ETA, cancelamento, *tentar de
  novo* nos itens que falharam e a saída completa do yt-dlp copiável em um clique.
- **Histórico** do que já foi baixado, com abrir a pasta, gerar legenda e baixar de novo.
- **Playlists** em subpasta numerada, com histórico opcional para não rebaixar o que já veio.
- **Progresso na barra de tarefas** do Windows e **atalhos**: `Ctrl+V` cola e analisa,
  `Ctrl+Enter` baixa, `Esc` cancela a transcrição, `Ctrl+1..4` troca de página.
- **Extras:** SponsorBlock, legendas embutidas, capa, metadados, capítulos, cookies do
  navegador para conteúdo com login, detecção de link na área de transferência.
- **Conversão por GPU (opcional).** NVENC em H.264, HEVC ou AV1 — leia a
  [seção sobre GPU](#sobre-a-gpu) antes de ligar.
- **Legendador local.** Transcreve vídeo ou áudio com `faster-whisper`, usando CUDA/float16
  na NVIDIA quando disponível e CPU/int8 como fallback. Exporta SRT, WebVTT, ASS, TXT e JSON.
  Inclui VAD, pré-processamento 16 kHz e filtro opcional contra alucinações. Aceita arquivo
  arrastado para dentro da janela e recebe direto o que veio da fila ou do histórico.
- **Ajuste automático ao hardware.** Fragmentos simultâneos, downloads em paralelo e threads
  do Whisper saem dos núcleos realmente disponíveis, em vez de um número fixo.

## Instalação

Baixe o instalador mais recente em **[Releases](../../releases)** e execute.

A instalação é por usuário, sem UAC, e cria o atalho no Menu Iniciar — é isso que faz o
programa aparecer quando você digita o nome na busca do Windows.

> [!WARNING]
> **O instalador não é assinado digitalmente.** O Windows vai mostrar *"Windows protegeu o
> seu computador"* na primeira execução, e alguns antivírus podem reclamar. Isso é esperado.
> A seção **[Assinatura digital](#assinatura-digital-e-o-aviso-do-windows)** explica por quê,
> o que fazer e como conferir que o arquivo é autêntico.

## Novidades da 1.2.0

**Interface**

- **Pasta de saída por download**, com caixa de seleção na própria tela Baixar.
- **Ícones da navegação refeitos.** Baixar e Legendar usavam o mesmo ícone, e a Fila usava o
  hambúrguer de menu. Agora cada página carrega o desenho da coisa que ela faz.
- **Recorte por tempo**, cortando na origem.
- **Tentar de novo** nos itens da fila que falharam, com a saída completa do yt-dlp copiável.
- **Página de histórico** com abrir na pasta, gerar legenda e baixar de novo.
- **Atalhos de teclado** e progresso no ícone da barra de tarefas.
- **Fila → Legendar** em um clique, e arrastar-e-soltar na aba de transcrição.

**Desempenho**

- **O PyTorch saiu do pacote** — cerca de 2,5 GB a menos. Detalhes em [Compilando](#compilando).
- **A abertura não consulta mais o pip toda vez.** Cache de 24 h, configurável.
- **Análise de playlist extrai um vídeo, não os N.** Playlist longa deixou de levar minutos.
- **Detecção de GPU saiu da thread da interface**, que congelava por segundos após o setup.
- **Padrões calculados a partir da máquina** — fragmentos, downloads simultâneos e threads do
  Whisper saem dos núcleos realmente disponíveis.

**Correções**

- "Salvar como" sem mídia escolhida derrubava a aba Legendar.
- A URL gravada no histórico vinha do campo da tela, não do download concluído.
- `embed_chapters` e `embed_subs` existiam nas configurações sem controle na interface.
- Remux redundante em arquivo que já estava no container certo.
- O handle do mutex de instância única era uma variável local.
- QThreads de análise, download e transcrição nunca eram destruídos.

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
.\build.ps1 -Installer   # gera também dist\installer\BaixadorYtdlp-1.2.0-setup.exe
```

O `-Installer` localiza o [Inno Setup 6](https://jrsoftware.org/isdl.php) tanto em
`Program Files` quanto em `Program Files (x86)`. Se ele ainda não estiver instalado,
use uma única vez:

```powershell
.\build.ps1 -Installer -InstallInnoSetup
```

Isso instala o compilador pelo `winget`, cria o setup e grava um arquivo `.sha256` ao lado
do instalador. O `build.cmd` é uma alternativa que abre o PowerShell com a política
temporária adequada, caso o Windows bloqueie a execução direta de `.ps1`.

O repositório também traz `.github/workflows/build.yml`, que compila e publica a release
sozinho a cada tag `v*`. Ele só entra em ação em contas com o GitHub Actions habilitado —
se o GitHub exibir *"Actions has been disabled for this user"*, nenhum workflow inicia e o
build local acima é o caminho.

> [!NOTE]
> **O PyTorch saiu do pacote.** O `faster-whisper` executa sobre o CTranslate2 — o torch
> estava lá só para responder "existe CUDA?" e para carregar cuBLAS/cuDNN, custando cerca de
> 2,5 GB no executável. A detecção agora vem do driver (`nvcuda.dll`) e do próprio
> CTranslate2, e as bibliotecas CUDA são os pacotes oficiais da NVIDIA
> (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`), instalados no runtime do usuário apenas
> quando existe GPU. Para voltar ao comportamento antigo, basta acrescentar `"torch"` em
> `PACKAGES`, no `runtime.py`.
>
> A verificação continua **bloqueante antes de liberar a interface**, como antes, mas agora
> com cache: se os pacotes estão na versão certa, a variante (CPU/CUDA) bate com a máquina e
> a última checagem foi dentro do prazo configurado (24 h por padrão, ajustável em
> Configurações), a abertura pula a consulta ao pip inteira. Se estiver offline, usa a cópia
> embutida já funcional e informa isso na tela inicial. O yt-dlp e o FFmpeg continuam
> atualizados no mesmo fluxo.

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

## Assinatura digital e o aviso do Windows

**Este programa não é assinado digitalmente.** Não é descuido nem falta de cuidado com o
código: é uma limitação prática que vale explicar por inteiro, para você decidir com
informação em vez de confiar às cegas.

### O que você vai ver

Ao executar o instalador pela primeira vez, aparece a tela azul do SmartScreen:

> **Windows protegeu o seu computador**
> O Microsoft Defender SmartScreen impediu a inicialização de um aplicativo não reconhecido.

Para instalar mesmo assim: **Mais informações → Executar assim mesmo**.

Alguns antivírus menores também podem marcar o arquivo. O motivo é conhecido e não tem
relação com o que este programa faz: executáveis gerados com **PyInstaller** compartilham o
mesmo *bootloader*, que já foi usado por malware no passado — então o detector marca o
carregador, não o código. É um falso positivo clássico dessa ferramenta.

### Por que não está assinado

Assinar exige um certificado de code signing emitido por uma autoridade certificadora, com
validação de identidade e custo anual. Três coisas pesaram na decisão:

1. **O caminho barato não está disponível no Brasil.** O *Azure Artifact Signing*
   (ex-Trusted Signing) da Microsoft custa cerca de US$ 10/mês, dispensa token físico e
   integra direto com o GitHub Actions — mas a validação de identidade só aceita
   desenvolvedores individuais nos EUA e Canadá, e organizações numa lista que não inclui
   o Brasil.
2. **Certificado EV não pula mais o SmartScreen.** Isso funcionava anos atrás e a própria
   Microsoft documenta que o comportamento acabou. Ou seja: mesmo pagando por um EV
   (US$ 400+/ano), um binário novo continuaria mostrando o aviso.
3. **A reputação é que remove o aviso, não a assinatura.** O SmartScreen libera um programa
   depois de acumular downloads limpos ao longo de várias versões, mantendo a mesma
   identidade de assinatura. Para um projeto pessoal com poucos downloads, isso praticamente
   não acontece.

O que a assinatura *traria* de imediato seria o nome do publicador verificado no lugar de
"Publicador desconhecido", e menos falso positivo de antivírus. A intenção é resolver isso
via **[SignPath Foundation](https://signpath.org/)**, que oferece assinatura gratuita para
projetos open source — quando/se for aprovado, o aviso e esta seção mudam junto.

### Como conferir que o arquivo é autêntico

Já que não há assinatura, a verificação honesta é o hash. Toda release publica um
`SHA256SUMS.txt` com o hash do instalador. Para conferir, no PowerShell:

```powershell
Get-FileHash .\baixador-ytdlp-setup.exe -Algorithm SHA256
```

Compare com a linha correspondente do `SHA256SUMS.txt` da release. Batendo, o arquivo é
byte a byte o que foi publicado, e o código-fonte que o originou é o da tag correspondente.

As notas de cada release dizem se ela foi compilada pela automação do repositório ou
localmente — quando sai do GitHub Actions, o log do build fica público em
**[Actions](../../actions)** e todo o processo é auditável de fora.

### Se você não estiver confortável

É uma posição legítima. Duas alternativas:

- **Rode a partir do código** ([seção acima](#rodando-a-partir-do-código)): sem executável,
  sem SmartScreen, e você lê tudo o que executa.
- **Não instale em estação corporativa.** Veja a última nota da seção seguinte.

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

> [!CAUTION]
> **Um aplicativo que baixa e executa binários em `%LOCALAPPDATA%` tem exatamente a
> assinatura comportamental que um EDR marca como suspeita.** Em máquina pessoal, tudo bem;
> em estação com agente corporativo, espere detecção — instale com consciência disso ou não
> instale.

## Estrutura

```text
main.py                       ponto de entrada, instância única, ícone
baixador_ytdlp/
├── config.py                 caminhos e settings.json
├── tools.py                  instala e atualiza yt-dlp e FFmpeg
├── runtime.py                bootstrap do runtime de transcrição, com cache
├── gpu.py                    detecção de NVENC
├── hardware.py               núcleos, RAM e os padrões calculados a partir deles
├── probe.py                  yt-dlp -J e montagem da lista de qualidades
├── downloader.py             linha de comando, leitura de progresso, NVENC
├── transcription.py          Whisper, filtro de qualidade e exportação de legendas
├── history.py                histórico dos downloads concluídos (JSON)
├── taskbar.py                progresso no ícone da barra de tarefas (ITaskbarList3)
├── workers.py                QThreads (nada de I/O na thread da interface)
└── ui/                       setup_dialog, home, queue, transcription, history,
                              settings e main_window
.github/workflows/build.yml   compilação e release automáticas
installer.iss                 receita do Inno Setup
baixador_ytdlp.spec           receita do PyInstaller
build.ps1 · build.cmd         build local, com ou sem instalador
```

A análise de playlist usa `--playlist-items 1`: a tabela de qualidades precisa dos formatos
de **um** vídeo, e extrair os formatos dos 200 itens de uma playlist só para montá-la levava
minutos. A contagem de itens, quando não vem no JSON, sai de uma chamada `--flat-playlist`,
que é uma requisição só.

O progresso do download é lido pelo `--progress-template` do yt-dlp, com campos separados
por `\x1f`, em vez de regex sobre a barra colorida — parsing determinístico e imune a
mudança de layout da saída.

## Onde ficam as coisas

| O quê | Caminho |
|---|---|
| Binários (yt-dlp, ffmpeg) | `%LOCALAPPDATA%\BaixadorYtdlp\bin` |
| Configurações | `%LOCALAPPDATA%\BaixadorYtdlp\settings.json` |
| Histórico | `%LOCALAPPDATA%\BaixadorYtdlp\history.json` |
| Modelos do Whisper | `%LOCALAPPDATA%\BaixadorYtdlp\models` |
| Runtime de transcrição | `%LOCALAPPDATA%\BaixadorYtdlp\runtime` |
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
