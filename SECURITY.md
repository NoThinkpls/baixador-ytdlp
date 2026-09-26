# Política de segurança

## Relate vulnerabilidades em privado

Não publique vulnerabilidades, tokens, cookies, logs pessoais ou links privados
em issues, discussões ou pull requests. Abra um relato privado em
[Security → Report a vulnerability](../../security/advisories/new) com:

- versão afetada e plataforma;
- passos mínimos para reproduzir;
- impacto observado e evidências relevantes;
- uma forma segura de contato, se houver necessidade de retorno.

Analizaremos o relato de forma privada e coordenaremos a correção antes de
qualquer divulgação. Problemas de uso geral, sem impacto de segurança, devem ser
abertos como [issue](../../issues/new/choose).

## Versões e distribuição oficial

A versão mais recente e a imediatamente anterior durante uma atualização são as
versões suportadas. Binários oficiais são publicados exclusivamente em
[GitHub Releases](../../releases) e incluem hashes SHA-256, inventários SBOM e
atestado de proveniência.

Verifique sempre a origem do download e os hashes publicados. O aplicativo não
solicita que você desative a validação TLS nem que compartilhe cookies ou senhas.

## Escopo prático

Relatos sobre atualização de binários, validação de downloads, tratamento de
cookies, credenciais, execução de subprocessos, dependências distribuídas e
arquivos de diagnóstico são especialmente bem-vindos.
