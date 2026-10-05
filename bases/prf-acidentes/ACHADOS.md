# Achados — PRF / Acidentes em Rodovias Federais (Agrupados por Ocorrência)

Histórico de achados sobre esta base, com data. **Leitura obrigatória antes de usar esta base para qualquer novo recorte ou comparação entre anos.**

---

## 2026-09-06 — Concentração de 89,8% da queda bruta de acidentes na classe sem vítima entre 2011 e 2025

A queda de 62,3% nos acidentes registrados pela Polícia Rodoviária Federal entre 2011 e 2025 (de 192.326 para 72.529 ocorrências) é em 89,8% explicada pela redução em uma única classe: registros Sem Vítimas.

O registro de acidentes Sem Vítimas desabou 90,6% no período (de 118.745 em 2011 para 11.138 em 2025), reduzindo sua participação de 61,7% para 15,4% dos registros totais da PRF. Em contrapartida, a série harmonizada comparável de acidentes com vítima (feridos ou mortos) caiu 15,2% no mesmo intervalo (de 72.416 em 2011 para 61.390 em 2025).

---

## 2026-09-06 — Prova do caráter administrativo da queda de registros em jun-jul/2015 e mar-abr/2018

A apuração comprova que o colapso nos registros de acidentes sem vítima decorre de mudanças administrativas de procedimento da PRF, evidenciadas por dois degraus concentrados em único mês:

1. **Junho para julho de 2015:** O total mensal de acidentes caiu 19,6% (de 10.681 para 8.592 registros), enquanto os acidentes com vítima variaram apenas −4,9% e as mortes subiram (de 528 para 564 óbitos).
2. **Março para abril de 2018:** O total mensal caiu 17,3% (de 6.684 para 5.530 registros), enquanto os acidentes com vítima variaram −3,7% e as mortes subiram (de 426 para 439 óbitos).

A natureza nacional e institucional dessas rupturas é demonstrada pela uniformidade espacial: as 23 UFs com mais acidentes em 2014 perderam mais de metade dos registros sem vítima até 2019, com queda mediana de 86,9%.

---

## 2026-09-06 — Reversão da tendência a partir de 2018 contraria narrativa de melhora contínua

O ano de 2018 representou o piso histórico dos registros da série comparável. Entre 2018 e 2025, os acidentes com vítima voltaram a subir 13,5% (de 54.079 para 61.390 ocorrências).

No mesmo período de 2018 a 2025:
- Os acidentes fatais subiram 15,6% (de 4.508 para 5.209);
- As mortes aumentaram 14,6% (de 5.274 para 6.043 mortos);
- Os feridos cresceram 8,9% (de 76.695 para 83.550 feridos).

Enquanto o registro sem vítima continuou caindo por razões administrativas, os indicadores de gravidade inverteram a trajetória. A redação jornalística e analítica é obrigatoriamente "voltou a subir desde 2018", sendo falso afirmar que "está no pior nível da série", já que a gravidade em 2011 era substancialmente maior.

---

## 2026-09-06 — Descontinuidade e inoperância de séries longas para causa e tipo de acidente a partir de 2017

Com a transição para o sistema BAT em 2017, as taxonomias de causa e tipo de acidente sofreram rupturas estruturais sem tabela de correspondência fornecida pela fonte:

- A variável causa_acidente contava com 11 rótulos até 2016, saltou para 24 em 2017 e atingiu 75 em 2023;
- A variável tipo_acidente tinha 16 rótulos em 2016; em 2017, 10 deles desaparecem, substituídos por renomeações em bloco (`Atropelamento de pessoa` → `Atropelamento de Pedestre`, `Colisão com objeto fixo` → `Colisão com objeto estático`) e por rótulos novos (`Engavetamento`), deixando o vocabulário em 17 — e em 2024 entra `Sinistro pessoal de trânsito`.

Nenhuma das duas taxonomias é publicável em série longa comparável sem harmonização que a PRF não disponibiliza.

---

## 2026-09-06 — Incompatibilidades técnicas de leiaute, datas, identificadores e codificação nas 20 safras

A extração unificada dos arquivos brutos enfrentou as seguintes pegadinhas de leitura:

