# Método — análise espacial dos sinistros da PRF em Minas Gerais

> Documento de trabalho. Registra as decisões e as pegadinhas medidas da análise
> espacial dos sinistros em rodovias federais em MG. Criado em 2026-09-07.
> Enquanto a análise não fecha, este arquivo é a memória dela: o que foi
> decidido, por quê, e o que ainda está aberto.

## O que se quer medir

Se os sinistros em rodovias federais de Minas Gerais se concentram no espaço
além do que o acaso explicaria — e onde. A ferramenta é a autocorrelação
espacial (Moran global e LISA), e a pergunta só faz sentido sobre uma **taxa**,
nunca sobre contagem bruta: contagem alta onde passa a rodovia mais movimentada
não é achado, é tautologia.

## Por que a unidade NÃO é o município

A primeira versão do desenho agregava por município. Isso quebra por um motivo
que não é de implementação: **sinistro em rodovia é fenômeno linear**, e
agregar por área impõe uma unidade arbitrária a ele. Pior, cria indefinidos —
município sem rodovia federal tem denominador zero, e "sinistros por km de
federal" vira 0/0, não zero. Excluí-los abre buracos na malha e desfaz a
contiguidade.

A unidade é a **faixa de 10 km ao longo de cada BR**, com teste de sensibilidade
em 5 km e 20 km. A faixa é estável entre anos por construção — o que resolve o
problema da seção seguinte — e a vizinhança passa a ser a natural do fenômeno:
faixas adjacentes na mesma rodovia.

⚠️ Comprimento de faixa é a **unidade modificável** em forma linear: ele muda o
resultado do Moran. Não há comprimento "certo"; há o comprimento declarado e o
teste que mostra se o padrão sobrevive a ele.

Este desenho — partir do sinistro e procurar exposição — foi abandonado depois
de medida a cobertura do VMDa sobre ele. A razão do abandono e o desenho que
o substituiu estão registrados na seção seguinte, sobre a inversão do
critério de entrada.

## A lógica foi invertida (2026-09-08)

O desenho original partia do sinistro e procurava exposição. A medição de
cobertura mostrou que isso não fecha: o VMDa não cobre toda a malha onde há
sinistro, a perda varia por ano, e nos anos iniciais a própria rede modelada é
menor. Tratar essa perda seria administrar um problema evitável.

Invertido, o critério de entrada passa a ser o **dado de exposição**: entram os
**10 principais corredores federais por veículo-km/dia** (BR-101, 116, 163, 153,
364, 381, 050, 376, 158, 135 — cerca de 28.300 km, cobertura de 72% a 91%), e os
sinistros são recortados a partir deles. O problema do denominador ausente deixa
de existir por construção.

⚠️ **Selecionar corredores, não links.** Os 583 links `Referencial` (pontos de
contagem) são o melhor dado do país — 16.378 km sem nenhum link sem volume —,
mas **não são contíguos**. Moran sobre eles mediria semelhança entre pontos de
contagem distantes, não concentração ao longo da via: outra pergunta, mais
fraca. Corredor inteiro preserva a contiguidade linear, que é a estrutura
espacial do fenômeno.

⚠️ **O que sai por dado, e não por irrelevância.** A BR-040 (Brasília–BH–Rio)
fica em 15º e não entra: **53 dos seus 100 links são "Não Simulável"**. A
ausência dela é da fonte, não da pergunta, e quem ler o resultado precisa saber
disso. A BR-262 fica em 11º por margem pequena (7,49 M contra 7,59 M da BR-135)
e tem 24 pontos de contagem, o quarto maior do país — é a primeira candidata num
teste de sensibilidade do corte.

⚠️ **Minas continua no trabalho**, como validação do método: é o estado com mais
pontos de contagem do país (104 em 2024, à frente de SP com 61), e três dos dez
corredores (116, 381, 050) o cruzam. O pipeline roda primeiro lá, onde o dado é
mais denso, antes do nacional.

### Os dois erros de leitura da fonte que a medição pegou

1. **`vl_extensa` é a extensão do trecho-PAI do SNV, repetida em cada
   sub-link.** Somá-la dá 173.976 km para o Brasil — mais que o dobro da malha
   real. A extensão do sub-link é `vl_ext_estim`, e com ela a soma é **103.440
   km**. O sintoma que denunciou: a BR-374 aparecia entre as mais movimentadas
   do país com 690 km, o que não fazia sentido — corrigido, ela sai do topo.
2. **`GEH` não é índice numérico: é nota (A, B, C, D)**, e só existe para links
   `classificação = 'Referencial'` (583 no país em 2024; 529 deles nota A).
   Quem informa qualidade do dado é o campo `classificação`, não o GEH.

### A tabela dos corredores (medida em 2024, extensão de sub-link)

| BR | km | % com volume | pontos de contagem | veic-km/dia |
|---|---|---|---|---|
| 101 | 4.378 | 74,5% | 57 | 36.770.676 |
| 116 | 4.376 | 85,3% | 57 | 34.809.976 |
| 163 | 4.118 | 71,8% | 28 | 16.581.767 |
| 153 | 3.255 | 91,4% | 34 | 14.494.895 |
| 364 | 3.587 | 86,4% | 15 | 14.293.132 |
| 381 | 1.162 | 83,0% | 13 | 14.110.635 |
| 050 | 964 | 75,9% | 16 | 11.112.855 |
| 376 | 883 | 79,3% | 8 | 9.003.639 |
| 158 | 3.220 | 84,9% | 15 | 7.690.232 |
| 135 | 2.394 | 84,6% | 10 | 7.591.356 |

Composição nacional por classe (2024, km de sub-link): `Referencial` 16.378 km
com **zero** links sem volume; `-` (modelado) 106.325 km; `Não Simulável`
27.371 km; `Não Pavimentada` 23.812 km (todos os 639 sem volume).

## Jurisdição: o denominador não pode ser mais largo que o numerador

A PRF policia **exclusivamente** a malha federal. O VMDa recente não: em Minas,
em 2023 e 2024, cerca de 45% dos quilômetros modelados são de via **estadual ou
municipal**, carregando aproximadamente 27% do veículo-quilômetro. Incluí-los no
denominador cobriria via que o numerador nunca cobre, e a taxa sairia
subestimada — de forma desigual entre anos, porque a composição muda.

Por isso a série carrega `jurisdicao`, e a análise usa **só `federal`**.

⚠️ **O vocabulário da fonte muda**: `FEDERAL-PAV`/`FEDERAL-PLA` em 2018 e 2020;
`Federal`/`Estadual`/`Municipal` em 2023–2025. Pior, em 2018 e 2020 mais da
metade dos quilômetros de Minas (~9.400 km) vem **sem valor nenhum** de
jurisdição. Esses ficam marcados como `indefinida` e **não são promovidos a
federal por suposição** — decidir o que fazer com eles é decisão de método, e
está em aberto.

⚠️ **Corrigido na mesma rodada:** a coluna `extensao_km` da série vinha de
`vl_extensa` (trecho-pai) e estava inflada quase 2× — 30.037 km contra 15.981
km reais em 2024. Extensão é fator direto do veículo-quilômetro; o erro
contaminava o denominador inteiro. Agora vem de `vl_ext_estim` (ou de
`ext_estim` em 2025 — ver nota de prefixo abaixo, "Os quatro layouts do
VMDa"), com `origem_extensao` dizendo quando o ano não tem o campo (só
2017; 2025 tem, apesar do nome sem prefixo).

⚠️ **A perda muda de escala quando se exige jurisdição federal**: 61–63% em 2017–2020, contra 16–34% de 2022 em diante. A diferença não é do tráfego nem da PRF — é que naqueles anos mais da metade dos quilômetros de Minas vem sem jurisdição declarada na fonte.

