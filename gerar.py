"""Gerador de dado sintetico do portfolio.

Uso:
    python gerar.py comercial
    python gerar.py comercial --seed 7 --meses 24 --saida dados
    python gerar.py comercial --hoje 2026-08-31 --linhas 1000000 --clientes 20000 \
        --produtos 1500 --vendedores 150 --colunas-origem --saida ../local/base-grande

Cada cenario e um modulo em `cenarios/`. A saida sao CSVs limpos, um arquivo
de aviso de dado ficticio e um `_manifesto.json` com parametros, linhas e somas
de controle. Semente fixa (forma reproduzivel), janela de datas terminando em
hoje ou na data passada em --hoje.
"""

from __future__ import annotations

import argparse
import importlib
import time
from datetime import date
from pathlib import Path

from motor.base import criar_contexto, escrever_aviso, escrever_csv, escrever_manifesto

RAIZ = Path(__file__).resolve().parent
# Saida padrao: pasta dados/ na raiz do repo. O feed comita daqui e o Power BI le
# pela URL raw. Quem clona e roda sem argumento ja escreve no lugar certo.
SAIDA_PADRAO = RAIZ / "dados"


def _positivo(texto: str) -> int:
    valor = int(texto)
    if valor < 1:
        raise argparse.ArgumentTypeError("precisa ser inteiro maior que zero")
    return valor


def _data(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("use o formato AAAA-MM-DD") from erro


def main() -> None:
    p = argparse.ArgumentParser(description="Gerador de dado sintetico do portfolio.")
    p.add_argument("cenario", help="nome do cenario (ex.: comercial)")
    p.add_argument("--seed", type=int, default=42, help="semente (default 42)")
    p.add_argument("--meses", type=_positivo, default=36, help="tamanho da janela em meses")
    p.add_argument("--hoje", type=_data, default=None,
                   help="data de corte da janela, AAAA-MM-DD (default: o dia da execucao)")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="pasta de saida")
    # Volume e colunas opcionais. Sem eles, cada cenario usa o proprio padrao.
    p.add_argument("--linhas", type=_positivo, help="linhas do fato (comercial: 48000)")
    p.add_argument("--clientes", type=_positivo, help="clientes (comercial: 140)")
    p.add_argument("--produtos", type=_positivo, help="produtos (comercial: 24)")
    p.add_argument("--vendedores", type=_positivo, help="vendedores (comercial: 16)")
    p.add_argument("--colunas-origem", action="store_true",
                   help="gera o fato por pedido, com numero_pedido e data_hora_emissao")
    args = p.parse_args()

    try:
        modulo = importlib.import_module(f"cenarios.{args.cenario}")
    except ModuleNotFoundError:
        disponiveis = [f.stem for f in (RAIZ / "cenarios").glob("*.py") if f.stem != "__init__"]
        p.error(f"cenario '{args.cenario}' nao existe. Disponiveis: {', '.join(disponiveis)}")

    parametros = {
        "linhas": args.linhas,
        "clientes": args.clientes,
        "produtos": args.produtos,
        "vendedores": args.vendedores,
        "colunas_origem": args.colunas_origem,
    }
    inicio_relogio = time.perf_counter()
    ctx = criar_contexto(seed=args.seed, meses=args.meses, hoje=args.hoje, parametros=parametros)
    tabelas = modulo.gerar(ctx)

    destino = args.saida / args.cenario
    print(f"Cenario: {modulo.NOME} | semente {args.seed} | janela {ctx.inicio} -> {ctx.hoje}")
    for nome, df in tabelas.items():
        caminho = escrever_csv(df, destino, nome)
        print(f"  {nome:<16} {len(df):>9} linhas  ->  {caminho}")
    escrever_aviso(destino)

    efetivos = {**getattr(modulo, "PADRAO", {}), **{k: v for k, v in parametros.items() if v is not None}}
    registro = {
        "cenario": modulo.NOME,
        "seed": args.seed,
        "meses": args.meses,
        "inicio": ctx.inicio.isoformat(),
        "hoje": ctx.hoje.isoformat(),
        **efetivos,
    }
    manifesto = escrever_manifesto(destino, registro, tabelas, getattr(modulo, "CONTROLES", {}))
    print(f"Aviso de dado ficticio e manifesto gravados em {destino}")
    print(f"Manifesto: {manifesto.name} | tempo total {time.perf_counter() - inicio_relogio:.1f} s")


if __name__ == "__main__":
    main()