- **Leiaute de colunas:** Três estruturas distintas (26 colunas até 2015, 25 colunas em 2016 com a remoção da coluna ano, e 30 colunas de 2017 em diante);
- **Formatos de data:** Três notações distintas, com o formato `dd/mm/aa` exclusivo da safra 2016;
- **Formatação de arquivos:** Codificação latin-1 com delimitador ponto e vírgula e CRLF em todas as safras, e aspas duplas em campos de texto apenas a partir de 2012;
- **Identificadores e nulos:** O campo id possuía repetições de registro até 2016 (com 1 id repetido em 2016) e zero repetições a partir de 2017. Além disso, o rótulo de classificação nula `Ignorado` virou `NA` em 2017;
- **Distribuição:** Arquivos distribuídos por Google Drive com IDs de arquivo instáveis a cada republicação mensal da PRF.

---

## 2026-09-06 — Incomparabilidade direta entre a base federal da PRF e as bases municipais de trânsito

Embora a base da PRF e as bases municipais (como a família `pbh-acidentes-*`) meçam acidentes de trânsito, os dados não se somam nem se comparam em nível absoluto:

- A base da PRF cobre exclusivamente a malha rodoviária federal sob jurisdição e policiamento da Polícia Rodoviária Federal ao longo de 20 safras anuais.
- A família de bases de Belo Horizonte (`pbh-acidentes-*`) atém-se à malha viária urbana municipal e limita-se a acidentes com vítima por construção metodológica.

---

## 2026-10-04 — Associação negativa C × R sobrevive ao controle de volume com atenuação; controle de precisão (EB) quase não encolhe a taxa e não testa a hipótese; Spearman e tercis divergem de Pearson

Avaliação da robustez da associação negativa entre cobertura de contagens de tráfego ($C$) e taxa de sinistros da PRF ($R$) nos dez principais corredores rodoviários federais (2017–2025), a partir dos dados consolidados em `bases/prf-acidentes/resultados/associacao_condicionada_corredores.csv`.

### Critério de decisão pré-registrado

Para cada tamanho de agregação espacial (5 km, 10 km e 20 km), a associação C × R:
- **sobrevive** a um controle se o coeficiente controlado tem o **mesmo sinal** do bivariado bruto **e** apresenta $p < 0,05$ (Pearson: `p_valor`; Moran_BV: `p_sim`);
- **atenua** se sobrevive com magnitude ($|\text{coeficiente}|$) menor que a do bivariado bruto;
- **não sobrevive** caso contrário.

### Veredito dos três controles avaliados

1. **Controle de volume (`bruta/log_aadt`):**
   - Em 5 km ($n = 4.540$): Pearson passa de -0,362 ($p < 0,001$) para -0,359 ($p < 0,001$); Moran_BV passa de -0,330 ($p = 0,0001$) para -0,322 ($p = 0,0001$). Veredito: **atenua** em ambas as medidas.
   - Em 10 km ($n = 2.329$): Pearson passa de -0,392 ($p < 0,001$) para -0,389 ($p < 0,001$); Moran_BV passa de -0,276 ($p = 0,0001$) para -0,267 ($p = 0,0001$). Veredito: **atenua** em ambas as medidas.
   - Em 20 km ($n = 1.206$): Pearson passa de -0,367 ($p < 0,001$) para -0,365 ($p < 0,001$); Moran_BV passa de -0,126 ($p = 0,0005$) para -0,120 ($p = 0,0007$). Veredito: **atenua** em ambas as medidas.
   - **Veredito geral do controle de volume:** a associação negativa **sobrevive com atenuação** nos três tamanhos tanto para Pearson quanto para Moran_BV.

