# Plano da IA para os Cortes

Na página **Cortes**, o campo **Plano da IA** recebe uma linha de texto que diz ao app
quais cortes fazer, com que título (animado ou fixo no topo) e onde colocar sons e zoom. A ideia é dividir o
trabalho: uma IA de texto (ChatGPT, Claude, Gemini ou outra) lê a transcrição inteira e
entende o contexto; o Baixador só executa, com precisão de palavra.

Você não precisa de nenhum prompt específico. Basta pedir à sua IA que, no fim da
resposta, entregue a linha no formato abaixo.

## Como usar

1. Transcreva o vídeo inteiro na aba **Legendar** e gere o `.srt`.
2. Envie o `.srt` para a sua IA junto com o pedido do plano (veja o texto pronto mais
   abaixo).
3. Copie a linha que começa com `{"bx":1` (ou a resposta inteira).
4. Em **Cortes**, escolha o vídeo, cole a linha no campo **Plano da IA** e clique em
   **Aplicar plano**. Com o campo vazio, o botão lê a área de transferência: dá para
   copiar a resposta inteira da IA e só clicar.

A lista de cortes é trocada pela do plano. Cada corte com efeitos mostra um `✦` com o
número de pontos; passe o mouse para ver quais são. **Efeitos sonoros** e **Zoom na
ênfase** são ligados sozinhos quando o plano traz sons ou zoom. Se o plano disser o tipo de
título (`t`) e a linha de cima (`l`), a página também passa a usá-los. Você ainda pode mudar
início, fim e título à mão antes de criar.

## O formato

Uma linha só de JSON, compacta de propósito:

```
{"bx":1,"t":"f","l":"PR. JOÃO · CULTO DE DOMINGO","c":[["12:03","12:58","\"DEUS NÃO TE ESQUECEU\"",[["12:10","graça","i",1],["12:31","","w",0]]]]}
```

- `bx`: sempre `1` (é como o app reconhece o plano no meio de outro texto).
- `t` (opcional): o tipo de título de todos os cortes. `"f"` = **título fixo no topo**
  (faixa escura com o título num cartão do começo ao fim, vídeo embaixo); `"a"` =
  **título animado** (entra com um pulo e some depois de alguns segundos). Sem `t`, vale o
  que está escolhido na página.
- `l` (opcional): a linha pequena acima do título fixo, a mesma em todos os cortes (nome
  do pregador, do podcast, da série ou do episódio), até 80 caracteres. Sem `l`, fica a
  da página.
- `c`: a lista de cortes. Cada corte é `[início, fim, título, efeitos]`.
  - **início** e **fim**: tempos do vídeo original, iguais aos do `.srt`, em `mm:ss`,
    `hh:mm:ss`, com décimos (`12:03.5` ou `12:03,5`) ou em segundos (`723.5`).
    Cada corte tem de 1 segundo a 10 minutos; no máximo 20 cortes.
  - **título**: o título do corte (pode ser `""`). Com título animado, curto (2 a 4
    palavras, até 20 caracteres) para caber numa linha. Com título fixo, cabe mais: até 3
    linhas no cartão (3 a 8 palavras, até uns 45 caracteres); a fonte diminui sozinha
    quando é comprido, e uma frase marcante entre aspas (`\"…\"` dentro do JSON) fica
    bem nesse formato.
  - **efeitos**: lista de pontos (pode ser `[]`). Cada ponto é
    `[tempo, palavra, som, zoom]`:
    - **tempo**: quando acontece, no tempo do `.srt`;
    - **palavra**: a palavra (ou expressão curta) dita naquele momento, como aparece na
      transcrição. É opcional, mas é o que dá precisão: o `.srt` só tem o tempo da
      frase, e o app procura essa palavra até 6 segundos em volta do tempo e usa o
      instante exato em que ela é dita;
    - **som**: uma letra, ou `""` para só zoom:

      | Letra | Som | Quando usar |
      | --- | --- | --- |
      | `w` | whoosh | troca de assunto ou de ideia |
      | `p` | pop | destacar uma palavra ou um número |
      | `i` | impacto | frase forte, clímax, revelação |
      | `d` | ding | ideia-chave, conclusão, "aha" |
      | `s` | subida | tensão crescendo; o som termina no ponto marcado |

      Os nomes inteiros (`whoosh`, `pop`, `impacto`, `ding`, `subida`) também valem.
    - **zoom**: `1` para uma aproximação rápida da imagem naquele ponto, `0` sem zoom.

