# Pendências para fechar a v1.10.11

Estado em 28/09/2026. A branch `main` deste repositório tem **27 commits locais
à frente do GitHub** (a partir de `1704090`, a v1.10.10 publicada): rodadas 1 e
2 completas e parte da rodada 3. A versão já está em **1.10.11** (config,
installer.iss, version_info.txt) e o `CHANGELOG.md` já descreve tudo o que foi
feito. Nada foi publicado ainda: a ideia é sair uma única atualização grande.

Contexto completo: `docs/PLANO-DE-CORRECOES.md` (auditoria, status por item e
tabela de uso de GPU) e `CLAUDE.md` (decisões e convenções do projeto).

## 1. Enviar o que já existe (fazer primeiro)

O zip contém a pasta `.git` com todos os commits. Na máquina Windows:

```
cd C:\dev\baixador-ytdlp          # pasta extraída do zip
git status                        # deve estar limpo
git log --oneline -3              # topo: "docs: pendências…"
git remote -v                     # origin = github.com/NoThinkpls/baixador-ytdlp
git push origin main
```

Se o `origin` não estiver configurado:
`git remote add origin https://github.com/NoThinkpls/baixador-ytdlp.git`.
**Não** criar tag nem release agora (ver seção 4).

## 2. Validação obrigatória na máquina com NVIDIA (antes de publicar)

1. `.\build.ps1` — instala os locks (inclui cuDNN 9.10.2.21, ~1 GB) e compila.
   O autoteste agora carrega o cuDNN e cria um handle na GPU; se falhar, a build
   para. Motivo: o CTranslate2 4.8.2 exige cuDNN 9 e a v1.10.10 embutia cuDNN 8,
   então a transcrição caía para CPU.
2. Abrir o app, transcrever um vídeo curto e conferir no log
   "Modelo pronto: CUDA" (e o processo no `nvidia-smi`).
3. Teste rápido de fumaça: analisar e baixar um vídeo; baixar um trecho;
   legendar dois arquivos arrastados juntos; "Corte rápido" nas Ferramentas.

## 3. Itens da rodada 3 que faltam

Cada item: um commit, com teste que falha no código antigo, e marcado no
`docs/PLANO-DE-CORRECOES.md` no mesmo commit. Adicionar ao `CHANGELOG.md` na
seção `[1.10.11]`. Testes: `QT_QPA_PLATFORM=offscreen python -m unittest
discover -s tests` e `ruff check .` (hoje: 178 testes, todos passando).

Ordem sugerida (do mais simples/seguro ao maior):

- [ ] **M2** — `tools.ensure_ffmpeg`: tirar `ffplay.exe` do conjunto `wanted`
      (o app não usa; economiza ~100+ MB em disco). Ajustar a checagem de
      integridade que lista os binários.
- [ ] **U5** — Configurações (`ui/settings_page.py`):
      - plural: "Até 1 downloads" → "Até 1 download";
      - ícones repetidos (sliders em Rede, Avançado, Reduzir tamanho e Caber em
        um limite) → ícones distintos de `ui/icons.py`;
      - "Verificar componentes" e "Verificar agora" → um botão só, com a hora da
        última checagem;
      - trocar o canal do yt-dlp não deve abrir o setup modal na hora (aplicar
        na próxima checagem ou pedir confirmação);
      - card Componentes deve mostrar o estado real do Whisper: "CUDA" só se
        `runtime.embedded_cuda_available()`; senão "CPU" + motivo.
- [ ] **F5** — Perfil pronto "Baixar + legendar + incorporar" na seção Perfis
      da página Baixar (liga "Gerar legenda ao terminar" e "Incorporar legenda
      como faixa").
- [ ] **F4** — Trecho por capítulo: o `-J` já traz `chapters`; na página Baixar,
      com "Baixar só um trecho" ligado, oferecer um seletor de capítulo que
      preenche início/fim. Guardar `chapters` em `MediaInfo` (`probe.py`).
- [ ] **F3** — Pausar/retomar downloads (por item e "Pausar tudo" na Fila).
      Pausar = cancelar o processo mantendo os `.part` e devolver o item à fila
      como "Pausado"; retomar = `--continue` (já é usado). Persistir o estado
      em `queue_state.py`.
- [ ] **U7** — Ferramentas (`ui/media_tools_page.py`): os 7 cards ocupam a
      primeira tela e a escolha do arquivo fica abaixo da dobra. Layout em
      duas colunas (lista de ferramentas à esquerda, formulário à direita) ou
      cards compactos; botão de ação desabilitado sem arquivo.
- [ ] **U8** — i18n: só ~104 `tr()`. Passar por `ui/i18n.py` os textos de
      toasts, status da fila, `probe.friendly_error` e `transcription`
      (`friendly_transcription_error`). Maior item; pode ficar para depois da
      publicação.
- [ ] **M1** — yt-dlp: hoje baixa o `yt-dlp.exe` onefile (descompacta a cada
      chamada). Avaliar a build onedir oficial para Windows: confirmar na
      release do yt-dlp o nome do zip e se ele está no `SHA2-256SUMS`, depois
      adaptar `tools.ensure_ytdlp` (extrair em pasta, apontar para o .exe de
      dentro, integridade por arquivo). Risco médio: testar bem.
- [ ] **H2** — Por último, em commit separado e só de quebras de linha:
      adicionar `.gitattributes` (`* text=auto eol=lf`, com exceções para
      `*.ps1 *.cmd *.bat *.iss text eol=crlf`) e rodar
      `git add --renormalize .`. Vários arquivos misturam CRLF e LF hoje.

## 4. Publicar a v1.10.11 (uma vez, depois de tudo acima)

1. Atualizar a data em `## [1.10.11] - não publicada` no `CHANGELOG.md`.
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
   `python scripts\prepare_release.py --publish` publica a release `v1.10.11`.
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
