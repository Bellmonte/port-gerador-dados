# port-gerador-dados

Gerador de dado sintético determinístico com um feed diário que roda de graça no GitHub
Actions. Produz um star schema comercial fictício e o mantém atualizado sozinho, servindo de
fonte única de dados para outras peças do portfólio (dashboards de BI, camada de ciência,
lakehouse). É um exercício de como montar uma base de dados plausível, reprodutível e
automatizada do zero, sem depender de nenhuma infraestrutura paga.

> **Dado 100% fictício.** Nomes de cliente, produto e vendedor são sorteados (faker `pt_BR`),
> sem qualquer vínculo com dado real de pessoa ou empresa. Serve para demonstração.

## O que este repositório demonstra

- **Geração de dado sintético plausível**: um star schema comercial (dimensões + fato de
  vendas) com sazonalidade, margem coerente e ~48 mil linhas de venda no padrão, com volume
  ajustável até milhões de linhas.
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

Os CSVs saem em `dados/comercial/`, junto de um aviso de dado fictício e de um
`_manifesto.json`. A janela de datas termina em "hoje", então o dado tem cara de atual sem
nenhuma infra externa.

### Parâmetros

| Parâmetro | Padrão | O que faz |
|---|---|---|
| `--seed` | 42 | semente; a mesma semente gera o mesmo dado |
| `--meses` | 36 | tamanho da janela em meses |
| `--hoje` | o dia da execução | data de corte da janela, no formato `AAAA-MM-DD`. Com ela fixa, duas execuções geram arquivos idênticos em qualquer dia |
| `--saida` | `dados/` | pasta de saída |
| `--linhas` | 48000 | linhas do fato de vendas |
| `--clientes` | 140 | clientes |
| `--produtos` | 24 | produtos |
| `--vendedores` | 16 | vendedores |
| `--colunas-origem` | desligado | gera o fato a partir de pedidos com vários itens e acrescenta `numero_pedido` (texto, `PV-000000123`) e `data_hora_emissao` (data e hora com segundos), como numa extração de ERP |

Sem nenhum parâmetro novo, a saída é a mesma de antes deles existirem.

Com `--colunas-origem`, o fato muda de forma de propósito. Cada pedido sorteia a data pela
sazonalidade, o cliente, um vendedor da região do cliente e o horário de emissão, e todas as
linhas do pedido herdam isso. O número de itens segue 1 mais uma binomial negativa com média de
4 itens: cerca de 19% dos pedidos têm um item, metade tem até 3, um em cada dez passa de 8, e o
teto é 40 (ou o número de produtos, se for menor), porque o pedido não repete produto. Produto,
quantidade, desconto e valores seguem as mesmas regras do fato padrão, e o total de linhas fecha
exatamente em `--linhas`. As dimensões saem iguais com ou sem a opção; o fato não, então os
números de uma base com a opção não se comparam linha a linha com os de uma base sem ela.

### O manifesto

Cada execução grava `_manifesto.json` na pasta de saída, com os parâmetros usados, a contagem de
linhas por tabela e a soma das colunas de valor do fato (quantidade, receita bruta, receita
líquida, custo e margem). Serve para conferir, do lado de quem consome, que o arquivo foi lido
inteiro e que o total bate com a origem. Ele não leva carimbo de hora, então a mesma entrada
produz o mesmo manifesto.

### Base grande, gerada localmente

Para testar desempenho de painel é preciso volume, e o gerador aguenta milhões de linhas. Um
exemplo com o porte de uma distribuidora média:

```bash
python gerar.py comercial --hoje 2026-08-31 --linhas 5000000 --clientes 20000 \
    --produtos 1500 --vendedores 150 --colunas-origem --saida ../base-local
```

Medido numa máquina de mesa comum: 1 milhão de linhas sai em cerca de 7 segundos, com o fato em
110 MB; 5 milhões saem em cerca de 35 segundos, com o fato em 554 MB. **Essa base não entra no
feed nem neste repositório**, porque passa do limite de 100 MB por arquivo do GitHub e porque
qualquer pessoa a reproduz igual com o mesmo comando. Aponte `--saida` para uma pasta fora do
repositório, já que `dados/` é versionada.

### Custo

Zero. O gerador roda local com Python e bibliotecas abertas, e o feed usa a cota gratuita do
GitHub Actions para repositório público.

## O modelo (cenário comercial)

| Tabela | Grão | Papel |
|---|---|---|
| `dim_calendario` | dia | calendário contínuo da janela |
| `dim_produto` | produto | catálogo com preço e custo por categoria |
| `dim_cliente` | cliente | porte, região, cidade |
| `dim_vendedor` | vendedor | região e fator de performance |
| `dim_regiao` | região | peso de mercado |
| `fato_vendas` | linha de venda | quantidade, desconto, receita, custo, margem |

Nome de cliente e de vendedor é único: o sorteio de nomes repete, e as repetições ganham sufixo
numérico (`Azevedo 2`), para que ninguém some duas pessoas ou empresas diferentes ao agrupar por
nome. As chaves continuam sendo `cliente_id` e `vendedor_id`.

Cada cenário é um módulo em `cenarios/`. Para um cenário novo, basta um módulo com uma
função `gerar(ctx)` que devolve as tabelas. Opcionalmente ele declara `PADRAO`, com os valores
usados quando o parâmetro não vem da linha de comando, e `CONTROLES`, com as colunas somadas no
manifesto.

## O feed diário

O workflow em [`.github/workflows/feed.yml`](.github/workflows/feed.yml) roda o gerador todo
dia às 06:00 UTC, com os parâmetros padrão, e comita os CSVs e o manifesto na pasta `dados/`. Qualquer ferramenta lê cada arquivo pela
URL raw do GitHub, por exemplo o Power BI apontando para:

```
https://raw.githubusercontent.com/Bellmonte/port-gerador-dados/main/dados/comercial/fato_vendas.csv
```

Dá para disparar manual pela aba **Actions** (`workflow_dispatch`) além do agendamento.

## Licença

MIT. Use à vontade; o dado é fictício e serve de exemplo.

---

<sub>**B&B** · Matheus Belmonte — do dado à decisão.</sub>
