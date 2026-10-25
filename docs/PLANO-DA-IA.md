# Plano da IA para os Cortes

Na página **Cortes**, o campo **Plano da IA** recebe uma linha de texto que diz ao app
quais cortes fazer, com que título e onde colocar sons e zoom. A ideia é dividir o
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
ênfase** são ligados sozinhos quando o plano traz sons ou zoom. Você ainda pode mudar
início, fim e título à mão antes de criar.

## O formato

Uma linha só de JSON, compacta de propósito:

```
{"bx":1,"c":[["12:03","12:58","TÍTULO DO CORTE",[["12:10","graça","i",1],["12:31","","w",0]]]]}
```

- `bx`: sempre `1` (é como o app reconhece o plano no meio de outro texto).
- `c`: a lista de cortes. Cada corte é `[início, fim, título, efeitos]`.
  - **início** e **fim**: tempos do vídeo original, iguais aos do `.srt`, em `mm:ss`,
    `hh:mm:ss`, com décimos (`12:03.5` ou `12:03,5`) ou em segundos (`723.5`).
    Cada corte tem de 1 segundo a 10 minutos; no máximo 20 cortes.
  - **título**: o texto animado no começo do corte (pode ser `""`).
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
  em cima dela;
- a **subida** termina exatamente no ponto; os outros sons começam nele;
- pontos fora do próprio corte, tempos ilegíveis e sons desconhecidos são ignorados
  (um som desconhecido com `zoom` 1 vira só zoom); o resto do plano continua valendo.

Sem plano, o app usa uma regra simples pelo áudio (whoosh em pausas longas cortadas e
pop em palavras ditas bem mais alto).

## Texto pronto para a sua IA

Cole no fim das instruções da sua IA (ou do seu pedido), sem mudar o resto:

```
No final da resposta, depois de tudo, entregue uma única linha de JSON compacto, sem
quebras de linha e sem comentários, neste formato:
{"bx":1,"c":[["INÍCIO","FIM","TÍTULO",[["TEMPO","PALAVRA","SOM",ZOOM]]]]}
- Um item em "c" para cada corte sugerido (máximo 20), com INÍCIO e FIM tirados do SRT
  (mm:ss ou hh:mm:ss) e o título curto do corte.
- Em cada corte, de 2 a 6 efeitos, só onde reforçam a fala: TEMPO do SRT; PALAVRA
  exatamente como foi dita naquele momento; SOM = w (troca de assunto), p (destaque de
  palavra), i (frase forte ou clímax), d (ideia-chave), s (tensão que termina no ponto)
  ou "" (sem som); ZOOM = 1 para aproximar a imagem nesse ponto, 0 para não.
- Não repita o mesmo som a menos de 4 segundos e não ponha efeito nos 2 primeiros
  segundos do corte.
```

## Sons próprios

Os cinco sons padrão são gerados pelo próprio app. Para usar outros (de uma biblioteca
que você tem direito de usar), crie uma pasta com arquivos chamados `whoosh`, `pop`,
`impacto`, `ding` e `subida` (WAV, MP3, OGG, M4A, FLAC, AAC ou Opus) e escolha a pasta
em **Cortes → Acabamento → Seus sons**. O que faltar na pasta continua com o som padrão.
