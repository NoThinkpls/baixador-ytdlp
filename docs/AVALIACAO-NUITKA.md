# Avaliação do Nuitka

O Nuitka é o empacotador padrão das releases Windows. A distribuição standalone
é normalizada para o layout usado pelo instalador e pela versão portátil. O
PyInstaller continua disponível como rota de contingência local.

## Gerar a candidata no Windows

```powershell
.\build.ps1                         # Nuitka (padrão)
.\build.ps1 -Installer              # Nuitka + instalador Inno Setup
.\build.ps1 -Packager PyInstaller   # contingência
```

O executável fica em `dist\baixador-ytdlp\baixador-ytdlp.exe`. A build usa o
plugin oficial do PySide6, inclui os ativos do aplicativo, as DLLs CUDA
carregadas dinamicamente e mantém a interface sem console. A primeira execução
pode baixar componentes de compilação do Nuitka; isso é confirmado pelo próprio
comando.

Antes de aceitar a pasta gerada, o build também executa `--self-test`: confere
os dados instalados do `faster-whisper` (incluindo os dois ONNX do VAD), os
imports e metadados do motor, a decodificação PyAV, a disponibilidade de CUDA e
uma carga do VAD por processo `spawn`. Isso bloqueia um pacote incompleto antes
de ele chegar ao instalador; não substitui a transcrição manual na máquina limpa.

## Comparação local — 25/09/2026

As duas distribuições foram geradas do mesmo commit, no Windows 11, com
Python 3.12: Nuitka 4.2.2 e PyInstaller 6.22.3. Cada executável foi aberto em
modo portátil, com uma pasta de dados isolada, e encerrado assim que a janela
principal `baixador-ytdlp 1.10.1` ficou disponível. Isso mede o início até a
primeira janela do aplicativo; a preparação de yt-dlp, FFmpeg e Deno ficou
fora da medição por depender de rede e não do empacotador.

| Métrica | Nuitka | PyInstaller | Resultado |
| --- | ---: | ---: | --- |
| Executável | 72,2 MiB | 10,0 MiB | O executável compilado do Nuitka é maior. |
| Distribuição completa | 1.942,3 MiB | 1.940,1 MiB | Nuitka: +2,2 MiB (0,11%). |
| DLLs CUDA obrigatórias | 6/6 | 6/6 | Ambos completos. |
| Primeira abertura | 1.990 ms | 1.569 ms | Nuitka: +421 ms. |
| Mediana de 5 aberturas alternadas | 1.510 ms | 1.514 ms | Empate prático. |
| Média de 5 aberturas alternadas | 1.604,8 ms | 1.508,6 ms | Nuitka: +96,2 ms. |

**Decisão de desempenho:** não há ganho mensurável de tamanho ou inicialização
que, sozinho, justifique trocar o empacotador. Esta comparação não decide a
questão de falsos positivos; ela é registrada na seção de segurança abaixo.

## Segurança — VirusTotal — 25/09/2026

Foram enviadas manualmente ao VirusTotal duas candidatas standalone sem
assinatura, geradas do mesmo commit. Os hashes e os relatórios permitem repetir
a consulta sem reenviar o arquivo. As contagens podem mudar quando os motores
atualizam suas assinaturas.