2. **Controle de precisão (`eb/nenhum`):**
   - Em 5 km: Pearson passa a -0,377 ($p < 0,001$); Moran_BV passa a -0,345 ($p = 0,0001$). Veredito: **sobrevive** sem atenuação.
   - Em 10 km: Pearson passa a -0,396 ($p < 0,001$); Moran_BV passa a -0,280 ($p = 0,0001$). Veredito: **sobrevive** sem atenuação.
   - Em 20 km: Pearson passa a -0,369 ($p < 0,001$); Moran_BV passa a -0,130 ($p = 0,0004$). Veredito: **sobrevive** sem atenuação.
   - **Veredito geral do controle de precisão:** a associação negativa **sobrevive** nos três tamanhos para ambas as medidas, sem atenuação.

   ⚠️ **Este controle tem pouco poder.** O peso EB $w_i$ tem mediana 0,980 (5 km), 0,990 (10 km) e 0,995 (20 km), e nenhuma faixa tem $w_i < 0,5$: a taxa EB é praticamente a bruta. Sobreviver a ele **não descarta** a explicação de precisão amostral (R2-01, item b), que segue em aberto (ver `METODO-ESPACIAL.md`, "Limite do controle de precisão").

3. **Controle conjunto de volume e precisão (`eb/log_aadt`):**
   - Em 5 km: Pearson é -0,372 ($p < 0,001$) e Moran_BV é -0,336 ($p = 0,0001$). Frente ao bivariado bruto (-0,362 e -0,330), ambas as medidas **sobrevivem** sem atenuação.
   - Em 10 km: Pearson é -0,392 ($p < 0,001$, exato -0,3922 vs -0,3921), **sobrevive** sem atenuação; Moran_BV é -0,270 ($p = 0,0001$ vs -0,276), **atenua**.
   - Em 20 km: Pearson é -0,367 ($p < 0,001$, exato -0,3670 vs -0,3666), **sobrevive** sem atenuação; Moran_BV é -0,124 ($p = 0,0005$ vs -0,126), **atenua**.
   - **Veredito geral do controle conjunto:** o veredito **varia entre medidas**. Pearson sobrevive sem atenuação nos três tamanhos (em 10 km e 20 km praticamente inalterado frente ao bivariado bruto, divergindo apenas na quarta casa decimal), enquanto Moran_BV sobrevive sem atenuação em 5 km e atenua em 10 km e 20 km.

### Concordância de Spearman e dos tercis com Pearson

- **Correlação de Spearman:**
  - Em 5 km e 10 km, Spearman **concorda** com Pearson: a correlação bivariada bruta é negativa e significativa (5 km: -0,143, $p < 0,001$; 10 km: -0,108, $p < 0,001$) e sobrevive com atenuação ao controle de volume (5 km: -0,113, $p < 0,001$; 10 km: -0,082, $p < 0,001$) e sob controle conjunto (5 km: -0,126; 10 km: -0,090).
  - Em 20 km, Spearman **discorda** de Pearson: embora o bivariado bruto seja negativo e significativo (-0,061, $p = 0,034$), Spearman **não sobrevive** ao controle de volume (`bruta/log_aadt`: -0,044, $p = 0,128$) nem ao controle conjunto (`eb/log_aadt`: -0,050, $p = 0,082$), perdendo a significância estatística ($p \ge 0,05$).
  - Portanto, o veredito de Spearman **varia conforme o tamanho da faixa**, não sustentando a associação condicionada na escala de 20 km.

- **Tercis de volume (`log_aadt`):**
  - Para Pearson, a correlação permanece negativa e altamente significativa em todos os tercis e nos três tamanhos (todos com $p < 0,001$), com magnitude maior nos tercis 2 e 3 que no tercil 1 (a 20 km o tercil 2 supera o 3):
    - 5 km: Tercil 1 (-0,280), Tercil 2 (-0,367), Tercil 3 (-0,524).
    - 10 km: Tercil 1 (-0,261), Tercil 2 (-0,410), Tercil 3 (-0,512).
    - 20 km: Tercil 1 (-0,208), Tercil 2 (-0,518), Tercil 3 (-0,480).
  - Spearman nos tercis (taxa bruta), contudo, **discorda fortemente de Pearson nos estratos de baixo e médio fluxo**:
    - No Tercil 1 (menor tráfego), Spearman **não sobrevive e inverte o sinal** nos três tamanhos, tornando-se fracamente positivo e sem significância: 5 km (+0,025, $p = 0,332$), 10 km (+0,029, $p = 0,418$), 20 km (+0,050, $p = 0,315$). Com a taxa EB, o Spearman do tercil 1 fica próximo de zero e com sinal misto: 5 km (-0,035, $p = 0,171$), 10 km (-0,005, $p = 0,891$), 20 km (+0,029, $p = 0,557$) — a inversão de sinal não é robusta à troca de taxa; o que é robusto é a ausência de associação monotônica nesse estrato.
    - No Tercil 2 (tráfego intermediário), Spearman é negativo e significativo apenas em 5 km (-0,118, $p < 0,001$), mas perde significância em 10 km (-0,057, $p = 0,113$) e em 20 km (-0,047, $p = 0,343$).
    - Apenas no Tercil 3 (maior tráfego) Spearman concorda plenamente com Pearson, sendo negativo e significativo nos três tamanhos: 5 km (-0,309, $p < 0,001$), 10 km (-0,282, $p < 0,001$), 20 km (-0,198, $p < 0,001$).
  - Portanto, o veredito nos tercis **varia entre medidas e entre estratos**: enquanto Pearson sustenta a associação negativa sob qualquer corte de tráfego, Spearman indica que a relação monotônica inexiste nas faixas de baixo volume e só emerge onde o volume de veículos é elevado.

