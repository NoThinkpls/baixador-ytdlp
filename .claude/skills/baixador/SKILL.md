---
name: baixador
description: Executa o Baixador-YTDLP pelo terminal, sem abrir a janela - baixar vídeo, áudio, playlist ou trecho, analisar link, legendar com Whisper, fazer cortes verticais e editar com FFmpeg. Use em /baixador ou quando pedirem para baixar, legendar ou cortar um vídeo.
---

# Baixador-YTDLP pelo terminal

O app Baixador-YTDLP instalado no computador tem um modo de linha de comando (versão 1.15.0
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
reconhecido, o app é anterior à 1.15.0 e precisa ser atualizado.

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
| "corte seguindo a pessoa", "com efeitos" | `--enquadramento track`, `--efeitos --zoom-enfase` |
| "extrai o áudio", "comprime", "corta o trecho", "gif" | `cli ferramenta audio\|compress\|trim\|gif ARQ` |
| "deixa com menos de 25 MB" | `cli ferramenta target_size ARQ --tamanho-mb 25` |
| "converte pra vertical" | `cli ferramenta shorts ARQ` |
| "grava a legenda no vídeo" | `cli ferramenta burn VIDEO --legenda ARQ.srt` |
| "acelera 2x", "gira", "tira o som", "normaliza" | `speed --escolha 2`, `rotate --escolha cw`, `mute`, `normalize` |
| "o que eu baixei?" | `cli historico --limite 10` |
| "atualiza o yt-dlp", "tá dando erro em todo vídeo" | `cli preparar --atualizar` |
| "manda o diagnóstico" | `cli status --exportar ARQ.zip` |

Referência completa: `"$B" cli ajuda` e `"$B" cli <comando> --help`.

## 4. Cortes escolhidos pelo Claude

Se pedirem "os melhores momentos" sem tempos: rode `cli legendar VIDEO --formato json`
(com link, primeiro `cli baixar`), leia a transcrição, escolha de 1 a 5 trechos de 20 s a 90 s
que façam sentido sozinhos (gancho no início, ideia completa), proponha os tempos e títulos e,
com o ok da pessoa, rode `cli cortar` com um `--corte` por trecho. Cada corte tem no máximo
10 minutos.

## 5. Erros

- Mostre a mensagem de `erro` como veio; ela já é a explicação amigável do app.
- Cookies só quando o erro falar em login, conta, idade, bot-check ou conteúdo privado: então
  pergunte qual navegador está logado e repita com `--cookies-navegador chrome|edge|firefox|brave`.
  Nunca use cookies como primeira tentativa nem para outros erros.
- Erro geral de extração em vários links: `cli preparar --atualizar` e tente de novo.
- GPU é opcional: o app volta para a CPU sozinho; não peça para instalar nada da NVIDIA.
- Nunca mostre nem copie cookies, tokens ou links privados nas respostas.