| Rodada | Empacotador | SHA-256 | Resultado no envio |
| --- | --- | --- | --- |
| 1 | Nuitka | `5f25df03119dbe549eff1550857221552358b3e054ebf351d2e9463cb8168829` | [1/67](https://www.virustotal.com/gui/file/5f25df03119dbe549eff1550857221552358b3e054ebf351d2e9463cb8168829/detection): Trapmine `Suspicious.low.ml.score`. Microsoft: não detectado. |
| 1 | PyInstaller | `0606eb7295728bd32f0af9faf0200f5ab9426feb3fd7f9223e484065d9383908` | [4/71](https://www.virustotal.com/gui/file/0606eb7295728bd32f0af9faf0200f5ab9426feb3fd7f9223e484065d9383908/detection): Bkav, Microsoft `Trojan:Win32/Wacatac.B!ml`, SecureAge e Skyhigh. |
| 2 | Nuitka | `05644041c2739a96d431f228dae55308507de3555f6567672e8335cadb826155` | [1/70](https://www.virustotal.com/gui/file/05644041c2739a96d431f228dae55308507de3555f6567672e8335cadb826155/detection): novamente apenas Trapmine `Suspicious.low.ml.score`. Microsoft: não detectado. |
| 2 | PyInstaller | `f8025429e9f8834eeaa2c7d6c636e877eabc2a36d9acca8a34a6d4b772abd83d` | [3/71](https://www.virustotal.com/gui/file/f8025429e9f8834eeaa2c7d6c636e877eabc2a36d9acca8a34a6d4b772abd83d/detection): Bkav, SecureAge e Skyhigh. Microsoft: não detectado nesta rodada. |

O teste local do Microsoft Defender não pôde ser realizado porque o mecanismo
está desativado neste computador; nenhuma configuração de segurança foi
alterada. O resultado do motor Microsoft no VirusTotal é uma evidência útil,
mas não substitui a execução em uma máquina limpa com Defender ativo.

## Instaladores Inno Setup — 25/09/2026

Os mesmos bundles da rodada 2 foram empacotados com Inno Setup 6.7.3 e a
configuração de instalação publicada: instalação por usuário, atalho, protocolo
`baixador://`, remoção de `_internal` de versões anteriores e compressão
`lzma2/max`. Os instaladores não foram executados, portanto não alteraram esta
máquina.

| Empacotador | Instalador gerado | SHA-256 | Assinatura |
| --- | ---: | --- | --- |
| PyInstaller | 739,2 MiB | `eeea8c284f00de2095495d4e5a71062b0745ab9d26b7dd1aef15e8fb2bce7797` | Não assinado |
| Nuitka | 732,1 MiB | `64812d90cc0772c0aca1babfd8c29c2f1c803dab2d06b5d645bff8ac88ad2bd1` | Não assinado |

O compilador concluiu ambos os instaladores com sucesso. O VirusTotal informa
na tela de envio um limite de 650 MiB; portanto, os dois excedem o limite (por
89,2 MiB e 82,1 MiB, respectivamente) e não foram enviados. Isso não é um
resultado de detecção: para comparar os instaladores será necessário reduzir o
artefato, usar um serviço com limite maior ou fazer a análise em um ambiente
corporativo que aceite esse tamanho.

As duas builds independentes preservaram o padrão: uma única heurística de
baixa relevância para Nuitka, contra três ou quatro motores para PyInstaller.
A assinatura `Wacatac.B!ml` do Microsoft oscilou entre as duas builds do
PyInstaller; por isso ela é uma evidência relevante, mas não deve ser tratada
como determinística sem a prova em Defender ativo.

**Decisão de segurança:** o Nuitka passou a ser o padrão de release Windows,
com o PyInstaller preservado como contingência. Ainda falta executar o teste em
máquina limpa sem Python e a análise dos instaladores em um canal que aceite o
tamanho do artefato.

## Checklist antes de decidir pela troca

- [ ] A pasta gerada abre em uma máquina limpa, sem Python instalado.
- [ ] A preparação instala/atualiza yt-dlp, FFmpeg e Deno.
- [ ] Download, transcrição CUDA e conversão por GPU concluem normalmente.
- [x] Os arquivos e bibliotecas CUDA obrigatórios estão presentes na pasta.
- [x] Medir tamanho total e tempo até a primeira janela contra a build do
  PyInstaller criada no mesmo commit. A tabela acima registra o resultado.
- [x] Registrar duas rodadas independentes das candidatas standalone sem
  assinatura no VirusTotal. Os hashes, links e detecções estão na tabela acima.
- [x] Gerar e validar estruturalmente os dois instaladores finais equivalentes.
- [ ] Verificar os instaladores em um canal de análise que aceite mais de
  739,2 MiB. O VirusTotal aceita até 650 MiB e o upload pode tornar binários
  públicos ao compartilhá-los com o serviço.
- [x] Adaptar o Inno Setup e o CI para a nova estrutura de saída do Nuitka.

Se algum item falhar, `build.ps1 -Packager PyInstaller` permite gerar uma
release de contingência enquanto a configuração do Nuitka é corrigida.