### Variação do veredito

Registra-se que o veredito **varia entre tamanhos** (Spearman sobrevive em 5 km e 10 km, mas não em 20 km) e **varia entre medidas** (no controle conjunto com Moran_BV e nos tercis de volume com Spearman), sem que nenhuma medida seja descartada ou privilegiada ad-hoc em favor de outra.

### Ressalva obrigatória de interpretação

Correlação parcial não identifica causa; sobreviver ao controle de volume não prova viés de amostragem — só deixa de ser explicado por log(AADT) linear.

---

## 2026-10-04 — Dispersão da taxa decresce com a cobertura temporal, e a associação C × R sobrevive com atenuação à ponderação por exposição nos três tamanhos

Avaliação direta da hipótese de precisão amostral (item R2-01 b do parecer 02 do trabalho `next-generation-road-safety`), investigando se a dispersão das taxas decresce com os anos de cobertura temporal ($C = \text{anos\_utilizaveis}$) e se a associação negativa entre cobertura e taxa de sinistros ($R$) decorre de imprecisão amostral nos trechos com menor histórico de contagem. Dados consolidados em `bases/prf-acidentes/resultados/precisao_amostral_corredores.csv`.

### Critério de decisão pré-registrado (Decisão 8)

Para cada tamanho de agregação espacial (5 km, 10 km e 20 km):
- **(b1) A dispersão decresce com a cobertura** se `brown_forsythe_classes` tem $p < 0,05$ **e** `spearman_c_desvio_abs` $< 0$ com $p < 0,05$; senão, não. Avalia-se também, descritivamente, se a variância e a distância interquartil (DIQ) caem monotonicamente (1–3 > 4–6 > 7–9 anos).
- **(b2) A precisão explica a associação** se `pearson_ponderado` no estrato global (`todos`) perde o sinal negativo **ou** apresenta $p \ge 0,05$; senão, a associação **sobrevive à ponderação** (e **atenua** se $|\text{ponderado}| < |\text{pearson}|$).
- **Dentro das classes:** reportam-se o sinal e o p-valor de Pearson e Spearman em cada classe temporal (1–3, 4–6 e 7–9 anos); a associação "persiste na classe" se for negativa com $p < 0,05$.

### Veredito sobre a dispersão temporal (hipótese b1)

