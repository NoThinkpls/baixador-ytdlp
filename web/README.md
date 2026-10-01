# Site (GitHub Pages)

Página do projeto publicada pelo workflow `.github/workflows/pages.yml`. É estática: HTML, CSS e JavaScript
puros, sem build, sem dependências e sem rastreadores.

| Arquivo | Função |
| --- | --- |
| `index.html` | Conteúdo em português (funciona sem JavaScript) |
| `app.js` | Tradução para inglês, tema, abas, detecção do sistema e versão/tamanhos da release mais recente |
| `theme-init.js` | Aplica o tema antes da pintura, para não piscar |
| `styles.css` | Tokens espelhados de `baixador_ytdlp/ui/theme.py` |
| `assets/` | Ícone e capturas (cópias de `assets/` e `docs/images/`) |

## Ver localmente

```bash
python -m http.server 8000 --directory web
```

Abra `http://localhost:8000`.

## Regras

- A paleta vem do tema do app. Se `theme.py` mudar, atualize `styles.css` (o teste `tests/test_site.py` avisa).
- Textos novos: escreva em português no HTML com `data-i18n="chave"` e adicione a chave em inglês em `app.js`.
- Os links de download devem ser os mesmos do README (o teste confere).
- A página tem uma política de segurança (CSP) estrita: sem scripts ou estilos inline. A única conexão externa
  é a API pública do GitHub, para mostrar versão e tamanhos; se ela falhar, a página continua inteira.
- Ao trocar uma captura em `docs/images/`, copie a nova para `web/assets/`.

## Publicação

Todo push na `main` que mude `web/` publica o site. Requer **Settings > Pages > Source: GitHub Actions**.

## Ferramentas no navegador (futuro)

Cortar/converter com `ffmpeg.wasm` e transcrever com Whisper em WebAssembly/WebGPU podem viver aqui em
subpastas (`web/ferramentas/...`), rodando no navegador do visitante. Baixar de sites não é possível no
navegador (CORS), então o download continua no app desktop.
