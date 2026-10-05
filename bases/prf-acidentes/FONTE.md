# Acidentes em Rodovias Federais (Agrupados por Ocorrência) — PRF

## O que é

A base de **Acidentes em Rodovias Federais (Agrupados por Ocorrência)** é divulgada pela Polícia Rodoviária Federal (PRF), por meio da Diretoria de Operações (DIOP), sob o sistema Boletim de Acidente de Trânsito (BAT) e o sistema legado BR-Brasil.

O grão no arquivo bruto é este: **uma linha = uma ocorrência de acidente de trânsito em rodovia federal policiada pela PRF**.

A base da PRF cobre exclusivamente a malha rodoviária federal sob jurisdição e policiamento da Polícia Rodoviária Federal ao longo de 20 safras anuais.

### Licença declarada pela fonte

A página de Dados Abertos da PRF **não declara licença nominal** para os dados (nenhum ODbL, CC-BY ou equivalente). O que a página informa é o regime geral: os dados abertos são disponibilizados "sem restrição de licenças, patentes ou mecanismos de controle, que qualquer pessoa pode livremente usá-los, reutilizá-los e redistribuí-los", no marco da Lei de Acesso à Informação (Lei nº 12.527/2011), da IN SLTI nº 4/2012 (Infraestrutura Nacional de Dados Abertos) e do Decreto nº 8.777/2016 (Política de Dados Abertos do Executivo Federal). O rodapé do portal gov.br exibe "Creative Commons Atribuição-SemDerivações 3.0" para o **conteúdo do site** — não é licença de dados e não se aplica aos CSVs. O manifest registra `"não declarada pela fonte"`.

### Os três recortes publicados e escopo de uso

A PRF publica os dados do BAT em três recortes com granularidades distintas:

1. **Agrupados por ocorrência** (o recorte desta base): cada registro representa um acidente de trânsito (2007–2026).
2. **Agrupados por pessoa**: cada registro representa um indivíduo (condutor, passageiro ou pedestre) envolvido no acidente (2007–2026).
3. **Agrupados por pessoa — Todas as causas e tipos de acidentes**: mesmo grão de pessoa, com o vocabulário completo de causa/tipo (publicado apenas de 2017 em diante — o que por si só já seria fronteira).

**Por que apenas o recorte de ocorrência foi utilizado nesta rodada:** O arquivo agrupado por ocorrência é o grão primário e direto para a contagem de acidentes, fatalidades, feridos e classificação de gravidade sem redundâncias ou multiplicações decorrentes da quantidade de veículos ou vítimas envolvidas.

### Estrutura de colunas e evolução dos leiautes

A base apresenta três leiautes ao longo da série temporal:

- **2007–2015 (`26` colunas):** `id`, `data_inversa`, `dia_semana`, `horario`, `uf`, `br`, `km`, `municipio`, `causa_acidente`, `tipo_acidente`, `classificacao_acidente`, `fase_dia`, `sentido_via`, `condicao_metereologica`, `tipo_pista`, `tracado_via`, `uso_solo`, `ano`, `pessoas`, `mortos`, `feridos_leves`, `feridos_graves`, `ilesos`, `ignorados`, `feridos`, `veiculos`.
- **2016 (`25` colunas):** A coluna `ano` foi removida, mantendo as demais `25` colunas.
- **2017–2026 (`30` colunas):** Foram adicionadas 5 novas colunas ao final do arquivo: `latitude`, `longitude`, `regional`, `delegacia`, `uop`.

---

## URL e Dicionário de dados

Página oficial de Dados Abertos da PRF:  
<https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf>

Dicionário de dados das variáveis e layouts do BAT ("Dicionário de Dados - Acidentes"):  
<https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dicionario-acidentes>

---

## Periodicidade

**Mensal** (declarada). A PRF disponibiliza safras anuais consolidadas e atualizações mensais do ano em curso.

---

## Como baixar

Os arquivos brutos são servidos em arquivos compactados ZIP disponibilizados via Google Drive no portal de Dados Abertos da PRF.

Para baixar diretamente via terminal contornando a página de confirmação do Google Drive, utiliza-se `wget` apontando para o endpoint `drive.usercontent.google.com`:

```bash
# Exemplo de download para a safra 2011 (substituir o ID pelo correspondente no manifest.json)
wget -U "<User-Agent de navegador>" -O raw/prf-acidentes/datatran2011.zip \
  "https://drive.usercontent.google.com/download?id=1HHhgLF-kSR6Gde2qOaTXL3T5ieD33hpG&export=download&confirm=t"
```

Conferência do checksum SHA-256 contra o `manifest.json`:

