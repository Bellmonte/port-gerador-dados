"""Gerador de dado sintetico do portfolio B&B Vector Value Method.

Uso:
    python gerar.py comercial
    python gerar.py comercial --seed 7 --meses 24 --saida ../../local/dados-sinteticos

Cada cenario e um modulo em `cenarios/`. A saida sao CSVs limpos + um arquivo
de aviso de dado ficticio. Semente fixa (forma reproduzivel), janela de datas
terminando em hoje (dado com cara de atual sem infra externa).
"""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

from motor.base import criar_contexto, escrever_aviso, escrever_csv

RAIZ = Path(__file__).resolve().parent
# Saida padrao: pasta dados/ na raiz do repo. O feed comita daqui e o Power BI le
# pela URL raw. Quem clona e roda sem argumento ja escreve no lugar certo.
SAIDA_PADRAO = RAIZ / "dados"


def main() -> None:
    p = argparse.ArgumentParser(description="Gerador de dado sintetico do portfolio.")
    p.add_argument("cenario", help="nome do cenario (ex.: comercial)")
    p.add_argument("--seed", type=int, default=42, help="semente (default 42)")
    p.add_argument("--meses", type=int, default=36, help="tamanho da janela em meses")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="pasta de saida")
    args = p.parse_args()

    try:
        modulo = importlib.import_module(f"cenarios.{args.cenario}")
    except ModuleNotFoundError:
        disponiveis = [f.stem for f in (RAIZ / "cenarios").glob("*.py") if f.stem != "__init__"]
        p.error(f"cenario '{args.cenario}' nao existe. Disponiveis: {', '.join(disponiveis)}")

    ctx = criar_contexto(seed=args.seed, meses=args.meses)
    tabelas = modulo.gerar(ctx)

    destino = args.saida / args.cenario
    print(f"Cenario: {modulo.NOME} | semente {args.seed} | janela {ctx.inicio} -> {ctx.hoje}")
    for nome, df in tabelas.items():
        caminho = escrever_csv(df, destino, nome)
        print(f"  {nome:<16} {len(df):>7} linhas  ->  {caminho}")
    escrever_aviso(destino)
    print(f"Aviso de dado ficticio gravado em {destino / '_LEIA-dados-sinteticos.txt'}")


if __name__ == "__main__":
    main()
