"""Helpers compartilhados do motor.

Nada aqui conhece um cenario especifico. Sao ferramentas: gerar o RNG e o
faker semeados, montar o calendario relativo a hoje, aplicar sazonalidade e
escrever CSV com um cabecalho de aviso de dado ficticio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from faker import Faker

# Aviso obrigatorio em toda peca publica (ver POLITICA_DESCARACTERIZACAO.md).
# Vai no topo de cada CSV como comentario e no README do gerador.
AVISO = (
    "Dado 100% sintetico, gerado para demonstracao de portfolio. "
    "Nomes, numeros e entidades sao ficticios, criados por sorteio, sem "
    "relacao com organizacoes, pessoas ou dados reais."
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

    @property
    def inicio(self) -> date:
        # Primeiro dia do mes, `meses` atras, para a janela fechar meses cheios.
        return (self.hoje.replace(day=1) - relativedelta(months=self.meses - 1))


def criar_contexto(seed: int = 42, meses: int = 36, hoje: date | None = None) -> Contexto:
    rng = np.random.default_rng(seed)
    faker = Faker("pt_BR")
    faker.seed_instance(seed)
    return Contexto(rng=rng, faker=faker, hoje=hoje or date.today(), meses=meses)


def calendario(ctx: Contexto) -> pd.DataFrame:
    """Tabela de datas dia a dia, do inicio da janela ate hoje."""
    dias = pd.date_range(start=ctx.inicio, end=ctx.hoje, freq="D")
    nomes_mes = [
        "Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    ]
    dias_semana = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado", "Domingo"]
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


def escrever_aviso(saida: Path) -> Path:
    """Grava o aviso de dado ficticio junto dos CSVs da pasta de saida."""
    saida.mkdir(parents=True, exist_ok=True)
    caminho = saida / "_LEIA-dados-sinteticos.txt"
    caminho.write_text(AVISO + "\n", encoding="utf-8")
    return caminho