Nos três tamanhos de faixa avaliados, tanto o teste de homogeneidade de variâncias quanto a correlação de postos confirmam que a dispersão das taxas diminui com o aumento da cobertura temporal:
- Em 5 km: `brown_forsythe_classes` tem $F = 406,152$ ($p < 0,001$, $gl = 2, 4.537$) e `spearman_c_desvio_abs` tem $r = -0,224$ ($p < 0,001$). Descritivamente, tanto a variância amostral (390.584,086 > 28.700,536 > 3.203,522) quanto a DIQ (384,284 > 76,542 > 30,890) caem monotonicamente na ordem 1–3 > 4–6 > 7–9 anos.
- Em 10 km: `brown_forsythe_classes` tem $F = 202,726$ ($p < 0,001$, $gl = 2, 2.326$) e `spearman_c_desvio_abs` tem $r = -0,214$ ($p < 0,001$). Descritivamente, variância (253.720,934 > 105.082,078 > 3.428,682) e DIQ (477,943 > 76,974 > 31,832) caem monotonicamente na ordem 1–3 > 4–6 > 7–9 anos.
- Em 20 km: `brown_forsythe_classes` tem $F = 93,800$ ($p < 0,001$, $gl = 2, 1.203$) e `spearman_c_desvio_abs` tem $r = -0,205$ ($p < 0,001$). Descritivamente, variância (548.514,600 > 328.562,082 > 4.392,665) e DIQ (621,566 > 82,493 > 33,287) caem monotonicamente na ordem 1–3 > 4–6 > 7–9 anos.
- O teste entre anos individuais (`brown_forsythe_anos`) corrobora a heterocedasticidade nos três tamanhos: 5 km ($F = 115,602$, $p < 0,001$, $gl = 7, 4.532$), 10 km ($F = 58,738$, $p < 0,001$, $gl = 7, 2.321$) e 20 km ($F = 37,066$, $p < 0,001$, $gl = 7, 1.198$).
- **Veredito geral de (b1):** a dispersão **decresce com a cobertura** nos três tamanhos.

### Veredito sobre a ponderação por exposição (hipótese b2)

Avaliando o estrato agregado (`todos`) com pesos $w_i = e_i$ ($\text{exposicao\_veic\_km}$, proporcional ao inverso da variância teórica de Poisson):
- Em 5 km ($n = 4.540$): Pearson passa de -0,362 ($p < 0,001$) para Pearson ponderado de -0,279 ($p < 0,001$). Como mantém o sinal negativo e significância com magnitude reduzida ($|-0,279| < |-0,362|$), o veredito é **sobrevive com atenuação**.
- Em 10 km ($n = 2.329$): Pearson passa de -0,392 ($p < 0,001$) para Pearson ponderado de -0,275 ($p < 0,001$). Como mantém o sinal negativo e significância com magnitude reduzida ($|-0,275| < |-0,392|$), o veredito é **sobrevive com atenuação**.
- Em 20 km ($n = 1.206$): Pearson passa de -0,367 ($p < 0,001$) para Pearson ponderado de -0,246 ($p < 0,001$). Como mantém o sinal negativo e significância com magnitude reduzida ($|-0,246| < |-0,367|$), o veredito é **sobrevive com atenuação**.
- **Veredito geral de (b2):** pelo critério da Decisão 8, a precisão **não explica** a associação $C \times R$: a associação negativa **sobrevive à ponderação com atenuação** nos três tamanhos.

### Persistência da associação dentro das classes de cobertura

Avaliando $C \times R$ dentro de estratos com cobertura homogênea:
- **5 km:**
  - 1–3 anos ($n = 120$): Pearson é -0,077 ($p = 0,402$), não persiste; Spearman é -0,201 ($p = 0,028$), **persiste**.
  - 4–6 anos ($n = 473$): Pearson é +0,050 ($p = 0,274$), não persiste; Spearman é +0,070 ($p = 0,129$), não persiste.
  - 7–9 anos ($n = 3.947$): Pearson é -0,083 ($p < 0,001$), **persiste**; Spearman é -0,043 ($p = 0,008$), **persiste**.
- **10 km:**
  - 1–3 anos ($n = 54$): Pearson é -0,172 ($p = 0,213$), não persiste; Spearman é -0,172 ($p = 0,213$), não persiste.
  - 4–6 anos ($n = 204$): Pearson é -0,055 ($p = 0,432$), não persiste; Spearman é +0,054 ($p = 0,443$), não persiste.
  - 7–9 anos ($n = 2.071$): Pearson é -0,070 ($p = 0,001$), **persiste**; Spearman é -0,035 ($p = 0,112$), não persiste.
- **20 km:**
  - 1–3 anos ($n = 22$): Pearson é +0,259 ($p = 0,244$), não persiste; Spearman é +0,248 ($p = 0,267$), não persiste.
  - 4–6 anos ($n = 76$): Pearson é -0,099 ($p = 0,395$), não persiste; Spearman é +0,026 ($p = 0,823$), não persiste.
  - 7–9 anos ($n = 1.108$): Pearson é -0,063 ($p = 0,037$), **persiste**; Spearman é -0,020 ($p = 0,517$), não persiste.

