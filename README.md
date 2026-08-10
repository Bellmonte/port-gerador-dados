# port-gerador-dados

Gerador de dado sintético determinístico e um feed diário que roda de graça no GitHub
Actions. É a fundação de dados do portfólio **B&B Vector**: todas as demais peças (dashboards
de BI, camada de ciência, lakehouse) consomem os CSVs que saem daqui, de uma fonte única.

> **Dado 100% fictício.** Nomes de cliente, produto e vendedor são sorteados (faker `pt_BR`),
> sem qualquer vínculo com dado real de pessoa ou empresa. Serve para demonstração.

## O que este repositório demonstra

- **Geração de dado sintético plausível**: um star schema comercial (dimensões + fato de
  vendas) com sazonalidade, margem coerente e ~48 mil linhas de venda.
- **Reprodutibilidade**: semente fixa e dependências pinadas, então o mesmo comando gera o
  mesmo dado em qualquer máquina.
- **Automação de custo zero**: um workflow do GitHub Actions regenera e publica os dados
  todo dia, sem servidor nem banco. O próprio Action já é a prova da automação.

## Como rodar

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows (Linux/Mac: .venv/bin/pip)
python gerar.py comercial
```

Os CSVs saem em `dados/comercial/`, junto de um aviso de dado fictício. A janela de datas
termina em "hoje", então o dado tem cara de atual sem nenhuma infra externa.

Parâmetros: `--seed` (default 42), `--meses` (default 36), `--saida` (pasta de saída).

## O modelo (cenário comercial)

| Tabela | Grão | Papel |
|---|---|---|
| `dim_calendario` | dia | calendário contínuo da janela |
| `dim_produto` | produto | catálogo com preço e custo por categoria |
| `dim_cliente` | cliente | porte, região, cidade |
| `dim_vendedor` | vendedor | região e fator de performance |
| `dim_regiao` | região | peso de mercado |
| `fato_vendas` | linha de venda | quantidade, desconto, receita, custo, margem |

Cada cenário é um módulo em `cenarios/`. Para um cenário novo, basta um módulo com uma
função `gerar(ctx)` que devolve as tabelas.

## O feed diário

O workflow em [`.github/workflows/feed.yml`](.github/workflows/feed.yml) roda o gerador todo
dia às 06:00 UTC e comita os CSVs na pasta `dados/`. Qualquer ferramenta lê cada arquivo pela
URL raw do GitHub, por exemplo o Power BI apontando para:

```
https://raw.githubusercontent.com/Bellmonte/port-gerador-dados/main/dados/comercial/fato_vendas.csv
```

Dá para disparar manual pela aba **Actions** (`workflow_dispatch`) além do agendamento.

## Licença

MIT. Use à vontade; o dado é fictício e serve de exemplo.