Há uma hipótese testável para isso: que nos anos antigos o campo só fosse preenchido para trechos federais, e que o vazio signifique "não federal" (em 2018 os `FEDERAL-*` somam 7.553 km; em 2023 os `Federal` somam 8.626 km, em redes de tamanho parecido). O teste é cruzar os trechos sem jurisdição com a classificação do SNV atual: cruzando por BR + faixa de km contra o SNV 202507a (`raw/geo-referencia/dnit_snv_mg_202507a.geojson`, a mesma fonte de `geo.dnit_snv_mg`, com `vl_km_inic`/`vl_km_fina` preservados — a tabela do PostGIS não guarda km), dos **18.777,2 km** `indefinida` de 2018 e 2020 (9.415,2 km em 2018, 9.362,0 km em 2020 — batendo com `km_indefinida` de `bin/mede_cobertura_vmda.py`), **18.698,6 km** (99,6%) caem em faixa coberta por algum trecho do SNV 202507a com a mesma BR (14,6 km não têm nenhuma correspondência); desses, **5.334,4 km** (28,5% do coberto; 28,4% do total `indefinida`) caem em trecho que o SNV 202507a classifica como Federal, e os outros **13.364,2 km** (71,5% do coberto) caem em Estadual ou Municipal. Por ano: 2018 tem 2.739,9 km (29,1% do seu `indefinida`) em trecho hoje Federal; 2020 tem 2.594,5 km (27,7%).

A fração medida (≈28%) fica acima do corte de 20% que separaria "vazio ≈ não federal" de "vazio é omissão de preenchimento"; ao mesmo tempo não é alta o bastante para dizer que o vazio é puro erro de preenchimento — o resultado é ambíguo em relação à hipótese original, não a confirma nem a derruba, e não autoriza tratar o vazio como equivalente a "não federal"; a decisão sobre o que fazer com os anos antigos cabe ao Diego.

## Mudança de jurisdição também quebra o NUMERADOR

A seção anterior trata do denominador. Há o problema espelhado, e ele é pior
porque parece resultado: **quando um trecho deixa de ser federal, a PRF deixa de
policiá-lo e para de registrar sinistro ali**. Aquele quilômetro zera na
contagem — não porque ficou seguro, mas porque o registrador foi embora. Numa
série temporal isso vira "queda de acidentes"; num Moran, vira trecho frio
cercado de quentes.

Medido em Minas, comparando 2022 com 2024 (os anos com vocabulário de jurisdição
explícito), em bins de 1 km:

| Grupo | Bins | Sinistros 2022 | Sinistros 2024 |
|---|---|---|---|
| Perderam a jurisdição federal | 139 | **33** | **6** |
| Controle: federais estáveis | 139 | 267 | 283 |

Queda de 82% no grupo que perdeu a tutela federal, contra um controle que não se
mexe (214 a 315 sinistros por ano, sem quebra de tendência).

⚠️ **São números pequenos** (33 contra 6). A queda isolada é sugestiva, não
conclusiva. O que sustenta a leitura é o conjunto: o controle estável, a
concentração estrutural descrita abaixo, e o mecanismo, que é conhecido e não
precisa ser inferido — a PRF policia a malha federal, e o que sai dela sai do
boletim.

### O efeito é confinado à franja planejada

A rotatividade de jurisdição não é uniforme. Medida nos bins com jurisdição
declarada em pelo menos dois anos (2022–2025):

| Superfície | Bins | Mudaram de jurisdição | % |
|---|---|---|---|
| `PLA` (planejada) | 8.254 | 219 | **2,65%** |
| `PAV` (pavimentada) | 8.091 | 36 | **0,44%** |
| `N_PAV` | 632 | 5 | 0,79% |

Rodovia federal **implantada e pavimentada praticamente não troca de tutela**.
A oscilação mora na franja `PLA`: designação federal prevista, estrada física
existente sob outra jurisdição, status mudando entre versões do SNV. Os 139 bins
que perderam a federal são `PLA` em **100%**.

O grupo inverso confirma por outro caminho: 75 bins ganharam jurisdição federal
entre 2022 e 2024 e têm **zero sinistros de 2021 a 2025** — mas 46 deles são
`PLA` e 40 são "Não Pavimentada", com 40 sem volume nenhum. Zero ali é ausência
de estrada trafegada, não ausência de registro. A jurisdição não explica esse
grupo, e não se deve forçá-la a explicar.

### A regra de entrada que isso impõe

Entram na análise apenas trechos **`PAV` ou `DUP`** com jurisdição **federal
estável em todos os anos que declaram jurisdição (2022–2025)**. Bin que muda de
tutela sai, e o número de bins excluídos por essa regra é reportado junto com o
resultado. Por que essa definição vale retroativamente para 2017–2021, ver "O
painel: a rede é definida pelos anos que declaram jurisdição".

Assim a descontinuidade de numerador não fica "improvável": ela é impossível por
construção, e o leitor vê quanto custou. A regra também conversa com o recorte
dos dez corredores — todos implantados e pavimentados, justamente a categoria
com 0,44% de rotatividade.

## O painel: a rede é definida pelos anos que declaram jurisdição

Em 2017–2020 a fonte não declara jurisdição para mais da metade da malha (~9.400
km/ano em Minas). Exigir jurisdição federal explícita em **todos** os anos
deixaria 4.502 bins de 1 km e capturaria só 31–34% dos sinistros de cada ano —
dois terços do dado fora.

A decisão foi outra: **a rede é definida pelos anos que declaram jurisdição
(2022–2025) e essa definição vale para a série inteira.**

Painel final: bins de 1 km com jurisdição **federal** e superfície **`PAV` ou
`DUP`** em todos os anos de 2022–2025 — **7.078 bins**.

| Ano | Sinistros no painel | Total do ano | Cobertura |
|---|---|---|---|
| 2017 | 10.124 | 12.721 | 79,6% |
| 2018 | 7.245 | 9.073 | 79,9% |
| 2019 | 6.771 | 8.736 | 77,5% |
| 2020 | 6.584 | 8.376 | 78,6% |
| 2021 | 6.544 | 8.334 | 78,5% |
| 2022 | 6.454 | 8.295 | 77,8% |
| 2023 | 7.141 | 9.007 | 79,3% |
| 2024 | 7.425 | 9.296 | 79,9% |
| 2025 | 7.632 | 9.570 | 79,7% |

### Por que a inferência se sustenta

Não é conveniência. São três coisas medidas:

1. **Rodovia federal pavimentada quase não troca de tutela**: 0,44% de
   rotatividade em quatro anos (seção anterior). Um trecho federal em 2022–2025
   era, quase certamente, federal em 2018 — o campo é que estava vazio, não a
   tutela é que era outra.
2. **A cobertura é plana nos nove anos**: 77,5% a 79,9%, sem deriva. Se a rede
   definida pelos anos recentes estivesse errada para os antigos, a cobertura
   cairia à medida que se recua no tempo. Ela não cai. **A estabilidade é o teste
   passando**, não um efeito colateral agradável.
3. O painel alternativo, sem inferência nenhuma (federal explícito nos oito
   anos), existe e está medido: 4.502 bins, 31–34% de cobertura. Fica registrado
   como recorte de sensibilidade — quem duvidar da inferência pode rodar nele e
   comparar.

### Os dois erros residuais

**Trecho delegado ao estado antes de 2022** aparece como não federal em 2022–2025
e sai do painel, mesmo tendo sinistro registrado em 2018. É erro **conservador**
— exclui em vez de incluir — e raro, pela taxa de 0,44%.

**Trecho que virou federal depois de 2020** entraria carregando anos em que a PRF
não registrava ali, e pareceria seguro por artefato. Esse é o perigoso, e foi
medido: são 75 bins, dos quais 46 `PLA` e 40 "Não Pavimentada". **O filtro
`PAV`/`DUP` elimina praticamente todos** — é para isso que ele está no painel,
não só pela estabilidade de tutela.