### Razão entre variância observada e esperada sob Poisson

A razão entre a variância amostral observada e a esperada sob Poisson ($\text{Razão} = s^2 / \text{Var}_{\text{Poisson}}$) em cada classe e tamanho é:
- Em 5 km: 202,504 na classe 1–3 anos; 82,646 na classe 4–6 anos; 34,628 na classe 7–9 anos.
- Em 10 km: 209,109 na classe 1–3 anos; 404,050 na classe 4–6 anos; 64,424 na classe 7–9 anos.
- Em 20 km: 535,355 na classe 1–3 anos; 1.587,007 na classe 4–6 anos; 129,569 na classe 7–9 anos.
- **O que a razão diz sobre o ruído de amostragem:** Sob a hipótese nula de que a variação observada decorre de flutuação amostral de contagem sob Poisson, a razão teórica esperada seria próxima de 1. Como os valores medidos situam-se entre 34,628 e 1.587,007 — dezenas a centenas de vezes superiores a 1 em todas as classes e tamanhos —, a variância observada entre as faixas excede em ordens de magnitude o ruído estocástico de contagem. Pelo número, o ruído de amostragem de Poisson responde por uma fração pequena da dispersão observada em todas as classes; o restante é heterogeneidade entre faixas, sem que a razão diga de onde ela vem.

### Baixo poder amostral nos estratos extremos

Registram-se duas limitações estruturais de poder estatístico:
- Na classe 7–9 anos, a cobertura $C$ assume exclusivamente os valores 7 ou 8 (o máximo observado no painel é de 8 anos, não existindo faixa com 9 anos). Cerca de 88% a 92% das faixas concentram-se exatamente em $C = 8$ (5 km: 3.479 de 3.947 faixas; 10 km: 1.851 de 2.071 faixas; 20 km: 1.021 de 1.108 faixas). A variabilidade quase nula de $C$ reduz drasticamente o poder estatístico dos testes intra-classe por construção.
- Na classe 1–3 anos na escala de 20 km, o número de faixas é de apenas $n = 22$ (16 com 1 ano, 2 com 2 anos e 4 com 3 anos), conferindo igualmente baixo poder amostral aos testes de associação nesse estrato.

### Variação do veredito entre tamanhos e medidas

O veredito de persistência intra-classe **varia entre tamanhos** e **varia entre medidas**:
- Pearson persiste na classe 7–9 anos nos três tamanhos (5 km: -0,083, $p < 0,001$; 10 km: -0,070, $p = 0,001$; 20 km: -0,063, $p = 0,037$), mas não persiste nas classes 1–3 e 4–6 anos em nenhum dos tamanhos.
- Spearman persiste apenas na escala de 5 km (nas classes 1–3 e 7–9 anos), perdendo a significância estatística em todas as classes nas escalas de 10 km e 20 km.
- Há discordância direta entre Pearson e Spearman na classe 1–3 anos a 5 km (Spearman persiste, Pearson não) e na classe 7–9 anos a 10 km e 20 km (Pearson persiste, Spearman não).
- Há inversões de sinal (coeficientes positivos) nas classes 4–6 e 1–3: na classe 4–6 anos (5 km Pearson +0,050 e Spearman +0,070; 10 km Spearman +0,054; 20 km Spearman +0,026) e na classe 1–3 anos a 20 km (Pearson +0,259 e Spearman +0,248).
- Registra-se que os resultados variam conforme a medida e a escala, sem resolução ad-hoc que privilegie uma métrica sobre a outra.

### Frase obrigatória sobre o que não se pode afirmar

Dispersão maior com menos anos é compatível com imprecisão, mas não a prova (faixa pouco contada pode também ser de outro tipo de via); e sobreviver à ponderação não identifica causa da associação.

---

## 2026-10-04 — Queda de 3 para 0 clusters HH no LISA a 10 km decorre da cobertura incompleta do próprio bin (b); os 3 sobreviventes têm VMDa implícito suspeito