```bash
sha256sum raw/prf-acidentes/datatran2011.zip
```

As URLs originais, IDs do Google Drive, hashes sha256 e datas de acesso estão registrados em `bases/prf-acidentes/manifest.json`.

---

## Pegadinhas conhecidas do reconhecimento

### 1. Mudança de layout de colunas (26 → 25 → 30 colunas)
De 2007 a 2015 os arquivos possuíam 26 colunas. Em 2016 a coluna ano foi removida (25 colunas). A partir de 2017 entraram novas colunas de geolocalização e estrutura administrativa (30 colunas). O leitor em `bin/extrai_prf_acidentes.py` valida o cabeçalho de cada safra contra o layout esperado do seu ano (depois de normalizar: strip, aspas, minúsculas, sem acento); os 25 nomes comuns são estáveis nos três layouts.

### 2. Três formatos de data e notação exclusiva de 2016
A coluna `data_inversa` utiliza `yyyy-mm-dd` ou `dd/mm/yyyy` em 2007–2015 e 2017–2026, porém na safra de 2016 adota exclusivamente o formato `dd/mm/aa` (onde o ano vem representado por dois dígitos, ex.: `16`).

### 3. Codificação latin-1, separador ponto e vírgula e aspas
Todas as 20 safras utilizam codificação `latin-1` (`ISO-8859-1`), separador ponto e vírgula (`;`) e quebra de linha CRLF (`\r\n`). As aspas duplas envolvendo campos de texto só foram introduzidas a partir de 2012.

### 4. Identificadores e repetição do campo `id`
No sistema legado BR-Brasil (2007–2016), o campo id possuía repetições de identificadores em algumas ocorrências (ex.: 1 id repetido em 2016). Com a implantação do BAT em 2017, o `id` passou a ser 100% único por acidente.

### 5. Rótulo de classificação nula (`Ignorado` vs `NA`)
Na variável `classificacao_acidente`, os acidentes sem classificação válida eram registrados como `Ignorado` até 2016 e passaram a ser gravados como `NA` (ou `(null)`) a partir de 2017.

### 6. Instabilidade de IDs do Google Drive
Os links de download são hospedados no Google Drive. A PRF pode alterar os IDs de arquivo e republicar ZIPs a qualquer momento. Caso o sha256 de uma safra mude em relação ao `manifest.json`, o extrator gera um erro duro em vez de processar dados alterados silenciosamente.

### 7. Tabela de IDs do Google Drive por safra