⚠️ **2021 continua sem denominador próprio.** O painel coloca os sinistros de
2021 (78,5% deles), mas o VMDa daquele ano não tem faixa de km e não produz
exposição. 2021 fica fora do cálculo de taxa, e não se interpola — inventar
denominador para fechar a série é exatamente o que este documento existe para
impedir.

## A chave de junção é BR + km, não o id do trecho

O VMDa quebra o trecho do SNV em sub-links, então `id_trecho_` **se repete** e
não é chave. Além disso cada ano do VMDa é quebrado numa versão diferente do SNV
(201801B, 201903A, 202001A, 202104A, 202301B, 202401A), e os ids não
correspondem entre versões.

BR + km é referência física e estável entre versões. É a chave.

⚠️ Normalização obrigatória: a PRF grava a BR como `40`, o VMDa como `040`
(zero-padding para 3 dígitos); o `km` da PRF é texto com vírgula decimal.

## A rede do PNCT cresceu — e isso não é detalhe

Medido nos arquivos anuais, em MG:

| Ano | Trechos | Extensão modelada |
|---|---|---|
| 2017 | 901 | 18.137,6 km |
| 2018 | 905 | 22.127,1 km |
| 2024 | 1.133 | 30.037,3 km |

A rede modelada cresceu **66%** entre 2017 e 2024. Não é defeito do dado: o
programa de contagem expandiu. Mas é uma armadilha de comparabilidade, da mesma
família da que já derrubou uma leitura do Censo Escolar neste repo — aritmética
fechando não prova comparabilidade.

Consequências, que valem como regra desta análise:

1. **Moran por ano é legítimo. Comparar o Moran entre anos, não** — a malha
   embaixo mudou. Afirmação temporal exige restringir às faixas com VMDa em
   **todos** os anos (painel balanceado), e isso tem que estar escrito no
   achado.
2. Sinistro em trecho sem VMDa **não tem denominador** e sai da taxa. O tamanho
   dessa perda por ano está na seção "Cobertura medida".

## Cobertura medida (2026-09-07, corrigida em 2026-09-08)

```
ano  | sinistros_ano | excluidos_grau_inteiro | sinistros_considerados | dentro_com_volume | dentro_sem_volume | fora_de_qualquer_faixa | pct_sem_denominador | origem_km         | extensao_vmda_km | brs_sinistros | brs_vmda
-----+---------------+------------------------+------------------------+-------------------+-------------------+------------------------+---------------------+-------------------+------------------+---------------+---------
2017 | 12721         | 19                     | 12702                  | 12646             | 0                 | 56                     | 0.44                | oficial           | 18137.6          | 17            | 45      
2018 | 9073          | 7                      | 9066                   | 7944              | 415               | 707                    | 12.38               | estimado          | 22127.1          | 17            | 46      
2019 | 8736          | 5                      | 8731                   | 7326              | 701               | 704                    | 16.09               | estimado          | 22214.8          | 18            | 46      
2020 | 8376          | 0                      | 8376                   | 7063              | 742               | 571                    | 15.68               | estimado          | 22432.0          | 17            | 46      
2021 | 8334          | 1                      | 8333                   | 0                 | 0                 | 8333                   | 100.0               | indisponivel_2021 | 33777.4          | 15            | 260     
2022 | 8295          | 0                      | 8295                   | 6928              | 631               | 736                    | 16.48               | estimado          | 19726.7          | 16            | 42      
2023 | 9007          | 1                      | 9006                   | 6105              | 2249              | 652                    | 32.21               | estimado          | 21808.0          | 18            | 43      
2024 | 9296          | 0                      | 9296                   | 6335              | 1499              | 1462                   | 31.85               | estimado          | 30037.3          | 15            | 46      
2025 | 9570          | 12                     | 9558                   | 6601              | 1414              | 1543                   | 30.94               | estimado          | 30037.3          | 16            | 46      

Total de registros excluídos por coordenada em grau inteiro (2017-2025): 45
```

A tabela acima é a saída corrigida de `bin/mede_cobertura_vmda.py` (ver seu
docstring, "O defeito da medição antiga"). A versão anterior contava um
sinistro como coberto sempre que caísse em **qualquer** faixa do VMDa daquele
ano, inclusive faixa sem estimativa de volume — o que superestimava a
cobertura. O número mais afetado era o de **2017**: aparecia com a menor
perda da série (0,44% fora) não porque a cobertura real ali fosse melhor, mas
porque 2017 é o único ano com `origem_km='oficial'` (faixas do trecho-pai do
SNV, mais largas e sem vãos entre elas), enquanto os demais usam `estimado`
(sub-link, com vãos). Um sinistro só conta como coberto (`dentro_com_volume`)
agora se cai numa faixa com `vmda_total > 0` e `classificacao` fora de
`{Não Simulável, Travessia - Não Simulável, Não Pavimentada}`; caso contrário
entra em `dentro_sem_volume` (faixa existe, sem denominador) ou
`fora_de_qualquer_faixa` (não caiu em faixa nenhuma).

2021 continua sem par de km na fonte (`origem_km='indisponivel_2021'`): 100%
fora não é uma medida de descolamento espacial, é ausência de chave — é
reportado como indisponível, não corrigido. Entre os anos em que a chave
br+km funciona, a maior perda (`pct_sem_denominador`) é em 2023, com 32,21%.

## Volume modelado × volume contado

O VMDa traz o campo `GEH`, que distingue link efetivamente **contado** (Count
Location, referencial) de link **modelado**. Decisão: todos os links entram, e a
classificação viaja junto como atributo — o achado tem que dizer quanto do
resultado se apoia em volume modelado. Restringir só aos contados deixaria a
malha esparsa demais para contiguidade.

⚠️ 2017 e 2018 **não trazem GEH**. Nesses anos não é possível separar contado de
modelado, e qualquer leitura que dependa dessa distinção não vale para eles.

## Os quatro layouts do VMDa

| Ano | Aba | Colunas | Cabeçalho | GEH | campo de sub-link (km/ext estim.) |
|---|---|---|---|---|---|
| 2017 | `SNV_201801B_Pav(Entrega31-10)` | 129 | **linha 1** | não | não |
| 2018 | `SNV_201903A` | 55 | linha 0 | não | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2019 | `SNV_202001A` | 56 | linha 0 | sim | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2020 | `SNV202104A` | 56 | linha 0 | sim | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2021 | `VMDa 2021` | — | linha 0 | — | — |
| 2022 | `SNV202301B` | 55 | linha 0 | sim | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2023 | `SNV202401A` | 55 | linha 0 | sim | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2024 | `SNV202401A` | 54 | linha 0 | sim | sim (`vl_km_i_estim`/`vl_km_f_estim`/`vl_ext_estim`) |
| 2025 | `VMDa2025_SNV202401A` | 55 | linha 0 | sim | **sim** (`km_i_estim`/`km_f_estim`/`ext_estim` — sem o prefixo `vl_`) |

2021 usa nomes de coluna inteiramente diferentes, em maiúsculas (`ID_PNCT`,
`CODIGO_BR`, `UF`, `EXTENSAO`). O extrator detecta o layout pelo cabeçalho e
falha duro em cabeçalho desconhecido.

⚠️ **O nome do campo de sub-link muda de prefixo entre anos** — pegadinha já
medida uma vez neste documento e que passou batido na primeira sondagem de
2025: em 2018–2024 os três campos vêm como `vl_km_i_estim`/`vl_km_f_estim`/
`vl_ext_estim`; em 2025 a mesma planilha traz os mesmos três campos, com o
mesmo preenchimento (100% das 1.133 linhas de MG), só que **sem o prefixo
`vl_`** (`km_i_estim`/`km_f_estim`/`ext_estim`). Uma sondagem por nome exato
que não busque as duas variantes conclui, errado, que o ano não tem o campo
— foi exatamente o que aconteceu aqui antes de ser corrigido.