Decomposição da queda no número de clusters alto-alto (HH) pós-FDR no LISA a 10 km (de 3 no painel completo para 0 no painel balanceado de 8 anos), avaliando quanto da redução decorre **(a) da exclusão dos 478 bins** sem histórico completo de monitoramento de tráfego e quanto decorre **(b) da cobertura incompleta do próprio bin**. Dados consolidados em `bases/prf-acidentes/resultados/lisa_decomposicao_queda_hh.csv`.

### Critério de decisão pré-registrado (Decisão 6)

O critério metodológico pré-registrado (Decisão 6 do plano de trabalho) estabelece:
- Se `efeito_cobertura_do_bin = 3` na semente 12345: os 3 HH são bins de cobertura incompleta; a queda é efeito da cobertura (b).
- Se `efeito_cobertura_do_bin = 0`: os 3 HH são bins balanceados; a queda é efeito da exclusão (a), discriminando qual subtermo (multiplicidade ou vizinhança) carrega a diferença.
- Caso misto: reportam-se os três termos sem resolução unívoca.
- Se a decomposição mudar entre sementes, reporta-se que muda e em quantas das cinco sementes avaliadas (12345, 1, 2, 3 e 4).
- Todo sobrevivente com tráfego implícito suspeito (`vmda_suspeito = True`, VMDa < 2.000 veículos/dia) deve ser explicitamente marcado na prosa.
- Frase obrigatória sobre o que não se pode afirmar: 3 HH num painel não balanceado não são hotspots de risco identificados; e a matriz $W$ de contiguidade é linear dentro de cada par `(br, uf)`.

### Veredito da decomposição na semente de referência (12345)

Na semente 12345, as contagens de clusters alto-alto pós-FDR nos quatro cenários avaliados são:
- **C1 (completo, $n = 2.329$):** 96 HH antes do FDR; corte FDR de 0,000451; **3** HH pós-FDR.
- **C2 (compl. só balanceados com FDR compl., $n = 1.851$):** 29 HH antes do FDR; corte FDR de 0,000451; **0** HH pós-FDR.
- **C3 (compl. restrito 1.851, $n = 1.851$):** 29 HH antes do FDR; corte FDR de 0,000459; **0** HH pós-FDR.
- **C4 (balanceado, $n = 1.851$):** 70 HH antes do FDR; corte FDR de 0,001432; **0** HH pós-FDR.

A decomposição sequencial aditiva dos três termos resulta em:
- `efeito_cobertura_do_bin` ($\text{HH}_{C1} - \text{HH}_{C2} = 3 - 0$): **3**;
- `efeito_multiplicidade` ($\text{HH}_{C2} - \text{HH}_{C3} = 0 - 0$): **0**;
- `efeito_vizinhanca` ($\text{HH}_{C3} - \text{HH}_{C4} = 0 - 0$): **0**;
- `queda_total` ($\text{HH}_{C1} - \text{HH}_{C4} = 3 - 0$): **3**.

Mapeamento para os termos da pergunta do Orientador:
- O termo **(b) cobertura incompleta do próprio bin** responde por **3** dos 3 clusters da queda (`efeito_cobertura_do_bin = 3`). Como nenhum dos 3 bins possui 8 anos monitorados de tráfego (`pertence_balanceado = False`), os 3 HH observados em C1 são eliminados imediatamente em C2 por insuficiência de cobertura do próprio bin.
- O termo **(a) exclusão dos 478 bins** responde por **0** clusters da queda (`efeito_multiplicidade + efeito_vizinhanca = 0 + 0 = 0`), sendo tanto o efeito da redução do número de hipóteses testadas no FDR (`efeito_multiplicidade = 0`) quanto a reconfiguração da matriz de contiguidade e da taxa global de referência (`efeito_vizinhanca = 0`) nulos na semente 12345.
- Pelo critério da Decisão 6: **os 3 HH são bins de cobertura incompleta; a queda é efeito da cobertura (b)**.

### Estabilidade nas cinco sementes

