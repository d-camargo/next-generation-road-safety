# next-generation-road-safety — companion repo (Open Data)

> **Fonte única das regras deste repo.** `CLAUDE.md` e `AGENTS.md` são symlinks
> relativos para cá (padrão da casa — ver `~/GEMINI.md` §2). Edite sempre aqui.

**O que é este repo:** publicação Open Data + código de replicação do trabalho
científico `next-generation-road-safety` (Collection *Next-Generation Road
Safety*, Discover Civil Engineering). É um **snapshot publicado** do pipeline
espacial que vive no repo `dados` (commit de origem registrado em
`docs/fontes_dados.yaml` e no README) e do manuscrito que vive no repo
`sci-team`.

**Regra 1 — este repo não é local de desenvolvimento.** Mudança de método,
novo recorte, novo número: nasce no repo `dados` (rito plan → run → review,
com testes de proveniência), entra no artigo, e só então é republicada aqui
como nova versão/release (o DOI do Zenodo é por release — nunca reescreva
história depois do primeiro release).

**Regra 2 — nunca inventar número** (herdada do repo `dados`): todo número
nesta árvore desce de célula de CSV ou de literal declarado em
`docs/fontes_dados.yaml`. Prosa nova no README só com lastro.

**Regra 3 — fidelidade de código:** os scripts em `bin/` são cópias fieis dos
`bin/*.py` do repo `dados` no commit de origem. Não "conserte" nada aqui sem
atualizar a origem primeiro; qualquer ajuste de caminho fica documentado no
README, não no código.

Criado em 2026-10-05.