| Ano | Nome do arquivo | ID do Google Drive | Tamanho (bytes) | SHA-256 |
|---|---|---|---|---|
| 2007 | datatran2007.zip | `1EFpZF5F6cB0DOHd2Uxnj7X948WE69a8e` | `3.078.464` | `8723ba7ad6ca9979b86b39e2488b0ccf2aee5fa63a0d1135880c2577caf950e1` |
| 2008 | datatran2008.zip | `1_OSeHlyKJw8cIhMS_JzSg1RlYX8k6vSG` | `3.383.500` | `4c56a3ad8d418a2107aacd64dc10a23976f5508c2935479f1ae24a5d4097a7ae` |
| 2009 | datatran2009.zip | `1qkVatg0pC_zosuBs0NCSgEXDJvBbnTYC` | `3.795.569` | `ef5a00393572b4742928ba04e26a0177a20ae1817d7b261f3d8d4378005ac8ac` |
| 2010 | datatran2010.zip | `1_yU6FRh8M7USjiChQwyF20NtY48GTmEX` | `4.394.611` | `8d665f411a01af2181da8f0e8300e24d810839cdd7364cc9f72fda4d14bfafa6` |
| 2011 | datatran2011.zip | `1HHhgLF-kSR6Gde2qOaTXL3T5ieD33hpG` | `4.600.829` | `e2b3dc33756cf22546b691fff435348087458e44fc67d3d2eb2730f09e5c5933` |
| 2012 | datatran2012.zip | `18Yz2prqKSLthrMmW-73vrOiDmKTCL6xE` | `4.641.569` | `5c1336e3fa05a5d80429ec928955f4f7a9c06f1feeceebf8997262f1863be99c` |
| 2013 | datatran2013.zip | `1p_7lw9RzkINfscYAZSmc-Z9Ci4ZPJyEr` | `4.707.582` | `f79e5bc4f60e4ff923bf96ccaad80f0a6a1bae49a04ca2a26a61a5749e747175` |
| 2014 | datatran2014.zip | `1FpF5wTBsRDkEhLm3z2g8XDiXr9SO9Uk8` | `4.304.737` | `b2416bd4ecb4886579615ee9ff722e23f650496ef12a46a317aac953a9466dc7` |
| 2015 | datatran2015.zip | `1DyqR5FFcwGsamSag-fGm13feQt0Y-3Da` | `3.163.538` | `07ac0fdbbb149614ff1345384dab6d09b36d5b302a7dccc4a8c4bdfe8b2d9186` |
| 2016 | datatran2016.zip | `16qooQl_ySoW61CrtsBbreBVNPYlEkoYm` | `2.518.479` | `27438f9a66969b57a797eedad795c8058de3ee0a8e7e235b8c3d36228a23c7bd` |
| 2017 | datatran2017.zip | `1HPLWt5f_l4RIX3tKjI4tUXyZOev52W0N` | `4.248.009` | `b5d40934c644e61fed2d70b332aca55b5f4bb293a90cf1771749cd2e2fc20fba` |
| 2018 | datatran2018.zip | `1cM4IgGMIiR-u4gBIH5IEe3DcvBvUzedi` | `3.294.461` | `a8eab316cc17c1af4d2295a5617c5cce37b57b4737a0d76ce902ed4e7c91084c` |
| 2019 | datatran2019.zip | `1pN3fn2wY34GH6cY-gKfbxRJJBFE0lb_l` | `3.237.669` | `3a7022edf4690334aae309cb1b01a7c98649bd9a0a05ce7d0bd3e7416183155d` |
| 2020 | datatran2020.zip | `1esu6IiH5TVTxFoedv6DBGDd01Gvi8785` | `3.075.980` | `92cb80217a17268c4f6fb8f91f36284ce90f28aac7053f0e857fafa5e838c9d8` |
| 2021 | datatran2021.zip | `12xH8LX9aN2gObR766YN3cMcuycwyCJDz` | `3.217.660` | `a246e0d1205860a475335f8996b532cbe2ca4c1c349bb5a1531bf47a779e3901` |
| 2022 | datatran2022.zip | `1PRQjuV5gOn_nn6UNvaJyVURDIfbSAK4-` | `3.227.721` | `5ace05699b82c720e47e28768323630310ef7fe300db57388da246fb448c8855` |
| 2023 | datatran2023.zip | `1-WO3SfNrwwZ5_l7fRTiwBKRw7mi1-HUq` | `3.397.281` | `b233c47d16b3980a6692472f9fe1bbab57698700fbb918d22628a5c0a382d985` |
| 2024 | datatran2024.zip | `14lB0vqMFkaZj8HZ44b0njYgxs9nAN8KO` | `3.681.095` | `20cec26ae45e794d57c0f4d2c0915d3f6f84a9895b3e1b9c0cd126f075700645` |
| 2025 | datatran2025.zip | `1-G3MdmHBt6CprDwcW99xxC4BZ2DU5ryR` | `3.727.148` | `52c8a631ac9d428bf845e2fa996b8c61f66b219f7014a61d292f9d95d186bb0f` |
| 2026 | datatran2026.zip | `1A3IirNm0AzRaSosA1IS94DOVmvKsn0Ol` | `2.172.432` | `a58eaf076957b20467f2eaf18f07593780936f8ac2c0c5ae1d22c7855e72280b` |

⚠️ **Advertência:** Os IDs acima são os capturados no momento do congelamento da base. Como a PRF distribui via links dinâmicos do Google Drive e republica os dados mensalmente, esses identificadores não são garantidos como permanentes.

### 8. Coordenadas geográficas a partir de 2017
As colunas `latitude` e `longitude` existem de 2017 em diante, mas **não são publicadas nesta rodada** (o formato de armazenamento de geometria no repositório continua em definição).

### 9. Degraus administrativos de registros sem vítima (2015 e 2018)
A notificação de acidentes sem vítima sofreu dois degraus de descontinuidade administrativa (junho-julho de 2015 e março-abril de 2018), decorrentes da criação do e-DAT e alteração das diretrizes de atendimento presencial da PRF para danos exclusivamente materiais.

### 10. Ruptura taxonômica em causa e tipo de acidente em 2017
As variáveis causa_acidente e tipo_acidente sofreram reestruturação completa em 2017: a causa saltou de 11 para 24 categorias (atingindo 75 em 2023) e o tipo tinha 16 rótulos em 2016, dos quais 10 desaparecem em 2017 — substituídos por renomeações em bloco (`Atropelamento de pessoa` → `Atropelamento de Pedestre`, `Colisão com objeto fixo` → `Colisão com objeto estático`) e por rótulos novos (`Engavetamento`), deixando o vocabulário em 17 rótulos, com `Sinistro pessoal de trânsito` entrando em 2024. Isso inviabiliza séries históricas longas sem harmonização prévia.
