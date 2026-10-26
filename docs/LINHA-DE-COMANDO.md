# Linha de comando

Desde a 1.16.0 o mesmo executável do app aceita comandos sem abrir a janela:

```
baixador-ytdlp cli <comando> [opções]
```

Os comandos usam exatamente o mesmo motor da interface (download, legendador, cortes e
ferramentas) e as **configurações salvas no app como padrão**: pasta de downloads, contêiner,
idioma e modelo do Whisper, estilo dos cortes, cookies e proxy. Nada é regravado nas
Configurações. A janela pode continuar aberta enquanto um comando roda.

O uso pensado é o **Claude Code** no seu computador: você pede no chat ("baixa esse vídeo em
720p", "faz três cortes desse vídeo") e o Claude executa o comando certo. A skill
[`baixador`](../.claude/skills/baixador/SKILL.md) ensina isso a ele.

## Onde está o executável

| Instalação | Caminho |
| --- | --- |
| Windows (instalador, por usuário) | `%LOCALAPPDATA%\Programs\baixador-ytdlp\baixador-ytdlp.exe` |
| Windows (instalado para todos) | `C:\Program Files\baixador-ytdlp\baixador-ytdlp.exe` |
| Windows portátil | `baixador-ytdlp.exe` na pasta extraída |
| macOS | `/Applications/baixador-ytdlp.app/Contents/MacOS/baixador-ytdlp` |
| Linux (.deb) | `baixador-ytdlp` |
| Código-fonte | `python main.py cli …` |

## Saída

- **stdout**: um único objeto JSON com o resultado, sempre com `"ok": true` ou
  `"ok": false, "erro": "…"`. A mensagem de erro é a mesma, amigável, que a janela mostraria.
- **stderr**: o andamento, uma linha por etapa e a cada 5%.
- `--json-saida ARQ` (em qualquer posição) grava também o JSON num arquivo.
- Código de saída: `0` sucesso, `1` falha, `2` uso incorreto, `130` cancelado (Ctrl+C).

**Windows:** o executável é de interface gráfica. No **Git Bash** (o terminal que o Claude Code
usa no Windows) a saída aparece e o terminal espera o fim do comando. No PowerShell e no cmd o
prompt volta antes de o comando terminar; ali use
`Start-Process -Wait -NoNewWindow baixador-ytdlp.exe -ArgumentList 'cli','status'` ou
`--json-saida` e leia o arquivo depois.

## Comandos

### `status`

Versão, pastas (dados, binários, downloads, log) e os padrões das Configurações.
`--gpu` detecta a GPU e os encoders de hardware; `--exportar ARQ` gera o ZIP de diagnóstico
redigido (o mesmo de Configurações → Diagnóstico).

### `preparar`

Baixa ou atualiza yt-dlp, FFmpeg e Deno nas fontes oficiais, com SHA-256, como a tela de
preparação. Os outros comandos já fazem isso sozinhos; `--atualizar` força a consulta agora.

### `info URL`

Analisa o link sem baixar: título, canal, duração, playlist, capítulos, legendas do site.
`--formatos` lista cada formato com o seletor para usar em `baixar --formato-id`.

### `baixar URL [URL…]`

| Opção | Efeito |
| --- | --- |
| `--pasta DIR` | destino (padrão: pasta de downloads) |
| `--audio`, `--formato-audio mp3\|m4a\|opus\|flac\|wav` | só o áudio |
| `--qualidade 1080` | limite de altura (`melhor` é o padrão) |
| `--formato-id SELETOR` | seletor exato vindo de `info --formatos` |
| `--container mp4\|mkv\|webm\|original` | contêiner do vídeo |
| `--inicio 1:30 --fim 4:00` | só um trecho |
| `--playlist` / `--no-playlist`, `--itens 1-3,7` | playlist inteira ou itens; o padrão segue o link |
| `--nome NOME` | nome do arquivo, sem extensão |
| `--legendas pt,en` | baixa as legendas publicadas no site |
| `--sponsorblock` | remove patrocínios |
| `--legendar` (+ `--idioma`, `--modelo`, `--formato`) | gera legenda com o Whisper ao terminar |
| `--cookies-navegador chrome`, `--cookies-arquivo ARQ` | **só** quando o erro pedir login, bot-check ou conteúdo restrito |

Falhas de rede repetem sozinhas, como na fila (Configurações → Tentativas automáticas).

### `legendar ARQUIVO`

Transcreve com o Whisper local (CUDA na NVIDIA, MLX no Mac, CPU nos demais).
`--idioma pt|en|…|auto`, `--modelo tiny|base|small|medium|large-v3-turbo|large-v3`,
`--formato srt|vtt|ass|karaoke|txt|json`, `--traduzir` (para inglês), `--prompt "nomes próprios"`
e `--saida ARQ`. Na primeira vez o modelo escolhido é baixado.

### `cortar FONTE --corte INICIO-FIM[=Título] [--corte …]`

Cortes verticais 1080x1920 com legenda palavra a palavra, como a página Cortes. A fonte é um
arquivo local ou um link (só os trechos são baixados). Exemplo:

```
baixador-ytdlp cli cortar video.mp4 --corte "1:20-2:05=O gancho" --corte 10:00-10:45 --efeitos
```

Enquadramento (`--enquadramento`): `track` segue quem está falando (detector de rosto e, com
mais de uma pessoa, o LR-ASD decide quem fala), `blur` mostra o vídeo inteiro com fundo
desfocado e `crop` corta no centro.

Título (`--titulo`): `animado` entra no começo e some (`--duracao-titulo S`, 0 = o corte
inteiro; `--altura-titulo %`, 0 = automático); `fixo` é a faixa escura no topo com o título
num cartão na cor de destaque o corte inteiro, e o vídeo embaixo. `--linha-titulo TEXTO` põe a
linha pequena acima do título fixo (nome do podcast, convidado, episódio). O título fixo
diminui sozinho para caber em até 3 linhas.

Outras opções: `--pasta`, `--animacao highlight|color|karaoke|word|pop|none`,
`--cor-destaque #RRGGBB`, `--palavras 1-4`, `--idioma`, `--modelo` e as chaves liga/desliga
`--remover-pausas`, `--zoom-emendas`, `--barra`, `--normalizar`, `--srt`, `--efeitos`,
`--zoom-enfase` (cada uma com `--no-…`). Sem a opção, vale o que está salvo na página Cortes.

No lugar de `--corte`, `--plano` recebe o [plano da IA](PLANO-DA-IA.md) (`{"bx":1,"c":[…]}`,
colado ou num arquivo): cortes, títulos e onde entra cada som e zoom. Se o plano traz `"t"`
(`"f"` fixo, `"a"` animado) e `"l"` (linha de cima), eles valem quando `--titulo` e
`--linha-titulo` não foram passados. Como na página, um plano com sons ou zoom liga
**Efeitos sonoros** e **Zoom na ênfase**. `--pasta-sons DIR` usa os seus sons.

Para o Claude escolher os melhores momentos: `legendar video.mp4 --formato json`, ler a
transcrição com os tempos e então chamar `cortar` com os intervalos escolhidos ou com um plano.

### `ferramenta OPERACAO ARQUIVO`

As ferramentas da página Ferramentas: `trim`, `audio`, `remux`, `compress`, `target_size`,
`shorts`, `burn`, `soft_sub`, `convert`, `speed`, `rotate`, `mute`, `normalize`, `gif`, `frame`,
`extract_subs`, `strip`. Opções: `--saida`, `--inicio`, `--fim`, `--escolha` (o parâmetro da
ferramenta: `mp3`, `2`, `cw`, `640`, `-14`…), `--legenda` (burn/soft_sub), `--idioma-legenda`,
`--tamanho-mb` (target_size), `--rapido` (trim sem reencodar) e `--sem-desfoque` (shorts).
Sem `--saida`, o arquivo vai ao lado do original com um sufixo (`_audio`, `_trecho`…), sem
sobrescrever nada.

### `historico`

Os últimos itens do Histórico do app (`--limite N`).

## Limitações

- O que é feito pela linha de comando ainda não entra no Histórico da janela.
- Um comando por vez é o recomendado: dois downloads simultâneos funcionam, mas não respeitam o
  limite de downloads paralelos da fila.
