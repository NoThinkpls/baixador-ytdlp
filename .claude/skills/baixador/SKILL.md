---
name: baixador
description: Executa o Baixador-YTDLP pelo terminal, sem abrir a janela: baixar, analisar link, legendar com Whisper, cortes verticais e ferramentas FFmpeg. Use em /baixador ou ao pedir para baixar, legendar ou cortar vídeo.
---

# Baixador-YTDLP pelo terminal

O app Baixador-YTDLP instalado no computador tem um modo de linha de comando (versão 1.16.0
ou mais nova). Transforme o pedido em um comando `cli`, rode e responda com o resultado em
português, curto: o que foi feito e onde ficou o arquivo.

## 1. Achar o executável (uma vez por conversa)

Rode no terminal Bash (no Windows é o Git Bash do Claude Code):

```bash
for c in "$(cygpath -u "${LOCALAPPDATA:-}" 2>/dev/null)/Programs/baixador-ytdlp/baixador-ytdlp.exe" \
         "/c/Program Files/baixador-ytdlp/baixador-ytdlp.exe" \
         "/Applications/baixador-ytdlp.app/Contents/MacOS/baixador-ytdlp" \
         "$(command -v baixador-ytdlp)"; do
  [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; break; }; done
```

Guarde o caminho como `B` e confira com `"$B" cli status`. Se nada for encontrado, pergunte
onde está o app (pode ser a versão portátil) ou se ele quer instalá-lo; se `cli` não for
reconhecido, o app é anterior à 1.16.0 e precisa ser atualizado.

## 2. Como rodar

- Sempre `"$B" cli <comando> ...` com aspas no caminho e nos argumentos com espaço.
- O resultado é UM JSON no stdout (`"ok": true` ou `"ok": false, "erro": "..."`); o andamento
  sai no stderr. Código 0 = sucesso, 1 = falha, 2 = comando errado, 130 = cancelado.
- Download, legenda e cortes podem demorar minutos: use timeout longo (10 min) ou rode em
  segundo plano e acompanhe.
- Se o stdout vier vazio (PowerShell/cmd no Windows), repita com `--json-saida "$TEMP/baixador.json"`
  e leia o arquivo.
- Sem pasta no pedido, não passe `--pasta`: vale a pasta de downloads do app. Os padrões das
  Configurações do app (qualidade, idioma, modelo, estilo dos cortes) valem quando a opção é
  omitida; só passe o que a pessoa pediu.

## 3. Comandos

| Pedido | Comando |
| --- | --- |
| "baixa esse vídeo" | `cli baixar URL` |
| "em 720p", "em mkv" | `--qualidade 720`, `--container mkv` |
| "só o áudio", "em mp3" | `--audio --formato-audio mp3` |
| "do minuto 2 ao 5" | `--inicio 2:00 --fim 5:00` |
| "a playlist toda", "os 3 primeiros" | `--playlist`, `--playlist --itens 1-3` |
| "com legenda do YouTube" | `--legendas pt,en` |
| "sem patrocínio" | `--sponsorblock` |
| "baixa e legenda" | `--legendar` (+ `--idioma`, `--modelo`) |
| "o que tem nesse link?", "quais qualidades?" | `cli info URL` (`--formatos`) |
| "legenda esse arquivo" | `cli legendar ARQ` (`--formato srt\|vtt\|txt\|json`, `--idioma pt\|auto`, `--modelo`, `--traduzir`) |
| "faz um corte de 1:20 a 2:05" | `cli cortar FONTE --corte "1:20-2:05=Título"` (repita `--corte`) |
| "seguindo quem fala", "fundo desfocado", "cortado no centro" | `--enquadramento track\|blur\|crop` |
| "título fixo em cima", "estilo podcast" | `--titulo fixo` (+ `--linha-titulo "PODCAST X · EP. 12"`) |
| "título que aparece e some" | `--titulo animado` (`--duracao-titulo 3`, `--altura-titulo 80`) |
| "com efeitos", "zoom na ênfase", "usa meus sons" | `--efeitos`, `--zoom-enfase`, `--pasta-sons DIR` |
| "legenda karaokê", "em amarelo", "2 palavras" | `--animacao karaoke`, `--cor-destaque #FFD700`, `--palavras 2` |
| "sem cortar as pausas", "com barra", "volume certo", "com .srt" | `--no-remover-pausas`, `--barra`, `--normalizar`, `--srt` |
| "extrai o áudio", "comprime", "corta o trecho", "gif" | `cli ferramenta audio\|compress\|trim\|gif ARQ` |
| "deixa com menos de 25 MB" | `cli ferramenta target_size ARQ --tamanho-mb 25` |
| "converte pra vertical" | `cli ferramenta shorts ARQ` |
| "grava a legenda no vídeo" | `cli ferramenta burn VIDEO --legenda ARQ.srt` |
| "acelera 2x", "gira", "tira o som", "normaliza" | `speed --escolha 2`, `rotate --escolha cw`, `mute`, `normalize` |
| "o que eu baixei?" | `cli historico --limite 10` |
| "atualiza o yt-dlp", "tá dando erro em todo vídeo" | `cli preparar --atualizar` |
| "manda o diagnóstico" | `cli status --exportar ARQ.zip` |