## Coordenadas descartadas

53 dos 88.859 sinistros entraram no PostGIS com coordenada em **grau inteiro**
(`-22` / `-44`), precisão de ~100 km. A amostra mostra que não caem no município
que o próprio registro declara. Eles saem da análise espacial, com a exclusão
declarada — são 0,06% do total.

Outros 9 registros ficaram na quarentena da ingestão por caírem fora da caixa
envolvente de MG (`build/quarentena_geo_prf_mg.csv`): ilha nula (`0`/`0`),
separador decimal perdido e longitude positiva.

## Resultado da primeira rodada (2026-09-08)

Recorte: dez corredores federais, painel de bins `(br, uf, km)` com jurisdição
federal e superfície `PAV`/`DUP` estáveis em 2022–2025, anos de análise
2017–2020 e 2022–2025. Foram **267.881 sinistros** atribuídos a bins do painel,
de 299.985 lidos (32.104 caíram fora da rede do painel).

### O defeito que a primeira execução escondeu

A primeira rodada somava **sinistros dos oito anos** contra **exposição só dos
anos com volume utilizável**. Onde a cobertura do VMDa é parcial, a taxa inflava
pelo fator da diferença. Medido: dos 28.404 km do painel, **74,4%** têm os oito
anos; **10,5%** têm quatro ou menos; **6,0%** têm um único ano.

O erro produziu dois clusters "alto-alto" que sobreviviam ao FDR e faziam
sentido narrativo — ambos em aproximação metropolitana. O que os derrubou foi
**aritmética inversa**: a exposição da BR-101/PE km 70–80 implicava **1.164
veículos/dia** na região metropolitana do Recife, o que é impossível. Alinhando
os anos, aquela faixa passa de 1.448 para **156 sinistros** (só 2017 tem
denominador) e o VMDa implícito vai a **9.310 veículos/dia** — plausível. Ela
deixa de sobreviver ao FDR.

⚠️ **Guarda permanente:** todo cluster alto-alto que sobrevive ao FDR reporta o
**VMDa médio implícito** (`exposição / (km × 365 × anos)`), e abaixo de 2.000
veículos/dia num corredor do top 10 sai marcado como suspeito. A conta que pegou
o erro virou verificação de rotina.

### O teste que separa risco de cobertura

A cobertura do VMDa **é fortemente autocorrelacionada no espaço** — medida como
`anos_utilizaveis` por faixa: **I = 0,780** (5 km), **0,661** (10 km), **0,431**
(20 km), todas com p = 0,0001. É **mais** autocorrelacionada que a própria taxa.

Isso significa que qualquer análise de taxa normalizada que não controle a
cobertura mede, em parte, a estrutura espacial do **programa de contagem**, não
do risco. É por isso que existe o recorte `anos_completos` (só faixas com os oito
anos), onde a cobertura é constante por construção.

### O que sobrevive ao controle

No recorte `anos_completos`, com 9.999 permutações:

| Faixa | n | I (Moran_Rate) | p |
|---|---|---|---|
| 5 km | 3.479 | **0,325** | 0,0001 |
| 10 km | 1.851 | **0,260** | 0,0001 |
| 20 km | 1.021 | **0,206** | 0,0002 |

A autocorrelação espacial da taxa por veículo-quilômetro é **positiva e
significativa** nos três tamanhos de faixa, e resiste ao ajuste bayesiano
empírico (a taxa bruta e a `Moran_Rate` não divergem em sinal nem em
significância em nenhuma das doze combinações rodadas). É mais fraca do que a
rodada desalinhada indicava: 0,260 contra 0,364 nas faixas de 10 km.

### O que NÃO sobrevive

**Nenhum cluster alto-alto passa a correção FDR** no recorte de referência
(10 km, `anos_completos`). Antes do FDR eram 70; depois, zero. Os clusters
baixo-baixo resistem melhor.

A leitura que os números sustentam é a distinção entre as duas coisas: **há
estrutura espacial global e não há picos locais isolados que resistam à
correção de multiplicidade**. A taxa varia de forma suave ao longo dos
corredores em vez de se concentrar em pontos destacáveis dos vizinhos.

⚠️ **O que NÃO se pode afirmar com esta rodada:** que existem hotspots de risco
identificados. Cluster que não sobrevive ao FDR não é hotspot fraco — é ruído
compatível com o acaso, dado o número de testes.

