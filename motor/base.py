"""Helpers compartilhados do motor.

Nada aqui conhece um cenario especifico. Sao ferramentas: gerar o RNG e o
faker semeados, montar o calendario relativo a hoje, aplicar sazonalidade e
escrever CSV com um cabecalho de aviso de dado ficticio.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker

# Aviso obrigatorio em toda peca publica (ver POLITICA_DESCARACTERIZACAO.md).
# Vai num arquivo a parte na pasta de saida e no README do gerador. Texto que
# chega a quem le o dado sai acentuado; o codigo continua em ASCII.
AVISO = (
    "Dado 100% sintético, gerado para demonstração de portfólio. "
    "Nomes, números e entidades são fictícios, criados por sorteio, sem "
    "relação com organizações, pessoas ou dados reais."
)


@dataclass
class Contexto:
    """Estado semeado que todo cenario recebe. Semente fixa deixa a FORMA do
    dado reproduzivel; a janela de datas termina sempre em `hoje`, entao cada
    execucao entrega dado com cara de atual sem depender de infra externa."""

    rng: np.random.Generator
    faker: Faker
    hoje: date
    meses: int
    seed: int = 42
    # Parametros especificos do cenario (volume, colunas opcionais). Cada
    # cenario le o que conhece e usa o proprio padrao para o que faltar.
    parametros: dict = field(default_factory=dict)

    def rng_extra(self, fluxo: int) -> np.random.Generator:
        """Gerador aleatorio independente do principal. Coluna opcional sorteada
        daqui nao consome o `rng` principal, entao ligar ou desligar a opcao nao
        altera nenhuma coluna existente."""
        return np.random.default_rng([self.seed, fluxo])

    @property
    def inicio(self) -> date:
        # Primeiro dia do mes, `meses` atras, para a janela fechar meses cheios.
        return (self.hoje.replace(day=1) - relativedelta(months=self.meses - 1))


def criar_contexto(
    seed: int = 42,
    meses: int = 36,
    hoje: date | None = None,
    parametros: dict | None = None,
) -> Contexto:
    rng = np.random.default_rng(seed)
    faker = Faker("pt_BR")
    faker.seed_instance(seed)
    return Contexto(
        rng=rng, faker=faker, hoje=hoje or date.today(), meses=meses,
        seed=seed, parametros=dict(parametros or {}),
    )


def nomes_unicos(nomes: list[str]) -> list[str]:
    """Garante nome unico sem novo sorteio: a primeira ocorrencia fica como
    veio e as repetidas ganham sufixo numerico (`Nome 2`, `Nome 3`). Nao consome
    RNG nem faker, entao nada depois dela muda de valor."""
    usados: set[str] = set()
    saida = []
    for nome in nomes:
        candidato, k = nome, 2
        while candidato in usados:
            candidato = f"{nome} {k}"
            k += 1
        usados.add(candidato)
        saida.append(candidato)
    return saida


def calendario(ctx: Contexto) -> pd.DataFrame:
    """Tabela de datas dia a dia, do inicio da janela ate hoje."""
    dias = pd.date_range(start=ctx.inicio, end=ctx.hoje, freq="D")
    nomes_mes = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    df = pd.DataFrame({"data": dias})
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    df["nome_mes"] = df["mes"].map(lambda m: nomes_mes[m - 1])
    df["ano_mes"] = df["data"].dt.strftime("%Y-%m")
    df["trimestre"] = df["data"].dt.quarter
    df["dia_semana"] = df["data"].dt.weekday.map(lambda d: dias_semana[d])
    df["fim_de_semana"] = df["data"].dt.weekday >= 5
    return df


def fator_sazonal(datas: pd.Series, ctx: Contexto) -> np.ndarray:
    """Multiplicador de volume por data: pico de meio/fim de ano, leve
    tendencia de crescimento no periodo e queda no fim de semana. Da ao dado
    um comportamento de negocio em vez de ruido uniforme."""
    dt = pd.to_datetime(datas)
    # Sazonalidade mensal (indexada em 1.0), com aquecimento no 2o semestre.
    peso_mes = np.array([0.85, 0.80, 0.95, 1.00, 1.05, 1.00,
                         1.05, 1.10, 1.15, 1.20, 1.25, 1.30])
    mensal = peso_mes[dt.dt.month.to_numpy() - 1]
    # Tendencia linear suave do inicio ao fim da janela (~ +20% no total).
    span = max((ctx.hoje - ctx.inicio).days, 1)
    progresso = (dt - pd.Timestamp(ctx.inicio)).dt.days.to_numpy() / span
    tendencia = 1.0 + 0.20 * progresso
    # Fim de semana movimenta menos.
    semana = np.where(dt.dt.weekday.to_numpy() >= 5, 0.55, 1.0)
    return mensal * tendencia * semana


def escrever_csv(df: pd.DataFrame, saida: Path, nome: str) -> Path:
    """Grava `nome`.csv limpo (tabular puro) em `saida`. O aviso de dado
    ficticio vai num arquivo a parte, para nao sujar o consumo em Power BI."""
    saida.mkdir(parents=True, exist_ok=True)
    caminho = saida / f"{nome}.csv"
    df.to_csv(caminho, index=False, encoding="utf-8")
    return caminho


def escrever_manifesto(
    saida: Path,
    parametros: dict,
    tabelas: dict[str, pd.DataFrame],
    controles: dict[str, list[str]],
) -> Path:
    """Grava `_manifesto.json`: parametros da execucao, linhas por tabela e soma
    das colunas de controle. E o registro de quanto saiu e a referencia para
    conferir se quem consome o dado leu tudo. Sem carimbo de hora de proposito:
    mesma entrada, mesmo arquivo."""
    somas = {}
    for nome, colunas in controles.items():
        df = tabelas[nome]
        somas[nome] = {}
        for col in colunas:
            valores = df[col].to_numpy()
            if np.issubdtype(valores.dtype, np.integer):
                somas[nome][col] = int(valores.sum())
            else:
                # fsum e exato ate o arredondamento final: total de controle estavel.
                somas[nome][col] = round(math.fsum(valores.tolist()), 2)
    manifesto = {
        "parametros": parametros,
        "linhas": {nome: int(len(df)) for nome, df in tabelas.items()},
        "somas": somas,
    }
    saida.mkdir(parents=True, exist_ok=True)
    caminho = saida / "_manifesto.json"
    caminho.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho


def escrever_aviso(saida: Path) -> Path:
    """Grava o aviso de dado ficticio junto dos CSVs da pasta de saida."""
    saida.mkdir(parents=True, exist_ok=True)
    caminho = saida / "_LEIA-dados-sinteticos.txt"
    caminho.write_text(AVISO + "\n", encoding="utf-8")
    return caminho