Referência completa: `"$B" cli ajuda` e `"$B" cli <comando> --help`.

## 4. Tipos de corte

- **Enquadramento**: `track` segue quem está falando (rosto e, com várias pessoas, o detector
  de quem fala; bom para podcast e entrevista), `blur` mostra o vídeo inteiro com fundo
  desfocado (bom para slides, telas e plano aberto), `crop` corta no centro.
- **Título**: `fixo` é a faixa escura no topo com o título num cartão o corte inteiro e o vídeo
  embaixo, com uma linha pequena opcional acima (`--linha-titulo`: podcast, convidado, pregador,
  episódio); o título cabe em até 3 linhas (3 a 8 palavras, até 45 caracteres). `animado` entra
  no começo e some; precisa caber em uma linha (até 4 palavras, 20 caracteres).
- Sem pedido explícito, não passe essas opções: vale o que a pessoa deixou salvo na página Cortes.

## 5. Cortes escolhidos pelo Claude

Se pedirem "os melhores momentos" sem tempos: rode `cli legendar VIDEO --formato json`
(com link, primeiro `cli baixar`), leia a transcrição, escolha de 1 a 5 trechos de 30 s a 90 s
que façam sentido sozinhos (começam no início de uma frase, terminam no fim de um pensamento),
proponha os tempos e títulos e, com o ok da pessoa, gere os cortes. Cada corte tem no máximo
10 minutos.

- Só tempos e títulos: um `--corte "INICIO-FIM=TÍTULO"` por trecho.
- Com sons e zoom em palavras específicas, monte o **plano da IA** numa linha e passe em
  `--plano` (texto ou arquivo):
  `{"bx":1,"t":"f","l":"LINHA DE CIMA","c":[["12:03","12:58","TÍTULO",[["12:15","graça","i",1]]]]}`
  - `t`: `"f"` título fixo ou `"a"` animado; `l`: linha de cima do título fixo (sem ela, tire
    o `"l"`). `--titulo`/`--linha-titulo` na linha de comando têm prioridade.
  - Cada corte é `[início, fim, TÍTULO EM MAIÚSCULAS, efeitos]`, respeitando o tamanho do tipo
    de título; cada efeito é `[tempo, palavra dita naquele momento, som, zoom]`.
  - Som: `w` troca de assunto (só numa pausa), `p` destaca palavra ou número, `i` frase forte
    ou clímax (no máximo um por corte), `d` ideia-chave ou conclusão, `s` tensão que termina
    na palavra, `""` só zoom. Zoom 1/0.
  - De 1 a 3 efeitos por corte, nada nos 2 primeiros segundos e pelo menos 4 s entre dois
    sons. O app acha o tempo exato da palavra e liga sons e zoom sozinho.
  - Aspas retas; aspas dentro do título como `\"`. Detalhes em `docs/PLANO-DA-IA.md`.

## 6. Erros

- Mostre a mensagem de `erro` como veio; ela já é a explicação amigável do app.
- Cookies só quando o erro falar em login, conta, idade, bot-check ou conteúdo privado: então
  pergunte qual navegador está logado e repita com `--cookies-navegador chrome|edge|firefox|brave`.
  Nunca use cookies como primeira tentativa nem para outros erros.
- Erro geral de extração em vários links: `cli preparar --atualizar` e tente de novo.
- GPU é opcional: o app volta para a CPU sozinho; não peça para instalar nada da NVIDIA.
- Nunca mostre nem copie cookies, tokens ou links privados nas respostas.
