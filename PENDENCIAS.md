# Pendências para fechar a v1.12.0

Estado em 28/09/2026. A branch `main` tem commits locais à frente do GitHub.
As rodadas 1 e 2 e os itens M2, U5, F5, F4, F3, U7, U8 e M1 da rodada 3 foram
implementados localmente. A versão candidata é **1.12.0**; ainda faltam H2,
validação de build/GPU, testes manuais e publicação.

Contexto completo: `docs/PLANO-DE-CORRECOES.md` (auditoria, status por item e
tabela de uso de GPU) e `CLAUDE.md` (decisões e convenções do projeto).

## 1. Histórico recebido no ZIP

O ZIP contém a pasta `.git` com os commits anteriores. Antes da publicação:

```
git status
git log --oneline -3
git remote -v
```

Se o `origin` não estiver configurado:
`git remote add origin https://github.com/NoThinkpls/baixador-ytdlp.git`.
Enviar os commits ao GitHub somente depois da validação da seção 4.

## 2. Validação obrigatória na máquina com NVIDIA (antes de publicar)

1. `.\build.ps1 -ValidateGpu` — instala os locks e compila. A opção explícita
   carrega cuDNN e cria um handle na GPU. O build comum continua validando o
   pacote sem exigir GPU funcional durante o desenvolvimento.
2. Abrir o app, transcrever um vídeo curto e conferir no log
   "Modelo pronto: CUDA" (e o processo no `nvidia-smi`).
3. Teste rápido de fumaça: analisar e baixar um vídeo; baixar um trecho;
   legendar dois arquivos arrastados juntos; "Corte rápido" nas Ferramentas.

## 3. Rodada 3

Os itens implementados têm commits separados e testes de regressão; os hashes
estão em `docs/PLANO-DE-CORRECOES.md`. O CHANGELOG da candidata é `[1.12.0]`.
Testes: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests` e
`ruff check .`.

Ordem sugerida (do mais simples/seguro ao maior):

- [x] **M2** — `tools.ensure_ffmpeg`: tirar `ffplay.exe` do conjunto `wanted`
      (o app não usa; economiza ~100+ MB em disco). Ajustar a checagem de
      integridade que lista os binários.
- [x] **U5** — Configurações (`ui/settings_page.py`):
      - plural: "Até 1 downloads" → "Até 1 download";
      - ícones repetidos (sliders em Rede, Avançado, Reduzir tamanho e Caber em
        um limite) → ícones distintos de `ui/icons.py`;
      - "Verificar componentes" e "Verificar agora" → um botão só, com a hora da
        última checagem;
      - trocar o canal do yt-dlp não deve abrir o setup modal na hora (aplicar
        na próxima checagem ou pedir confirmação);
      - card Componentes deve mostrar o estado real do Whisper: "CUDA" só se
        `runtime.embedded_cuda_available()`; senão "CPU" + motivo.
- [x] **F5** — Perfil pronto "Baixar + legendar + incorporar" na seção Perfis
      da página Baixar (liga "Gerar legenda ao terminar" e "Incorporar legenda
      como faixa").
- [x] **F4** — Trecho por capítulo: o `-J` já traz `chapters`; na página Baixar,
      com "Baixar só um trecho" ligado, oferecer um seletor de capítulo que
      preenche início/fim. Guardar `chapters` em `MediaInfo` (`probe.py`).
- [x] **F3** — Pausar/retomar downloads (por item e "Pausar tudo" na Fila).
      Pausar = cancelar o processo mantendo os `.part` e devolver o item à fila
      como "Pausado"; retomar = `--continue` (já é usado). Persistir o estado
      em `queue_state.py`.
- [x] **U7** — Ferramentas (`ui/media_tools_page.py`): os 7 cards ocupam a
      primeira tela e a escolha do arquivo fica abaixo da dobra. Layout em
      duas colunas (lista de ferramentas à esquerda, formulário à direita) ou
      cards compactos; botão de ação desabilitado sem arquivo.
- [x] **U8** — i18n: só ~104 `tr()`. Passar por `ui/i18n.py` os textos de
      toasts, status da fila, `probe.friendly_error` e `transcription`
      (`friendly_transcription_error`). Maior item; pode ficar para depois da
      publicação.
- [x] **M1** — yt-dlp: hoje baixa o `yt-dlp.exe` onefile (descompacta a cada
      chamada). Avaliar a build onedir oficial para Windows: confirmar na
      release do yt-dlp o nome do zip e se ele está no `SHA2-256SUMS`, depois
      adaptar `tools.ensure_ytdlp` (extrair em pasta, apontar para o .exe de
      dentro, integridade por arquivo). Risco médio: testar bem.
- [ ] **H2** — Por último, em commit separado e só de quebras de linha:
      adicionar `.gitattributes` (`* text=auto eol=lf`, com exceções para
      `*.ps1 *.cmd *.bat *.iss text eol=crlf`) e rodar
      `git add --renormalize .`. Vários arquivos misturam CRLF e LF hoje.

## 4. Publicar a v1.12.0 (uma vez, depois de tudo acima)

1. Atualizar a data em `## [1.12.0] - não publicada` no `CHANGELOG.md`.
2. **Assinatura Ed25519 (opcional, recomendada):**
   - `python scripts\release_signing.py generate` → a chave privada vai para
     `%APPDATA%\BaixadorYtdlp-release\release-signing.key` (fazer backup fora do
     PC; nunca vai para o Git); a pública é impressa.
   - Colar a pública em `RELEASE_PUBLIC_KEYS` (`baixador_ytdlp/updater.py`),
     commit.
   - A partir daí o app recusa atualização sem `.sig` válido. Perder a chave
     privada obriga todos a atualizar manualmente.
3. `.\build.ps1` de novo (com a chave pública já no código).
4. `python scripts\prepare_release.py` → gera `SHA256SUMS.txt`, assina, confere
   e extrai as notas; mostra o comando `gh`. Depois
   `python scripts\prepare_release.py --publish` publica a release `v1.12.0`.
5. `git push` (se ainda houver commits locais).
6. Na versão seguinte, atualizar pelo app e conferir: só aparece a janela de
   progresso do instalador (`/SILENT`) e o app reabre sozinho. O `.iss` não foi
   compilado no ambiente onde as mudanças foram feitas.

## Observações

- O GitHub Actions está bloqueado na conta; o workflow `.github/workflows/build.yml`
  foi mantido coerente (DLLs do cuDNN 9), mas a release sai do build local.
- Instalador ficará maior por causa do cuDNN 9. Depois de validar a GPU, dá
  para testar excluir `cudnn_adv64_9.dll` (282 MB, não usado pelo Whisper).
- Os commits foram feitos com o autor "Nathan Ferraz", igual ao histórico.
