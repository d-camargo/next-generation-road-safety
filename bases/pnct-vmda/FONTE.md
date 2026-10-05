# Volume Médio Diário Anual (VMDa) — PNCT/DNIT

## O que é

O **Programa Nacional de Contagem de Tráfego (PNCT)** é o programa do DNIT
que estima e/ou mede o volume de veículos que passa por cada trecho da malha
rodoviária modelada, todo ano. O produto usado nesta base é o **Volume Médio
Diário Anual (VMDa)**: uma planilha anual, por trecho do SNV, com o volume
estimado (ou contado) por categoria de veículo (A a J) e sentido (crescente
e decrescente).

O grão do arquivo bruto é **um trecho (ou sub-trecho/"elo") da malha
modelada naquele ano**, não um veículo nem uma contagem física isolada — o
VMDa já é o agregado anual por trecho que o DNIT publica.

⚠️ **A malha modelada NÃO é só a malha federal (SNV) o tempo todo.** Embora
o VMDa nasça do Sistema Nacional de Viação (rodovias federais), pelo menos a
partir de determinado ano o arquivo passa a misturar, no mesmo recorte por
UF, trechos de jurisdição federal, estadual e municipal (coincidentes ou
conectados à malha federal, necessários para a modelagem de rede) — ver a
seção "Composição por jurisdição" abaixo. Um filtro só por UF (o que este
extrator faz) pega TODOS esses trechos, não só os federais.

## URL

Página oficial do PNCT (redireciona para o portal de dados abertos):
<https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/pnct>

Portal de dados abertos onde os arquivos ficam hospedados:
<https://servicos.dnit.gov.br/dadospnct>

## Periodicidade

**Anual.** Um arquivo XLSX por ano, pasta `Volume Médio Diário Anual
(VMDa)/<ano>/VMDa <ano>.xlsx`. A API lista anos desde 2016; esta apuração
baixa **2017 a 2025** (2016 fica fora do escopo — ver `manifest.json`,
`mudancas_metodologicas`).

## Como baixar

O download é feito pela API do PNCT, não por um link estático de arquivo:

```
GET https://servicos.dnit.gov.br/dadospnct-api/api/v1/downloads/diretorios?path=<path>
GET https://servicos.dnit.gov.br/dadospnct-api/api/v1/downloads/file?path=<path>
```

⚠️ O parâmetro é `path` (URL-encoded), **nunca** `filePath` — medido em
2026-09-07 testando as duas variantes contra o endpoint real.
`bin/extrai_pnct_vmda.py::baixar_ano_idempotente` monta a URL de download e
confere o sha256 contra o manifest a cada execução; hash divergente do que
já estava gravado é erro duro.

## Os quatro layouts (narrativa) e os sete cabeçalhos exatos (técnico)

O VMDa não tem layout único — nem entre anos, nem dentro do mesmo ano
comparado a outro. Foram medidos, em 2026-09-07, **sete cabeçalhos exatos
distintos** ao longo de nove anos (2019 e 2020 são idênticos entre si; 2022
e 2023 também; os outros cinco — 2017, 2018, 2021, 2024 e 2025 — divergem
todos entre si, ainda que muitos deles se pareçam). `bin/extrai_pnct_vmda.py`
casa o cabeçalho normalizado (strip + sem acento + minúsculas) contra os
sete registrados em `LAYOUTS`; cabeçalho que não casa com nenhum é **erro
duro**, nunca aviso — a mesma disciplina de `extrai_prf_acidentes.py`.

| Ano | Aba (a que não é "Metadados") | Colunas | Linha do cabeçalho | GEH | km "estimado" |
|---|---|---|---|---|---|
| 2017 | `SNV_201801B_Pav(Entrega31-10)` | 129 | linha 2 (a linha 1 só tem rótulo de grupo mesclado) | não | não |
| 2018 | `SNV_201903A` | 55 | linha 1 | não | sim (`vl_km_i_estim`/`vl_km_f_estim`) |
| 2019 | `SNV_202001A` | 56 | linha 1 | sim | sim |
| 2020 | `SNV202104A` | 56 | linha 1 | sim | sim |
| 2021 | `VMDa 2021` | 41 | linha 1 | sim | não tem par de km nenhum (ver abaixo) |
| 2022 | `SNV202301B` | 55 | linha 1 | sim | sim |
| 2023 | `SNV202401A` | 55 | linha 1 | sim | sim |
| 2024 | `SNV202401A` | 54 | linha 1 | sim | sim |
| 2025 | `VMDa2025_SNV202401A` | 55 | linha 1 | sim | sim, mas a coluna se chama `km_i_estim`/`km_f_estim` (sem o prefixo `vl_`) |

