"""Verificação de tipos com pyright (modo básico) em catraca.

O código já tinha dezenas de avisos herdados (Qt, ctypes, atributos opcionais). Em vez de
bloquear tudo de uma vez, o CI falha só para erros NOVOS em relação a ``scripts/pyright-baseline.json``;
o que for corrigido some da linha de base com ``--update``.

Uso: python scripts/pyright_check.py [--update]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "pyright-baseline.json"


def fingerprint(item: dict) -> str:
    """Arquivo, regra e mensagem (sem número de linha: editar acima não vira "erro novo")."""
    path = Path(item["file"]).resolve()
    try:
        name = path.relative_to(ROOT).as_posix()
    except ValueError:
        name = path.as_posix()
    return f'{name}|{item.get("rule", "")}|{item["message"].splitlines()[0]}'


def run_pyright() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "baixador_ytdlp", "main.py"],
        cwd=ROOT, capture_output=True, text=True, check=False)
    try:
        report = json.loads(result.stdout)
    except ValueError:
        print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
        raise SystemExit("O pyright não devolveu um relatório legível.") from None
    return sorted(fingerprint(d) for d in report["generalDiagnostics"] if d["severity"] == "error")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="reescreve a linha de base")
    args = parser.parse_args()
    current = run_pyright()
    if args.update:
        BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Linha de base gravada: {len(current)} avisos herdados.")
        return 0
    known = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else []
    remaining = list(known)
    new = []
    for item in current:
        if item in remaining:
            remaining.remove(item)
        else:
            new.append(item)
    fixed = len(remaining)
    print(f"pyright: {len(current)} avisos ({len(known)} na linha de base; {fixed} já corrigidos).")
    if new:
        print(f"\n{len(new)} erro(s) NOVO(S):")
        for item in new:
            print("  -", item)
        return 1
    if fixed:
        print("Dica: a linha de base reúne o que o ambiente local e o do CI enxergam (o CI vê mais "
              "erros de tipos do Qt). Só encolha com --update usando a lista do próprio CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
