"""Cenario comercial: star schema de vendas.

Dimensoes (produto, cliente, vendedor, regiao, calendario) e um fato de vendas
coerente, com sazonalidade e margem plausivel. Todo nome e sorteado (faker),
nenhum vinculo com dado real. Alimenta o dashboard de Analise Comercial do
portfolio.

Parametros lidos de `ctx.parametros` (todos opcionais, padrao entre parenteses):
linhas (48000), clientes (140), produtos (24), vendedores (16) e
colunas_origem (False). Com os padroes, a saida e a mesma de sempre. Com
colunas_origem ligada, o fato e gerado a partir de pedidos com varios itens e
ganha numero_pedido e data_hora_emissao; as dimensoes nao mudam.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from motor.base import Contexto, calendario, fator_sazonal, nomes_unicos

NOME = "comercial"

# Padroes do volume. O feed diario roda com eles; volume maior e passado pela
# linha de comando e gerado localmente.
PADRAO = {"linhas": 48000, "clientes": 140, "produtos": 24, "vendedores": 16}

# Colunas somadas no _manifesto.json, para conferir leitura completa na ponta.
CONTROLES = {
    "fato_vendas": ["quantidade", "receita_bruta", "receita_liquida", "custo_total", "margem"],
}

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
        # faker.company() repete nome; o sufixo deterministico evita juntar
        # clientes diferentes em quem agrupa por nome, sem novo sorteio.
        "cliente": nomes_unicos([ctx.faker.company() for _ in range(n)]),
        "porte": portes,
        "regiao": regioes,
        "cidade": [ctx.faker.city() for _ in range(n)],
    })


def _dim_vendedor(ctx: Contexto, n: int = 16) -> pd.DataFrame:
    return pd.DataFrame({
        "vendedor_id": np.arange(1, n + 1),
        # Mesmo cuidado do cliente: nome repetido ganha sufixo, sem novo sorteio.
        "vendedor": nomes_unicos([ctx.faker.name() for _ in range(n)]),
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


# Itens por pedido quando o fato e gerado a partir de pedidos: 1 + binomial
# negativa com n=1,5 e p=1/3, media 4 e desvio 3. Muito pedido pequeno de
# reposicao e uma cauda de pedido grande, como numa distribuidora. O teto e 40,
# ou o numero de produtos se ele for menor, porque o pedido nao repete produto.
_ITENS_DISPERSAO = 1.5
_ITENS_P = 1 / 3
_ITENS_TETO = 40


def _fato_por_pedido(ctx, cal, prod, cli, vend, linhas_alvo) -> pd.DataFrame:
    """Fato gerado a partir de pedidos, usado so com --colunas-origem.

    Cada pedido sorteia data (pela sazonalidade), cliente e vendedor da regiao
    do cliente, horario de emissao e numero de itens. As linhas herdam isso do
    pedido; produto, quantidade, desconto e valores seguem as MESMAS regras de
    `_fato_vendas`, que fica intocada para o caminho padrao nao mudar. Quem
    mudar uma regra de valor la precisa mudar aqui tambem."""
    rng = ctx.rng
    teto = min(_ITENS_TETO, len(prod))

    # 1. Itens por pedido, ate fechar exatamente `linhas_alvo` (corta o ultimo).
    lotes, total = [], 0
    while total < linhas_alvo:
        lote = 1 + rng.negative_binomial(_ITENS_DISPERSAO, _ITENS_P,
                                         size=max(1024, (linhas_alvo - total) // 3))
        lote = np.minimum(lote, teto)
        lotes.append(lote)
        total += int(lote.sum())
    itens = np.concatenate(lotes)
    acumulado = np.cumsum(itens)
    ultimo = int(np.searchsorted(acumulado, linhas_alvo))
    itens = itens[: ultimo + 1].copy()
    itens[-1] -= int(acumulado[ultimo]) - linhas_alvo
    n_ped = len(itens)

    # 2. Cabecalho do pedido: data pela sazonalidade, cliente, vendedor da regiao.
    dias = cal["data"]
    peso_dia = fator_sazonal(dias, ctx)
    peso_dia = peso_dia / peso_dia.sum()
    data_ped = np.repeat(dias.to_numpy(), rng.multinomial(n_ped, peso_dia))
    cliente_ped = rng.integers(0, len(cli), size=n_ped)
    regiao_ped = cli["regiao"].to_numpy()[cliente_ped]
    vend_por_regiao = {r: vend.index[vend["regiao"] == r].to_numpy() for r in _REGIOES}
    todos_vend = vend.index.to_numpy()
    vendedor_ped = np.empty(n_ped, dtype=int)
    for r in _REGIOES:
        mask = regiao_ped == r
        pool = vend_por_regiao[r] if len(vend_por_regiao[r]) else todos_vend
        vendedor_ped[mask] = rng.choice(pool, size=int(mask.sum()))
    # Horario de um gerador separado, entre 07:00:00 e 19:59:59.
    hora_ped = ctx.rng_extra(1).integers(7 * 3600, 20 * 3600, size=n_ped)
    # Numeracao do pedido segue a ordem de emissao: data, depois horario.
    ordem = np.lexsort((hora_ped, data_ped))
    data_ped, cliente_ped, vendedor_ped, hora_ped, itens = (
        data_ped[ordem], cliente_ped[ordem], vendedor_ped[ordem], hora_ped[ordem], itens[ordem])

    # 3. Linhas herdam o pedido.
    ped = np.repeat(np.arange(n_ped), itens)
    n = len(ped)
    cliente_ix = cliente_ped[ped]
    vendedor_ix = vendedor_ped[ped]
    datas = data_ped[ped]

    # Produto sem repeticao dentro do pedido: resorteia so as linhas repetidas.
    produto_ix = rng.integers(0, len(prod), size=n)
    while True:
        repetido = pd.DataFrame({"p": ped, "x": produto_ix}).duplicated().to_numpy()
        if not repetido.any():
            break
        produto_ix[repetido] = rng.integers(0, len(prod), size=int(repetido.sum()))

    # 4. Valores, com as regras de `_fato_vendas`.
    preco_tab = prod["preco_tabela"].to_numpy()[produto_ix]
    custo_un = prod["custo_unitario"].to_numpy()[produto_ix]
    perf = vend["fator_performance"].to_numpy()[vendedor_ix]
    porte_base = {"Pequeno": 6, "Medio": 18, "Grande": 45}
    base = cli["porte"].map(porte_base).to_numpy()[cliente_ix]
    quantidade = np.maximum(1, rng.poisson(base * perf * 0.5)).astype(int)
    desc_max = np.where(cli["porte"].to_numpy()[cliente_ix] == "Grande", 0.18, 0.10)
    desconto_pct = np.round(rng.uniform(0, 1, size=n) * desc_max, 3)
    receita_bruta = np.round(preco_tab * quantidade, 2)
    receita_liquida = np.round(receita_bruta * (1 - desconto_pct), 2)
    custo_total = np.round(custo_un * quantidade, 2)
    margem = np.round(receita_liquida - custo_total, 2)

    carimbo = pd.to_datetime(datas) + pd.to_timedelta(hora_ped[ped], unit="s")
    return pd.DataFrame({
        "venda_id": np.arange(1, n + 1),
        "data": pd.to_datetime(datas).strftime("%Y-%m-%d"),
        "produto_id": prod["produto_id"].to_numpy()[produto_ix],
        "cliente_id": cli["cliente_id"].to_numpy()[cliente_ix],
        "vendedor_id": vend["vendedor_id"].to_numpy()[vendedor_ix],
        "regiao": cli["regiao"].to_numpy()[cliente_ix],
        "quantidade": quantidade,
        "desconto_pct": desconto_pct,
        "receita_bruta": receita_bruta,
        "receita_liquida": receita_liquida,
        "custo_total": custo_total,
        "margem": margem,
        "numero_pedido": [f"PV-{p + 1:09d}" for p in ped],
        "data_hora_emissao": carimbo.strftime("%Y-%m-%d %H:%M:%S"),
    })


def gerar(ctx: Contexto) -> dict[str, pd.DataFrame]:
    par = {**PADRAO, **{k: v for k, v in ctx.parametros.items() if v is not None}}
    # Ordem fixa de consumo do RNG mantem a semente reproduzivel. As dimensoes
    # saem iguais com ou sem --colunas-origem; so o fato muda de caminho.
    cal = calendario(ctx)
    prod = _dim_produto(ctx, par["produtos"])
    cli = _dim_cliente(ctx, par["clientes"])
    vend = _dim_vendedor(ctx, par["vendedores"])
    if par.get("colunas_origem"):
        fato = _fato_por_pedido(ctx, cal, prod, cli, vend, linhas_alvo=par["linhas"])
    else:
        fato = _fato_vendas(ctx, cal, prod, cli, vend, linhas_alvo=par["linhas"])
    return {
        "dim_calendario": cal.assign(data=cal["data"].dt.strftime("%Y-%m-%d")),
        "dim_produto": prod,
        "dim_cliente": cli,
        "dim_vendedor": vend,
        "dim_regiao": _dim_regiao(),
        "fato_vendas": fato,
    }