O que o app faz com cada ponto:

- converte o tempo para o vídeo final, já sem as pausas removidas;
- o **whoosh** perto de uma emenda (até 1,5 s) vai para a emenda, e o pico do som cai
  em cima dela; sem emenda perto, o whoosh é descartado (não haveria transição na
  imagem para ele acompanhar);
- a **subida** termina exatamente no ponto; os outros sons começam nele;
- todo som que não é whoosh ganha o zoom rápido naquele ponto, para algo acontecer na
  tela junto com ele; com **Zoom na ênfase** desligado, só o whoosh continua;
- dois sons ficam a pelo menos 3 s um do outro (a subida que termina num impacto conta
  como um efeito só); o que vier perto demais é descartado;
- o volume de cada som é medido e fica alguns dB abaixo da voz do corte;
- pontos fora do próprio corte, tempos ilegíveis e sons desconhecidos são ignorados
  (um som desconhecido com `zoom` 1 vira só zoom); o resto do plano continua valendo.

Sem plano, o app usa uma regra simples pelo áudio (whoosh em pausas longas cortadas e
pop em palavras ditas bem mais alto).

## Texto pronto para a sua IA

Cole no fim das instruções da sua IA (ou do seu pedido), sem mudar o resto:

```
No final da resposta, depois de tudo, entregue uma única linha de JSON compacto, sem
quebras de linha e sem comentários, neste formato:
{"bx":1,"t":"f","l":"LINHA DE CIMA","c":[["INÍCIO","FIM","TÍTULO",[["TEMPO","PALAVRA","SOM",ZOOM]]]]}
- "t" é o tipo de título: "f" (fixo no topo, num cartão, o corte inteiro) ou "a"
  (animado, aparece no começo e some). Use "f", a não ser que eu peça título animado.
- "l" é uma linha curta acima do título fixo, igual em todos os cortes (nome de quem fala
  e do programa, série ou episódio, até 40 caracteres). Se não souber, não ponha "l".
- Um item em "c" para cada corte sugerido (máximo 20), com INÍCIO e FIM tirados do SRT
  (mm:ss ou hh:mm:ss) e o título do corte: com "f", de 3 a 8 palavras e até 45
  caracteres (uma frase forte de quem fala pode ir entre aspas, escritas como \");
  com "a", de 2 a 4 palavras e até 20 caracteres.
- Em cada corte, de 1 a 3 efeitos, só onde reforçam a fala: TEMPO do SRT; PALAVRA
  exatamente como foi dita naquele momento; SOM = w (troca de assunto), p (destaque de
  palavra), i (frase forte ou clímax), d (ideia-chave), s (tensão que termina no ponto)
  ou "" (sem som); ZOOM = 1 para aproximar a imagem nesse ponto, 0 para não.
- Deixe pelo menos 4 segundos entre dois sons e não ponha efeito nos 2 primeiros
  segundos do corte. Use w só numa pausa ou troca de assunto. Prefira poucos efeitos
  bem colocados a muitos.
```

## Sons próprios

Os cinco sons padrão são gerados pelo próprio app. Para usar outros (de uma biblioteca
que você tem direito de usar), crie uma pasta com arquivos chamados `whoosh`, `pop`,
`impacto`, `ding` e `subida` (WAV, MP3, OGG, M4A, FLAC, AAC ou Opus) e escolha a pasta
em **Cortes → Ritmo e efeitos → Seus sons (opcional)**, que aparece com **Efeitos sonoros** ligado. O que faltar na pasta continua com o som padrão.