2019/2020 e 2022/2023 têm cabeçalho **idêntico** (mesmo nome de coluna, na
mesma posição) — mesmo assim cada aba declara sua própria `versao_snv` por
linha, e os `id_trecho_` não correspondem entre versões (ver
`bases/prf-acidentes/METODO-ESPACIAL.md`, seção "A chave de junção é BR +
km, não o id do trecho").

⚠️ **2021 usa nomes de coluna COMPLETAMENTE diferentes**, em maiúsculas:
`ID_PNCT`, `ID_MODELO`, `CODIGO_BR`, `REGIAO`, `UF`, `EXTENSAO`,
`SUPERFICIE`, `CODIGO_SNV-SRE`, `CLASSIFICACAO`, `GEH`, mais as 20 colunas
de categoria por sentido `A_AB..J_AB`/`A_BA..J_BA` e os totais já prontos
`VMDA_AB`/`VMDA_BA`/`VMDA_TOTAL`. Não é o mesmo esquema dos demais, e **não
tem NENHUMA coluna de km inicial/final** — só `EXTENSAO` (comprimento total
do trecho). Sem quebra de km, a chave br+km não funciona para 2021: neste
ano, `km_inicial`/`km_final` saem vazios na série tidy e `origem_km` grava
`indisponivel_2021`, para deixar isso explícito em vez de implícito.

## `vmda_total`: qual soma foi usada em cada layout

A série tidy soma, por trecho, as 20 colunas de volume por categoria de
veículo (A a J) × sentido — mas o NOME dessas 20 colunas muda por layout, e
em dois anos (2017 e 2021) a estrutura exige uma decisão explícita:

- **2018 a 2025 (família "padrão"):** as 20 colunas já se chamam
  `A_C..J_C` (crescente) e `A_D..J_D` (decrescente) em todos esses anos —
  soma direta, sem ambiguidade.
- **2021:** as 20 colunas equivalentes se chamam `A_AB..J_AB` e
  `A_BA..J_BA` (a planilha usa "AB"/"BA" em vez de "C"/"D") — mesma soma,
  nomes diferentes. A planilha também já traz um `VMDA_TOTAL` pronto; a série
  tidy soma as 20 colunas (não usa `VMDA_TOTAL` direto), pela mesma
  convenção dos outros anos.
- **2017 (decisão que precisa ficar registrada):** este ano tem TRÊS
  metodologias de estimativa **concorrentes** para o mesmo trecho —
  colunas rotuladas "PNCT", "SGP" e "HDM" — cada uma com sua própria
  quebra por categoria de veículo. Não são camadas que se somam (isso
  contaria o mesmo volume três vezes); são três estimativas alternativas da
  MESMA grandeza. A série tidy usa a metodologia **PNCT** (as 10 colunas
  `VMDa_A..VMDa_J` do bloco "Crescente (C) - PNCT" mais as 10 do bloco
  "Decrescente (D) - PNCT" — 20 no total, mesmas letras A-J dos outros
  anos), e o extrator confere, linha a linha, que essa soma bate com as
  colunas `VMDa_T` (Crescente + Decrescente) que a própria planilha de 2017
  já traz prontas — divergência é erro duro, não é feita "de olho". As
  colunas SGP e HDM existem no arquivo bruto mas não entram no
  `vmda_total`.

Onde a soma não é possível numa linha específica (alguma das 20 colunas
vem como texto "-", not-a-number, em vez de valor — típico de trecho ainda
"Planejado", sem tráfego para medir), `vmda_total` fica **vazio nessa
linha**, nunca zero: zero afirmaria "sem tráfego", vazio afirma "não
medido/não modelado".

⚠️ **A guarda que confere PNCT × `VMDa_T` tolera diferença ≤ 1,0, mas conta
e imprime quantas linhas tolerou — nunca em silêncio.** Medido em
2026-09-08, nas **2.031** linhas dos dez corredores (`BRS_CORREDORES` em
`bin/extrai_pnct_vmda.py`) em 2017: a soma da família **PNCT** (A–J) diverge
de `VMDa_T` em só **1** linha (BR-153/TO), com diferença de **1,0**
veículo/dia — ruído da fonte (arredondamento/digitação), não erro de leitura
de coluna; acima de 1,0 a guarda continua falhando duro. A soma da família
**HDM** (`VMDa_P`, `VMDa_2CB`, `VMDa_2C`… — 13 colunas × 2 sentidos)
reproduz `VMDa_T` do mesmo jeito: diverge na MESMA única linha, com a MESMA
diferença de 1,0. Já a soma da família **SGP** (`VMDa_P1P3`, `VMDa_O1`,
`VMDa_C1`… — 12 colunas × 2 sentidos) diverge de `VMDa_T` em **1.959** das
2.031 linhas, com diferença máxima de **3,95** veículos/dia (MG, BR-381).
Ou seja: **PNCT e HDM reproduzem `VMDa_T`; só SGP diverge sistematicamente**
— a série tidy usa PNCT por ser a metodologia com as mesmas 10 categorias
A-J dos outros oito anos da série (não porque seja a única que bate com
`VMDa_T`: HDM também bate), mas trocar por SGP mudaria o total sistemática e
silenciosamente. `bin/verificadores.py::pnctvmda_2017_familia_diff_max`
recomputa estes três números a cada `pytest`.

## `km_inicial`/`km_final`: qual par foi usado (`origem_km`)

O SNV quebra cada trecho num sub-link (`vl_km_inic`/`vl_km_fina`, os limites
"oficiais" do trecho no cadastro), e a partir de 2018 o VMDa também traz um
par "estimado" (`vl_km_i_estim`/`vl_km_f_estim`, ou `km_i_estim`/`km_f_estim`
em 2025) — os limites do SUB-trecho onde a contagem/estimativa de tráfego
realmente muda de valor, que pode ser mais fino que o sub-link oficial. A
série tidy usa o par **estimado** quando ele existe numa linha, e registra
qual par foi usado na coluna `origem_km`:

- `estimado`: usou `vl_km_i_estim`/`vl_km_f_estim` (ou o par equivalente de
  2025) — 2018 a 2025.
- `oficial`: usou `vl_km_inic`/`vl_km_fina` — 2017 (não tem par estimado
  nenhum) e qualquer linha, em qualquer ano da família "padrão", em que o
  par estimado vier vazio/não numérico.
- `indisponivel_2021`: nenhum par existe no arquivo de 2021 (ver acima).

## `extensao_km`: qual valor foi usado (`origem_extensao`) — corrigido em 2026-09-08

`vl_extensa` é a extensão do trecho-**PAI** do SNV, repetida em cada
sub-link — somá-la conta a mesma extensão várias vezes (ver
`bases/prf-acidentes/METODO-ESPACIAL.md`, "Os dois erros de leitura da fonte
que a medição pegou"). A partir de 2018 o VMDa também traz `vl_ext_estim`
(`ext_estim` em 2025, sem o prefixo `vl_`, mesmo padrão de
`vl_km_i_estim`→`km_i_estim`): a extensão do **sub-link**, a que de fato
corresponde à faixa `[km_inicial, km_final]` daquela linha. A série tidy usa
`vl_ext_estim` quando o layout do ano traz essa coluna, e registra qual foi
usado em `origem_extensao`:

- `estimado`: usou `vl_ext_estim` — 2018 a 2024.
- `oficial`: usou `vl_extensa` — 2017, 2021 (nenhum dos dois tem coluna de
  extensão estimada) e **2025** (decisão explícita, ver nota abaixo).

⚠️ **2025 tem uma coluna chamada `ext_estim`, com dado preenchido em 100% das
1.133 linhas de MG** — medido em 2026-09-08 ao corrigir este defeito. Ela seria
o equivalente exato de `vl_ext_estim`, mas foi **deliberadamente deixada de
fora** desta rodada de correção (fica `oficial`, como 2017/2021), porque a
decisão de tratá-la como `estimado` muda o número publicado de 2025 e não
estava no escopo desta correção — decidir com o Diego antes de estender.
Ano com `oficial` **não é comparável** a ano com `estimado`: é por isso que
`extensao_vmda_km` de 2025 salta para 30.037 km na tabela de cobertura de
`bin/mede_cobertura_vmda.py`, enquanto 2024 (mesma malha, `estimado`) fica em
15.981 km — a diferença é de origem do dado, não de crescimento da malha.

## `contagem_trecho` de 2017 sem extensão nem km

Um bloco de trechos do arquivo de 2017 (identificados só por
`id_trecho_`/`vl_br`/`sg_uf`/`vl_codigo`, sem nenhum outro metadado
preenchido — nem `vl_km_inic`, nem `vl_extensa`) tem esses campos vazios na
planilha bruta. A série tidy preserva isso como vazio (`extensao_km`,
`km_inicial`, `km_final`) em vez de inventar um valor. Estão presentes tanto
no recorte nacional quanto no recorte MG desse ano.

## Composição por jurisdição (medido, não é só "a malha cresceu")

O crescimento da malha modelada entre 2017 e 2024 (ver
`bases/prf-acidentes/METODO-ESPACIAL.md`) não é só "mais do mesmo tipo de
trecho": a **composição por jurisdição** dentro do próprio arquivo também
muda. Em 2018, todo trecho em MG vem com jurisdição só federal
(`ds_jurisdi` começando em "FEDERAL-"). Em 2024, o mesmo arquivo já mistura
trechos "Federal", "Estadual" e "Municipal" sob a mesma UF — a maioria
ainda é federal, mas uma fração relevante não é. Isso significa que
"trechos no VMDa daquele ano" não é uma medida de "malha federal": é uma
medida de "tudo que o PNCT modelou naquela UF", que inclui vias não
federais coincidentes/conectadas à malha SNV.

2021 leva isso ao extremo: além de ter muito mais linhas por MG que
qualquer outro ano, boa parte delas tem `CODIGO_BR` = `-` (trecho do tipo
"Conector", sem jurisdição nem tipo de via classificados) ou um código
placeholder (`999` para via municipal, `900` para trecho estadual/municipal
com numeração própria) — nenhum dos dois é um número de rodovia federal de
verdade. `bin/extrai_pnct_vmda.py::normalizar_br` NÃO faz zero-padding
nesses placeholders (só em sequências só-de-dígitos), para não fabricar algo
como `-00` a partir de um traço que significa "não se aplica".

**Carregado na série tidy desde 2026-09-08:** `jurisdicao_bruta` (o valor como
veio da fonte — `ds_jurisdi` na família "padrão", `jurisdicao` em 2021, sem
nenhuma coluna equivalente em 2017) e `jurisdicao` (normalizada por
`bin/extrai_pnct_vmda.py::normalizar_jurisdicao`: prefixo, insensível a
caixa — qualquer valor começando com `federal`/`estadual`/`municipal` cai na
respectiva categoria; vazio ou qualquer outra coisa vira `indefinida`). O
vocabulário muda de ano para ano (`FEDERAL-PAV`/`FEDERAL-PLA` em 2018/2020;
`Federal`/`Estadual`/`Municipal` em 2022-2025; `-` em 2021 para os
"Conectores" do parágrafo acima), e a normalização por prefixo é o que os
junta sem inventar equivalência que a fonte não declarou.

⚠️ **`indefinida` nunca é promovida a `federal` por suposição.** Em MG, isso
pesa em três anos: 2017 tem 9.642 km sem `ds_jurisdi` preenchido (a coluna
vem majoritariamente vazia nesse arquivo — 488 das 901 linhas), 2018 tem
9.415 km e 2020 tem 9.362 km — mais da metade da malha modelada em cada um
dos três. Decidir o que fazer com eles (incluir como federal, excluir, ou
tirar esses anos da análise que depende de jurisdição) é decisão do Diego,
registrada como aberta em `bases/prf-acidentes/METODO-ESPACIAL.md`.

## GEH (contado × modelado)

O VMDa traz, a partir de determinado ano, um campo `GEH` que classifica o
trecho pela estatística GEH (uma medida usual de comparação entre volume
contado e volume modelado em engenharia de tráfego), em faixas A/B/C/D.
2017 e 2018 não têm esse campo na série tidy: 2018 não tem coluna nenhuma
equivalente; **2017 tem uma coluna chamada `GEH_T`, com o mesmo vocabulário
de faixas (A/B/C/D) do `GEH` dos anos seguintes** — mas essa coluna está
associada especificamente à metodologia PNCT dentre as três que 2017 traz
(ver seção `vmda_total` acima), enquanto o `GEH` dos anos seguintes não tem
mais essa distinção de metodologia para se referenciar. Por não serem
claramente a mesma grandeza medida da mesma forma, `GEH_T` de 2017 **não**
alimenta a coluna `geh` da série tidy — fica de fora, documentado aqui, em
vez de tratado como equivalente sem prova.

## Estrutura da série tidy

`bases/pnct-vmda/series/vmda_mg_por_trecho_2017_2025.csv`, uma linha por
trecho (ou sub-trecho, para os anos com quebra por sub-link) em Minas
Gerais, por ano: `ano`, `chave_linha` (sequencial, só para o schema
genérico de `bin/build_db.py` — a chave de junção real é br+km, não esta),
`uf`, `br` (zero-padded a 3 dígitos quando é só dígitos), `km_inicial`,
`km_final`, `origem_km`, `extensao_km`, `origem_extensao` (`estimado` ou
`oficial` — ver seção acima), `vmda_total`, `superficie`, `geh`,
`classificacao`, `versao_snv`, `jurisdicao_bruta`, `jurisdicao` (`federal` /
`estadual` / `municipal` / `indefinida` — ver seção acima),
`contagem_trecho` (sempre 1 — conta trechos quando somada), `escopo`,
`harmonizada` (sempre 0: esta série não é harmonizável entre anos, ver
`manifest.json`/`mudancas_metodologicas` e
`bases/prf-acidentes/METODO-ESPACIAL.md`).
