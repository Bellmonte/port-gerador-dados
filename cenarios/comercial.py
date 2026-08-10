"""Cenario comercial: star schema de vendas.

Dimensoes (produto, cliente, vendedor, regiao, calendario) e um fato de vendas
coerente, com sazonalidade e margem plausivel. Todo nome e sorteado (faker),
nenhum vinculo com dado real. E a base da espinha do portfolio e alimenta o
dashboard de Analise Comercial.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from motor.base import Contexto, calendario, fator_sazonal

NOME = "comercial"

# Catalogo de produto: linhas ficticias, faixa de preco e custo por categoria.
# (categoria, preco_min, preco_max, margem_bruta_alvo)
_CATEGORIAS = {
    "Linha Essencial": (40, 120, 0.32),
    "Linha Performance": (120, 320, 0.40),
    "Linha Premium": (320, 900, 0.48),
}
_REGIOES = ["Sul", "Sudeste", "Centro-Oeste", "Nordeste", "Norte"]
# Peso relativo de faturamento por regiao (Sudeste concentra, Norte menor).
_PESO_REGIAO = np.array([0.22, 0.34, 0.20, 0.16, 0.08])


def _dim_produto(ctx: Contexto, n: int = 24) -> pd.DataFrame:
    linhas = []
    cats = list(_CATEGORIAS)
    for i in range(n):
        cat = cats[i % len(cats)]
        pmin, pmax, margem = _CATEGORIAS[cat]
        preco = round(float(ctx.rng.uniform(pmin, pmax)), 2)
        custo = round(preco * (1 - margem) * float(ctx.rng.uniform(0.92, 1.08)), 2)
        nome = f"{ctx.faker.word().capitalize()} {ctx.faker.random_uppercase_letter()}{ctx.rng.integers(100, 999)}"
        linhas.append({
            "produto_id": i + 1,
            "produto": nome,
            "categoria": cat,
            "preco_tabela": preco,
            "custo_unitario": custo,
        })
    return pd.DataFrame(linhas)


def _dim_cliente(ctx: Contexto, n: int = 140) -> pd.DataFrame:
    portes = ctx.rng.choice(["Pequeno", "Medio", "Grande"], size=n, p=[0.55, 0.32, 0.13])
    regioes = ctx.rng.choice(_REGIOES, size=n, p=_PESO_REGIAO)
    return pd.DataFrame({
        "cliente_id": np.arange(1, n + 1),
        "cliente": [ctx.faker.company() for _ in range(n)],
        "porte": portes,
        "regiao": regioes,
        "cidade": [ctx.faker.city() for _ in range(n)],
    })


def _dim_vendedor(ctx: Contexto, n: int = 16) -> pd.DataFrame:
    return pd.DataFrame({
        "vendedor_id": np.arange(1, n + 1),
        "vendedor": [ctx.faker.name() for _ in range(n)],
        "regiao": ctx.rng.choice(_REGIOES, size=n, p=_PESO_REGIAO),
        # Multiplicador de performance individual (uns vendem mais que outros).
        "fator_performance": np.round(ctx.rng.normal(1.0, 0.18, size=n).clip(0.6, 1.5), 3),
    })


def _dim_regiao() -> pd.DataFrame:
    return pd.DataFrame({
        "regiao": _REGIOES,
        "peso_mercado": _PESO_REGIAO,
    })


def _fato_vendas(ctx, cal, prod, cli, vend, linhas_alvo=48000) -> pd.DataFrame:
    rng = ctx.rng
    # Distribui o total de linhas pelos dias segundo a sazonalidade.
    dias = cal["data"]
    peso_dia = fator_sazonal(dias, ctx)
    peso_dia = peso_dia / peso_dia.sum()
    por_dia = rng.multinomial(linhas_alvo, peso_dia)

    datas = np.repeat(dias.to_numpy(), por_dia)
    n = len(datas)

    # Cliente sorteado; vendedor tende a ser da regiao do cliente.
    cliente_ix = rng.integers(0, len(cli), size=n)
    cli_regiao = cli["regiao"].to_numpy()[cliente_ix]

    vend_por_regiao = {r: vend.index[vend["regiao"] == r].to_numpy() for r in _REGIOES}
    todos_vend = vend.index.to_numpy()
    vendedor_ix = np.empty(n, dtype=int)
    for r in _REGIOES:
        mask = cli_regiao == r
        pool = vend_por_regiao[r] if len(vend_por_regiao[r]) else todos_vend
        vendedor_ix[mask] = rng.choice(pool, size=int(mask.sum()))

    produto_ix = rng.integers(0, len(prod), size=n)

    preco_tab = prod["preco_tabela"].to_numpy()[produto_ix]
    custo_un = prod["custo_unitario"].to_numpy()[produto_ix]
    perf = vend["fator_performance"].to_numpy()[vendedor_ix]

    # Quantidade: base por porte do cliente, modulada pela performance.
    porte_base = {"Pequeno": 6, "Medio": 18, "Grande": 45}
    base = cli["porte"].map(porte_base).to_numpy()[cliente_ix]
    quantidade = np.maximum(1, rng.poisson(base * perf * 0.5)).astype(int)

    # Desconto por venda (0 a 18%), maior para cliente grande.
    desc_max = np.where(cli["porte"].to_numpy()[cliente_ix] == "Grande", 0.18, 0.10)
    desconto_pct = np.round(rng.uniform(0, 1, size=n) * desc_max, 3)

    receita_bruta = np.round(preco_tab * quantidade, 2)
    receita_liquida = np.round(receita_bruta * (1 - desconto_pct), 2)
    custo_total = np.round(custo_un * quantidade, 2)
    margem = np.round(receita_liquida - custo_total, 2)

    fato = pd.DataFrame({
        "venda_id": np.arange(1, n + 1),
        "data": pd.to_datetime(datas).strftime("%Y-%m-%d"),
        "produto_id": prod["produto_id"].to_numpy()[produto_ix],
        "cliente_id": cli["cliente_id"].to_numpy()[cliente_ix],
        "vendedor_id": vend["vendedor_id"].to_numpy()[vendedor_ix],
        "regiao": cli_regiao,
        "quantidade": quantidade,
        "desconto_pct": desconto_pct,
        "receita_bruta": receita_bruta,
        "receita_liquida": receita_liquida,
        "custo_total": custo_total,
        "margem": margem,
    })
    return fato.sort_values("data").reset_index(drop=True)


def gerar(ctx: Contexto) -> dict[str, pd.DataFrame]:
    # Ordem fixa de consumo do RNG mantem a semente reproduzivel.
    cal = calendario(ctx)
    prod = _dim_produto(ctx)
    cli = _dim_cliente(ctx)
    vend = _dim_vendedor(ctx)
    fato = _fato_vendas(ctx, cal, prod, cli, vend)
    return {
        "dim_calendario": cal.assign(data=cal["data"].dt.strftime("%Y-%m-%d")),
        "dim_produto": prod,
        "dim_cliente": cli,
        "dim_vendedor": vend,
        "dim_regiao": _dim_regiao(),
        "fato_vendas": fato,
    }