A decomposição varia entre as cinco sementes de Monte Carlo testadas (12345, 1, 2, 3 e 4):
- Em 4 das 5 sementes (**12345, 2, 3 e 4**), a totalidade dos clusters HH observados em C1 é explicada pela cobertura do próprio bin (`efeito_cobertura_do_bin`), com `efeito_multiplicidade = 0` e `efeito_vizinhanca = 0`:
  - Semente 12345: C1 = 3, C2 = 0, C3 = 0, C4 = 0 → cobertura = 3, multiplicidade = 0, vizinhança = 0, queda = 3;
  - Semente 2: C1 = 2, C2 = 0, C3 = 0, C4 = 0 → cobertura = 2, multiplicidade = 0, vizinhança = 0, queda = 2;
  - Semente 3: C1 = 1, C2 = 0, C3 = 0, C4 = 0 → cobertura = 1, multiplicidade = 0, vizinhança = 0, queda = 1;
  - Semente 4: C1 = 2, C2 = 0, C3 = 0, C4 = 0 → cobertura = 2, multiplicidade = 0, vizinhança = 0, queda = 2.
- Em 1 das 5 sementes (**semente 1**), C4 apresenta 1 cluster HH pós-FDR, resultando em: C1 = 1, C2 = 0, C3 = 0, C4 = 1 → cobertura = 1, multiplicidade = 0, vizinhança = -1, queda = 0.
- Em todas as 5 sementes (5 de 5), C2 = 0 e C3 = 0: nenhum bin do conjunto restrito aos balanceados atinge significância estatística pós-FDR em C2 ou C3, mantendo `efeito_multiplicidade = 0` em todas as sementes.
- O número de clusters HH pós-FDR em C1 oscila entre 1 e 3 conforme a semente (3 na semente 12345; 2 nas sementes 2 e 4; 1 nas sementes 1 e 3), refletindo a flutuação amostral de Monte Carlo (9.999 permutações) em torno do corte de Benjamini-Hochberg.

### Localização dos 3 HH sobreviventes e VMDa implícito

Os três bins que configuram clusters alto-alto pós-FDR em C1 na semente 12345 formam um trecho contíguo de 30 km na BR-364 no Acre:
- **BR-364/AC km 110–120**:
  - Sinistros: 39; exposição: 20.550.339,50 veic-km; extensão com exposição: 10,0 km; anos utilizáveis: 3 (2018; 2024; 2025); taxa: 189,78 por 100M veic-km; $p_{\text{sim}} = 0,0004$ (significativo sob corte FDR 0,000451);
  - VMDa implícito (10 km): 1.876,7 veículos/dia — **suspeito** (< 2.000);
  - VMDa implícito (km com exposição = 10,0 km): 1.876,7 veículos/dia — **suspeito** (< 2.000).
- **BR-364/AC km 120–130**:
  - Sinistros: 296; exposição: 8.289.905,55 veic-km; extensão com exposição: 9,0 km; anos utilizáveis: 4 (2017; 2018; 2024; 2025); taxa: 3.570,61 por 100M veic-km; $p_{\text{sim}} = 0,0003$ (significativo sob corte FDR 0,000451);
  - VMDa implícito (10 km): 567,8 veículos/dia — **suspeito** (< 2.000);
  - VMDa implícito (km com exposição = 9,0 km): 630,9 veículos/dia — **suspeito** (< 2.000).
- **BR-364/AC km 130–140**:
  - Sinistros: 104; exposição: 5.327.054,55 veic-km; extensão com exposição: 8,0 km; anos utilizáveis: 1 (2017); taxa: 1.952,30 por 100M veic-km; $p_{\text{sim}} = 0,0001$ (significativo sob corte FDR 0,000451);
  - VMDa implícito (10 km): 1.459,5 veículos/dia — **suspeito** (< 2.000);
  - VMDa implícito (km com exposição = 8,0 km): 1.824,3 veículos/dia — **suspeito** (< 2.000).

Os três sobreviventes disparam a guarda permanente de tráfego implícito suspeito (`vmda_suspeito = True`), registrando volume médio diário abaixo do piso de 2.000 veículos/dia em ambas as fórmulas (extensão nominal de 10 km e extensão efetiva com exposição).

### Frase obrigatória sobre o que não se pode afirmar

3 HH num painel não balanceado não são hotspots de risco identificados; a W é linear dentro de (br, uf).