*(Para a investigação detalhada de por que o painel completo apresenta 3 clusters alto-alto pós-FDR a 10 km enquanto o painel balanceado apresenta zero, ver a seção [Decomposição da queda de HH no LISA, 10 km (2026-10-04)](#decomposição-da-queda-de-hh-no-lisa-10-km-2026-10-04) mais adiante).*

### Limitações desta rodada

- **Contiguidade só dentro de `(br, uf)`.** A quilometragem reinicia em cada
  estado, então o corredor se fragmenta na divisa: a BR-101 vira onze cadeias.
  Costurar as divisas exige a geometria do SNV, não o marco quilométrico.
  Ilhas por combinação: de 2 a 18, contadas e reportadas.
- **Cruzamento entre corredores não é vizinhança.** Onde duas BRs se cruzam, as
  faixas não são vizinhas neste desenho.
- **Sem AADT por sentido.** O VMDa separa crescente e decrescente; a análise
  soma os dois.
- **`p_sim` do Moran global não é bit-a-bit reprodutível** (a versão do `esda`
  em uso não aceita semente nesses estimadores; o LISA aceita e usa
  `seed=12345`). Com 9.999 permutações a significância a 5% não mudou entre
  execuções.

## Associação cobertura × taxa condicionada (2026-10-04)

### A pergunta (R2-01)

Item R2-01 do parecer 02 do trabalho `next-generation-road-safety`. O revisor
apontou que a associação negativa observada no Moran bivariado e na correlação
entre cobertura de monitoramento ($C = \text{anos\_utilizaveis}$) e taxa de
sinistros ($R$) nos corredores federais ($I_{BV} = -0,276$ a 10 km; $r = -0,392$)
possui duas explicações alternativas que não foram descartadas:

1. **Volume:** a cobertura de contagem acompanha o volume da rodovia e, como a
   relação entre sinistros e volume é sublinear (*safety in numbers*), a taxa por
   veículo-quilômetro tende a decrescer nos trechos mais movimentados mesmo sem
   viés de amostragem.
2. **Precisão amostral:** faixas monitoradas por menor número de anos acumulam
   menor exposição, resultando em estimativas de taxa com maior variância
   amostral e, consequentemente, valores mais extremos nos trechos de menor
   cobertura.

### Decisões metodológicas (amostra, variáveis e estimadores)

- **Amostra:** por tamanho de faixa (5 km, 10 km e 20 km), entram todas as faixas
  do painel com exposição positiva (`exposicao_veic_km > 0`), correspondendo
  estritamente ao recorte `sem_piso` de `bin/moran_corredores.py` (4.540 faixas a
  5 km, 2.329 a 10 km e 1.206 a 20 km).
- **Por que `anos_completos` e "número fixo de anos" não servem:** no recorte
  `anos_completos` (e em qualquer corte por número fixo de anos monitorados), a
  cobertura $C$ torna-se constante ($C = 8$), de modo que sua variância é nula
  ($\text{Var}(C) = 0$), tornando o Moran bivariado e a correlação de Pearson
  indefinidos por construção (divisão por zero).
- **Fórmula do AADT e sua aproximação:** o tráfego médio diário anual estimado
  de cada faixa é calculado por:
  $$\text{AADT\_medio} = \frac{\text{exposicao\_veic\_km}}{365 \times \text{km\_com\_exposicao} \times \text{anos\_utilizaveis}}$$
  e o controle de volume utiliza o logaritmo natural $\ln(\text{AADT\_medio})$. É
  uma aproximação porque trechos em que a extensão coberta variou entre os anos
  puxam o denominador para baixo, mas a transformação logarítmica amortece essa
  dispersão.
- **Estimador Bayesiano Empírico (EB):** para controlar a heterocedasticidade
  amostral decorrente de diferentes extensões e volumes de tráfego, calcula-se o
  estimador global de Marshall (1991, método dos momentos) por tamanho sobre toda
  a amostra:
  $$r_i = \frac{y_i}{e_i}, \quad m = \frac{\sum y_i}{\sum e_i}, \quad s^2 = \frac{\sum e_i (r_i - m)^2}{\sum e_i}, \quad \bar{e} = \frac{\sum e_i}{n}$$
  $$\phi = \max\left(0, s^2 - \frac{m}{\bar{e}}\right), \quad w_i = \frac{\phi}{\phi + m/e_i}, \quad \text{eb}_i = w_i r_i + (1 - w_i) m$$
  expressa como taxa suavizada por 100 milhões de veículo-km.
- **As três medidas e a ordem do Moran_BV:**
  - *Pearson ($r$):* correlação bivariada e parcial (resíduos OLS de $C$ e $R$
    sobre $\ln(\text{AADT})$), com p-valor analítico via teste $t$ de Student com
    $gl = n - 2 - k$ ($k = 0$ sem controle, $k = 1$ parcial).
  - *Spearman ($\rho$):* correlação sobre postos médios bivariada e parcial
    (parcial = correlação de Pearson entre os resíduos OLS dos postos de $C$ e de $R$
    sobre os postos de $\ln(\text{AADT})$), avaliando robustez à forte assimetria da taxa.
  - *Moran bivariado (`esda.Moran_BV`, 9.999 permutações):* calculado estritamente
    na ordem **(taxa, cobertura)**, idêntica à de `bin/moran_corredores.py`, com a
    mesma matriz de vizinhança linear contígua por `(br, uf)` padronizada em
    linhas (`transformation='r'`); no controle por volume, executado sobre os
    resíduos OLS de $R$ e $C$ sobre $\ln(\text{AADT})$.
- **Tercis de volume:** estratificação de $\text{AADT\_medio}$ em tercis
  calculados por tamanho via `statistics.quantiles(aadt, n=3)` (estrato 1: $\le q_1$;
  estrato 2: $(q_1, q_2]$; estrato 3: $> q_2$), avaliando a estabilidade da
  correlação dentro de classes homogêneas de fluxo. Não se calcula Moran_BV nos
  tercis porque a partição por volume rompe a contiguidade física linear dos
  corredores.

### Resultados da associação condicionada

Tabela por tamanho comparando a associação bivariada bruta, a parcial controlando
por $\ln(\text{AADT})$ bruta, a bivariada com taxa EB e a parcial com taxa EB,
copiada diretamente de `bases/prf-acidentes/resultados/associacao_condicionada_corredores.csv`:

| Faixa | n | Medida | Bivariada bruta | Parcial log(AADT) bruta | Bivariada EB | Parcial log(AADT) EB |
|---|---|---|---|---|---|---|
| 5 km | 4.540 | Pearson (r) | -0,362 (p = 7,17e-141) | -0,359 (p = 9,42e-138) | -0,377 (p = 1,01e-153) | -0,372 (p = 3,71e-149) |
| 5 km | 4.540 | Moran_BV (I) | -0,330 (p = 0,0001) | -0,322 (p = 0,0001) | -0,345 (p = 0,0001) | -0,336 (p = 0,0001) |
| 10 km | 2.329 | Pearson (r) | -0,392 (p = 1,79e-86) | -0,389 (p = 6,21e-85) | -0,396 (p = 2,46e-88) | -0,392 (p = 1,77e-86) |
| 10 km | 2.329 | Moran_BV (I) | -0,276 (p = 0,0001) | -0,267 (p = 0,0001) | -0,280 (p = 0,0001) | -0,270 (p = 0,0001) |
| 20 km | 1.206 | Pearson (r) | -0,367 (p = 1,12e-39) | -0,365 (p = 2,95e-39) | -0,369 (p = 3,39e-40) | -0,367 (p = 9,99e-40) |
| 20 km | 1.206 | Moran_BV (I) | -0,126 (p = 0,0005) | -0,120 (p = 0,0007) | -0,130 (p = 0,0004) | -0,124 (p = 0,0005) |

### Caminho da saída e reprodutibilidade

- **Caminho da saída versionada:** `bases/prf-acidentes/resultados/associacao_condicionada_corredores.csv`
  (acompanhado de `associacao_condicionada_corredores.prov.json`).
- **Comando para regerar:**
  ```bash
  ~/.venvs/geo/bin/python bin/associacao_corredores.py
  ```
- **Limitação do `p_sim`:** o estimador `esda.Moran_BV` não aceita semente na
  versão utilizada (`esda` 2.10.0), de modo que `p_sim` e `z_sim` variam
  ligeiramente entre execuções por simulação Monte Carlo (9.999 permutações).
  O coeficiente $I$ do Moran bivariado e todas as correlações de Pearson e
  Spearman são estritamente determinísticos.

### Veredito

O veredito, pelo critério pré-registrado, está em `bases/prf-acidentes/ACHADOS.md`
(entrada de 2026-10-04). Este documento registra só o método e a tabela.

### Limite do controle de precisão (medido em 2026-10-04)

O EB global de Marshall quase não encolhe a taxa neste painel: a exposição de cada
faixa é grande demais diante da variância entre faixas. O peso $w_i$ medido tem
mediana 0,980 a 5 km, 0,990 a 10 km e 0,995 a 20 km, mínimo 0,586 / 0,724 / 0,832,
e nenhuma faixa com $w_i < 0,5$. Logo $\text{eb}_i \approx r_i$, e a coluna EB **não
testa** a explicação (b) — precisão amostral ligada ao número de anos monitorados.
Essa explicação segue em aberto (ver o teste direto dessa hipótese por estratificação
e ponderação na seção [Precisão amostral por classe de cobertura (2026-10-04)](#precisão-amostral-por-classe-de-cobertura-2026-10-04) a seguir).

## Precisão amostral por classe de cobertura (2026-10-04)

### A pergunta (R2-01 b e o limite do controle EB)

Item R2-01 (b) do parecer 02 do trabalho `next-generation-road-safety`. O revisor
apontou que faixas monitoradas por menor número de anos acumulam menor exposição,
resultando em estimativas de taxa de sinistros com maior variância amostral e,
consequentemente, valores mais extremos nos trechos de menor cobertura, o que
poderia produzir espuriamente a associação negativa com a cobertura
($C = \text{anos\_utilizaveis}$).

O controle via estimador Bayesiano Empírico (EB global de Marshall) avaliado na
seção anterior **não testou** essa hipótese: como demonstrado em
[Limite do controle de precisão](#limite-do-controle-de-precisão-medido-em-2026-10-04),
o peso de encolhimento $w_i$ tem mediana entre 0,980 e 0,995 (exposição muito alta
diante da variância entre faixas), de modo que $\text{eb}_i \approx r_i$. Esta seção
testa a hipótese diretamente, investigando se a dispersão das taxas efetivamente
decresce com a cobertura temporal e se a correlação negativa $C \times R$
permanece sob estratificação homogênea e ponderação pela exposição.

### Decisões metodológicas (amostra, estratos e estimadores)

- **Amostra e taxa analisada:** por tamanho de agregação (5 km, 10 km e 20 km), a
  amostra é idêntica ao recorte `sem_piso` (faixas com $\text{exposicao\_veic\_km} > 0$),
  totalizando 4.540 faixas a 5 km, 2.329 a 10 km e 1.206 a 20 km. A taxa
  analisada é a taxa bruta ($\text{taxa\_por\_100M\_veic\_km}$), dado que a taxa EB
  coincide numericamente com ela na precisão relevante.
- **Classes de cobertura e distribuição observada:** as faixas são estratificadas em
  três classes temporais: `anos_1_3` (1 a 3 anos utilizáveis), `anos_4_6` (4 a 6 anos)
  e `anos_7_9` (7 a 9 anos). O **máximo observado é 8 anos** — nenhuma faixa no
  painel possui 9 anos utilizáveis. A distribuição empírica de $C$ por tamanho é:

| Faixa | 1 ano | 2 anos | 3 anos | 4 anos | 5 anos | 6 anos | 7 anos | 8 anos | Total |
|---|---|---|---|---|---|---|---|---|---|
| 5 km | 83 | 18 | 19 | 110 | 236 | 127 | 468 | 3.479 | 4.540 |
| 10 km | 37 | 7 | 10 | 48 | 106 | 50 | 220 | 1.851 | 2.329 |
| 20 km | 16 | 2 | 4 | 20 | 36 | 20 | 87 | 1.021 | 1.206 |

- **Baixo poder amostral em estratos extremos:**
  - Na classe `anos_7_9`, a variável $C$ assume apenas os valores 7 ou 8, com cerca
    de 88% das faixas concentradas exatamente em $C = 8$ (3.479 de 3.947 a 5 km;
    1.851 de 2.071 a 10 km; 1.021 de 1.108 a 20 km). A variabilidade interna de $C$
    é quase nula, conferindo baixo poder estatístico por construção para testes de
    associação intra-classe.
  - Na escala de 20 km, a classe `anos_1_3` possui apenas $n = 22$ faixas (16 com 1
    ano, 2 com 2 anos e 4 com 3 anos), resultando igualmente em reduzido poder
    amostral.
- **Medidas de dispersão e variância de Poisson esperada:**
  - Para cada estrato calculam-se a variância amostral ($s^2$, com divisor $n - 1$)
    e a distância interquartil ($\text{DIQ} = Q_3 - Q_1$, via método padrão de
    quartis da stdlib).
  - Sob hipótese nula de que a variação decorre puramente de contagem de Poisson com
    taxa comum do estrato $M = 10^8 \times \sum y_i / \sum e_i$, a variância teórica
    individual é $\text{Var}(r_i) = 10^8 \times M / e_i$. A variância de Poisson
    esperada do estrato é a média dessas variâncias individuais:
    $$\text{Var}_{\text{Poisson}} = \frac{1}{n} \sum_{i=1}^n \frac{10^8 \times M}{e_i}$$
  - A razão entre a variância observada e a esperada sob Poisson
    ($\text{Razão} = s^2 / \text{Var}_{\text{Poisson}}$) mensura quanto da dispersão
    excede o ruído amostral de contagem. Uma razão próxima de 1 indicaria
    predomínio do ruído estocástico; razões substancialmente superiores a 1
    indicam heterogeneidade espacial real entre os trechos.
- **Testes de homogeneidade de dispersão e gradiente (estrato `todos`):**
  - *Brown-Forsythe classes (`brown_forsythe_classes`):* teste de Levene centrado
    na mediana de cada uma das 3 classes ($gl_1 = 2$, $gl_2 = n - 3$), robusto a
    distribuições fortemente assimétricas.
  - *Brown-Forsythe anos (`brown_forsythe_anos`):* o mesmo teste aplicado entre os
    8 valores individuais de anos utilizáveis ($gl_1 = 7$, $gl_2 = n - 8$).
  - *Spearman do desvio absoluto (`spearman_c_desvio_abs`):* correlação de postos
    entre a cobertura $C$ e o desvio absoluto da taxa em relação à mediana global do
    tamanho ($|r_i - \text{mediana}(r)|$), com significância via teste $t$ de
    Student ($gl = n - 2$). Um coeficiente negativo e estatisticamente significante
    indica que trechos com mais anos de contagem apresentam desvios menores em torno
    da mediana.
- **Associação cobertura $\times$ taxa e Pearson ponderado:**
  - Dentro de cada classe e no total (`todos`), calculam-se as correlações bivariadas
    de Pearson ($r$) e postos médios de Spearman ($\rho$).
  - No agregado (`todos`), calcula-se a correlação linear de Pearson ponderada
    (`pearson_ponderado`) com pesos $w_i = e_i$ ($\text{exposicao\_veic\_km}$). Como
    a variância de amostragem individual sob Poisson é proporcional a $1/e_i$, o
    peso $w_i \propto 1/\text{Var}(r_i)$ compensa a imprecisão das estimativas de
    baixa exposição.
  - A inferência estatística do Pearson ponderado utiliza o teste $t$ de Student
    adotando como aproximação analítica o tamanho amostral efetivo de Kish
    ($n_{\text{eff}} = \lfloor (\sum w_i)^2 / \sum w_i^2 \rfloor$, com
    $gl = n_{\text{eff}} - 2$), controlando a inflação espúria dos graus de liberdade
    gerada pela concentração de pesos.

### Resultados de dispersão e associação

A tabela a seguir apresenta os resultados compilados por tamanho de faixa e classe
de cobertura, com valores extraídos diretamente de
`bases/prf-acidentes/resultados/precisao_amostral_corredores.csv` (arredondados em até
3 casas decimais; $p < 0,001$ quando inferior a $10^{-3}$):

| Faixa | Classe / Estrato | n | Variância | DIQ | Razão Var Obs/Esp | Pearson (p) | Spearman (p) | Pearson pond. (p) | BF classes (F, p) | BF anos (F, p) | Spearman desvio abs (r, p) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 km | 1–3 anos | 120 | 390.584,086 | 384,284 | 202,504 | -0,077 (p = 0,402) | -0,201 (p = 0,028) | — | — | — | — |
| 5 km | 4–6 anos | 473 | 28.700,536 | 76,542 | 82,646 | 0,050 (p = 0,274) | 0,070 (p = 0,129) | — | — | — | — |
| 5 km | 7–9 anos | 3.947 | 3.203,522 | 30,890 | 34,628 | -0,083 (p < 0,001) | -0,043 (p = 0,008) | — | — | — | — |
| 5 km | Todos | 4.540 | — | — | — | -0,362 (p < 0,001) | -0,143 (p < 0,001) | -0,279 (p < 0,001) | 406,152 (p < 0,001) | 115,602 (p < 0,001) | -0,224 (p < 0,001) |
| 10 km | 1–3 anos | 54 | 253.720,934 | 477,943 | 209,109 | -0,172 (p = 0,213) | -0,172 (p = 0,213) | — | — | — | — |
| 10 km | 4–6 anos | 204 | 105.082,078 | 76,974 | 404,050 | -0,055 (p = 0,432) | 0,054 (p = 0,443) | — | — | — | — |
| 10 km | 7–9 anos | 2.071 | 3.428,682 | 31,832 | 64,424 | -0,070 (p = 0,001) | -0,035 (p = 0,112) | — | — | — | — |
| 10 km | Todos | 2.329 | — | — | — | -0,392 (p < 0,001) | -0,108 (p < 0,001) | -0,275 (p < 0,001) | 202,726 (p < 0,001) | 58,738 (p < 0,001) | -0,214 (p < 0,001) |
| 20 km | 1–3 anos | 22 | 548.514,600 | 621,566 | 535,355 | 0,259 (p = 0,244) | 0,248 (p = 0,267) | — | — | — | — |
| 20 km | 4–6 anos | 76 | 328.562,082 | 82,493 | 1.587,007 | -0,099 (p = 0,395) | 0,026 (p = 0,823) | — | — | — | — |
| 20 km | 7–9 anos | 1.108 | 4.392,665 | 33,287 | 129,569 | -0,063 (p = 0,037) | -0,020 (p = 0,517) | — | — | — | — |
| 20 km | Todos | 1.206 | — | — | — | -0,367 (p < 0,001) | -0,061 (p = 0,034) | -0,246 (p < 0,001) | 93,800 (p < 0,001) | 37,066 (p < 0,001) | -0,205 (p < 0,001) |

*Notas sobre graus de liberdade dos testes de Brown-Forsythe:*
- 5 km: classes $gl = 2, 4.537$; anos $gl = 7, 4.532$.
- 10 km: classes $gl = 2, 2.326$; anos $gl = 7, 2.321$.
- 20 km: classes $gl = 2, 1.203$; anos $gl = 7, 1.198$.

### Caminho da saída e reprodutibilidade

- **Caminho da saída versionada:** `bases/prf-acidentes/resultados/precisao_amostral_corredores.csv`
  (acompanhado de `precisao_amostral_corredores.prov.json`).
- **Comando para regerar:**
  ```bash
  ~/.venvs/geo/bin/python bin/precisao_corredores.py
  ```
- **Determinismo:** todos os estimadores, testes $t$, testes de Brown-Forsythe e
  estatísticas de Kish são puramente determinísticos e reprodutíveis bit a bit
  (sem simulação Monte Carlo).

### Veredito

O veredito sobre a hipótese de precisão amostral, avaliado conforme o critério
pré-registrado, está documentado em `bases/prf-acidentes/ACHADOS.md` (entrada de
2026-10-04). Este documento registra exclusivamente o método, as decisões
metodológicas e as tabelas com os dados observados.

## Decomposição da queda de HH no LISA, 10 km (2026-10-04)

### A pergunta do Orientador

No âmbito do trabalho `next-generation-road-safety` (sci-team), o Orientador formulou
questão sobre a divergência observada na análise espacial local de clusters: no LISA
(`esda.Moran_Local_Rate`, 9.999 permutações, `seed=12345`, taxa por 100 milhões de
veículo-km, controle de FDR a 5%) das faixas de 10 km dos dez corredores federais,
o painel completo (`sem_piso`, $n = 2.329$) apresenta **3** clusters alto-alto (HH)
que sobrevivem ao FDR, enquanto o painel balanceado (`anos_completos`, $n = 1.851$)
apresenta **0** clusters HH.

A investigação desdobra-se em duas partes:
1. Quanto dessa queda decorre **(a) da exclusão dos 478 bins** sem os 8 anos completos de contagem e quanto decorre **(b) da cobertura incompleta** no próprio bin;
2. Onde estão localizados (BR, UF, km inicial e final) os 3 bins sobreviventes em C1, e qual o **VMDa médio implícito** de cada um.

### Os quatro cenários

Todos os cenários avaliam faixas de 10 km dos dez corredores federais com
exposição positiva (`exposicao_veic_km > 0`):

- **C1 `completo`**: amostra completa `sem_piso` ($n = 2.329$), matriz de contiguidade
  linear $W$ construída sobre os 2.329 bins (contiguidade dentro de cada par `(br, uf)`),
  controle de FDR aplicado sobre os $m = 2.329$ p-valores. Reproduz a linha de
  referência do painel completo (96 HH antes, 3 HH pós-FDR).
- **C2 `completo_so_balanceados_fdr_completo`**: utiliza exatamente o mesmo objeto
  LISA e o mesmo ponto de corte FDR calculados em C1, contabilizando apenas os bins
  que possuem os 8 anos completos de monitoramento (`anos_utilizaveis == 8`,
  $n = 1.851$). Isola o efeito de o próprio bin ter ou não cobertura completa,
  mantendo a matriz de vizinhança $W$ e o limiar de multiplicidade originais de C1.
- **C3 `completo_restrito_1851`**: utiliza o mesmo objeto LISA de C1 (estatística
  local e p-valores simulados a partir da matriz $W$ e taxa de referência completas
  de 2.329 bins), porém restrito aos 1.851 bins balanceados, com o corte de FDR
  recalculado exclusivamente sobre esses 1.851 p-valores ($m = 1.851$).
- **C4 `balanceado`**: amostra balanceada `anos_completos` ($n = 1.851$), matriz de
  contiguidade linear $W$ reconstruída exclusivamente sobre os 1.851 bins, e corte FDR
  recalculado com $m = 1.851$. Reproduz a linha de referência do painel balanceado
  (70 HH antes, 0 HH pós-FDR).

### Decomposição sequencial da queda de HH e arbitrariedade da ordem

A queda de clusters alto-alto pós-FDR entre C1 e C4 é decomposta sequencialmente de
forma aditiva:
$$\text{queda\_total} = \text{HH}(C1) - \text{HH}(C4)$$
$$\text{efeito\_cobertura\_do\_bin} = \text{HH}(C1) - \text{HH}(C2)$$
$$\text{efeito\_multiplicidade} = \text{HH}(C2) - \text{HH}(C3)$$
$$\text{efeito\_vizinhanca} = \text{HH}(C3) - \text{HH}(C4)$$
com a identidade exata:
$$\text{efeito\_cobertura\_do\_bin} + \text{efeito\_multiplicidade} + \text{efeito\_vizinhanca} \equiv \text{queda\_total}$$

Mapeamento para os termos da pergunta do Orientador:
- O termo **(b) cobertura incompleta do próprio bin** corresponde a `efeito_cobertura_do_bin` (sobreviventes em C1 que são eliminados em C2 por não terem 8 anos monitorados).
- O termo **(a) exclusão dos 478 bins** corresponde à soma `efeito_multiplicidade + efeito_vizinhanca`.

⚠️ **A ordem da decomposição sequencial é uma escolha metodológica:**
A decomposição sequencial de termos interdependentes não é matematicamente única. A
ordem fixada ($C1 \to C2 \to C3 \to C4$) afere primeiramente a cobertura do próprio bin
antes de avaliar o afrouxamento do corte de FDR decorrente de testar menos hipóteses
($m = 2.329 \to 1.851$) e a reestruturação da matriz de contiguidade linear $W$ e da
taxa global de referência. Uma sequência distinta (por exemplo, recalcular primeiro o FDR
ou a matriz $W$) poderia alterar os valores atribuídos à multiplicidade e à vizinhança.
A sequência adotada reflete a prioridade substantiva de isolar a suficiência do próprio bin
diante dos efeitos de rede e multiplicidade.

### Sensibilidade à semente

O p-valor empírico do LISA (`p_sim`) provém de simulação de Monte Carlo por permutações
aleatórias condicionadas (9.999 permutações). Bins com valores de pseudo-$p$ muito
próximos ao limiar de significância de Benjamini-Hochberg podem alternar sua condição
pós-FDR entre realizações estocásticas com sementes distintas.

Para verificar a sensibilidade dos resultados diante da semente, além da semente
pré-registrada de referência (**12345**), os quatro cenários e a decomposição foram
recalculados em quatro sementes adicionais (**1, 2, 3 e 4**).

### Tabelas de cenários e de decomposição (semente 12345)

Os valores a seguir foram copiados diretamente de
`bases/prf-acidentes/resultados/lisa_decomposicao_queda_hh.csv`:

#### 1. Contagens dos quatro cenários na semente 12345

| Cenário | n | Testes FDR (m) | Ilhas | Corte FDR | HH antes | BB antes | AB antes | BA antes | HH pós-FDR | BB pós-FDR | AB pós-FDR | BA pós-FDR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C1: completo | 2.329 | 2.329 | 2 | 0,000451 | 96 | 267 | 1 | 13 | 3 | 17 | 1 | 0 |
| C2: compl. só balanceados (FDR compl.) | 1.851 | 2.329 | 2 | 0,000451 | 29 | 211 | 0 | 8 | 0 | 17 | 0 | 0 |
| C3: compl. restrito 1.851 | 1.851 | 1.851 | 2 | 0,000459 | 29 | 211 | 0 | 8 | 0 | 17 | 0 | 0 |
| C4: balanceado | 1.851 | 1.851 | 18 | 0,001432 | 70 | 202 | 15 | 13 | 0 | 38 | 14 | 1 |

*Cortes exatos de FDR na semente 12345: C1 e C2 = 0,00045083726921425505; C3 = 0,00045921123716909784; C4 = 0,0014316585629389521.*

#### 2. Decomposição da semente 12345 e sensibilidade à semente

| Semente | HH C1 | HH C2 | HH C3 | HH C4 | Cobertura do bin (C1 - C2) | Multiplicidade (C2 - C3) | Vizinhança (C3 - C4) | Queda total (C1 - C4) |
|---|---|---|---|---|---|---|---|---|
| **12345 (ref.)** | **3** | **0** | **0** | **0** | **3** | **0** | **0** | **3** |
| 1 | 1 | 0 | 0 | 1 | 1 | 0 | -1 | 0 |
| 2 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 2 |
| 3 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 |
| 4 | 2 | 0 | 0 | 0 | 2 | 0 | 0 | 2 |

### Bins sobreviventes em C1 (semente 12345)

Os três bins que configuram clusters alto-alto (HH) pós-FDR no cenário completo C1 na
semente 12345, com todos os atributos copiados diretamente do CSV (`bloco=hh_sobrevivente`):

| BR | UF | km inicial | km final | Anos utiliz. | Anos com dados | Balanceado? | Sinistros | Exposição (veic-km) | km com exp. | Taxa (por 100M veic-km) | p_sim | Corte FDR (C1) | Sig. FDR (C1) | VMDa implícito (10 km) | VMDa implícito (km exp.) | VMDa suspeito (<2.000) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 364 | AC | 110 | 120 | 3 | 2018; 2024; 2025 | Não | 39 | 20.550.339,50 | 10,0 | 189,78 | 0,0004 | 0,000451 | Sim | 1.876,7 | 1.876,7 | Sim |
| 364 | AC | 120 | 130 | 4 | 2017; 2018; 2024; 2025 | Não | 296 | 8.289.905,55 | 9,0 | 3.570,61 | 0,0003 | 0,000451 | Sim | 567,8 | 630,9 | Sim |
| 364 | AC | 130 | 140 | 1 | 2017 | Não | 104 | 5.327.054,55 | 8,0 | 1.952,30 | 0,0001 | 0,000451 | Sim | 1.459,5 | 1.824,3 | Sim |

*Comportamento dos sobreviventes nos cenários C2, C3 e C4:*
- **C2 e C3:** os três bins não são contabilizados como clusters HH porque nenhum deles possui os 8 anos monitorados (`pertence_balanceado = False`). Em C3, embora seus valores individuais de `p_sim` permaneçam inferiores ao limiar recalculado (0,000459), eles não participam do conjunto restrito aos balanceados.
- **C4:** não pertencem à amostra balanceada e, portanto, não entram na análise.
- **Guarda de VMDa suspeito:** os três bins apresentam VMDa médio implícito abaixo de 2.000 veículos/dia (tanto na extensão nominal de 10 km quanto na extensão efetiva com exposição `km_com_exposicao`), disparando a guarda permanente de tráfego implícito suspeito documentada neste método.

### Caminho da saída e reprodutibilidade

- **Caminho da saída versionada:** `bases/prf-acidentes/resultados/lisa_decomposicao_queda_hh.csv`
  (acompanhado de `lisa_decomposicao_queda_hh.prov.json`).
- **Comando para regerar:**
  ```bash
  ~/.venvs/geo/bin/python bin/lisa_decomposicao_hh.py
  ```
- **Reprodutibilidade:** a execução com as sementes declaradas é estritamente
  determinística e gera saída com SHA-256 verificado por teste automatizado.

### Veredito

O veredito sobre a pergunta do Orientador e a leitura substantiva da decomposição,
avaliados conforme o critério pré-registrado na Decisão 6 do plano de trabalho, estão
documentados em `bases/prf-acidentes/ACHADOS.md` (entrada de 2026-10-04). Este
documento registra exclusivamente o método, as decisões de desenho e as tabelas com os
números observados.

## Para onde este trabalho vai

Esta análise é o **dado empírico** do trabalho científico conduzido no funil
`next-generation-road-safety` do repo `sci-team`, cujo veículo-alvo é a
Collection **next2026** (*Next-Generation Road Safety: Human Factors, Smart
Infrastructure and Artificial Intelligence*, Discover Civil Engineering), que
lista "Geospatial Analytics" entre as palavras-chave declaradas.

A revisão sistemática desse trabalho já existe e é vizinha desta análise: 200
registros identificados, 54 incluídos, em
`~/projects/sci-team/data/trabalhos/next-generation-road-safety/revisao/`
(rodada em 2026-09-07). O corpus dela é de análise espaço-temporal de hotspots,
autocorrelação espacial e delimitação de hot zones — os mesmos métodos desta
análise. As duas frentes se encontram no mesmo trabalho.

⚠️ **Número desta análise que entrar no artigo passa por `./dados citar`, nunca
por `afirmar`.** A interface do sci-team com este repo é `citar` (referência em
LaTeX e figura com `--perfil artigo`), não o `afirmar` do LinkedIn e do blog —
está na §5.30 do `GEMINI.md` do sci-team e na §7 do `~/.hermes/MAPA.md`.

Tópico do Discord onde o trabalho é conduzido: **#sci-team → "Next-Generation
Road Safety"** (`1545607868307218526`).

R2-01 é respondido por esta saída, presa por commit.

## O que ainda está aberto

- **Denominador final**: veículo-quilômetro (VMDa × extensão × dias) é o alvo,
  mas falta decidir se o ano parcial de 2026 entra (a PRF tem 2026; o VMDa
  não vai além de 2025).
- **Faixas sem sinistro nenhum**: numa malha de 10 km haverá faixas com zero.
  Zero sinistro com exposição alta é informação; zero com exposição quase nula é
  ruído. Falta o critério de exposição mínima para a faixa entrar.
- **Sentido da via**: o VMDa separa crescente e decrescente; a PRF registra
  sentido, mas a junção atual soma os dois. Se a análise for por sentido, a
  unidade dobra.
- **Formato de versionamento da geometria**: continua em aberto no `GEMINI.md`
  (GeoJSON × CSV+WKT) para geometria que seja fonte de verdade.
- **Costura das divisas estaduais**: a chave é `(br, uf, km)` porque o marco
  quilométrico reinicia em cada estado, e a vizinhança é construída dentro de
  `(br, uf)`. O efeito colateral é que a BR-101 são onze cadeias separadas e
  nenhum par de faixas vizinhas cruza divisa. Costurar exige a geometria do SNV,
  não só o marco.

### Fechado desde a primeira redação

- **Ingestão nacional da PRF** (2026-09-08): feita. `geo.prf_acidentes_corredores`
  tem **334.267** ocorrências dos dez corredores no país inteiro, 2017–2025,
  contra as **88.859** de `geo.prf_acidentes_mg`, que continua intacta. A
  estimativa de ~600 mil, feita antes da ingestão, era alta: ela contava o
  corredor inteiro, e só entra o que a leitura consegue atribuir às BRs do
  recorte.
- **Regra de estabilidade de jurisdição** (2026-09-08): decidida *e* aplicada. A
  rede é definida por jurisdição federal e superfície `PAV`/`DUP` estáveis em
  2022–2025, projetada retroativamente sobre 2017–2020 (ver "O painel"), e está
  implementada em `bin/painel_corredores.py` (`SUPERFICIES_PAINEL` e a
  construção da rede). O recorte sem inferência (4.502 bins) fica como
  sensibilidade.
