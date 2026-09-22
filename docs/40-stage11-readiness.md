# Stage 11 — gotowość Rendering Engine

Status: IMPLEMENTATION IN PROGRESS

Repozytorium: `marcusdd720-ui/lukart-work`

Bazowy SHA:
`74364cb7b648feaff30cff465a5beade8d5f3498`

Architecture Gate:
GitHub Issue #25 — `Stage 11A — Rendering Architecture Gate`.

## Potrzeba decyzyjna

Stage 10 kończy kontrolowane tworzenie i walidację treści, ale nie istnieje jeszcze
produkcyjny, deterministyczny renderer DOCX/PDF. Po scaleniu trusted-procedure PR #17
workflow `Stage 11 Rendering Assurance` prawidłowo zatrzymał `main`, ponieważ
`tests/test_stage11.py` nie istniał.

Stage 11 wdraża brakującą granicę:

```text
SemanticDocument
    -> RenderModel
    -> LayoutTree
    -> DOCX / PDF
    -> RenderReceipt
```

## Inwarianty

- Renderer nie podejmuje decyzji prawnych.
- Renderer nie korzysta z modelu AI.
- Renderer nie zmienia treści zatwierdzonego Draft.
- Jeden RenderModel zasila oba formaty.
- Styl pochodzi z wersjonowanego RenderProfile.
- Font jest kontrolowany przez dokładny SHA-256.
- Brak fontu lub niezgodny hash oznacza FAIL.
- PDF jest kanonicznym artefaktem wizualnym.
- DOCX jest kontrolowanym artefaktem edytowalnym.
- Brak widocznych etykiet AI/REVIEW.
- Ten sam input + profil + renderer ma dawać identyczne bajty w kontrolowanym środowisku.
- Brak dowodu deterministyczności oznacza brak PASS.

## Granica lifecycle

Wykryto istniejącą niespójność pomiędzy `Draft.APPROVED` a końcowym
`DOCUMENT_APPROVAL`, który wymaga hashy już wyrenderowanych artefaktów.

Stage 11 nie obchodzi tej granicy. Rendering Engine:
- renderuje stan co najmniej `VALIDATED`;
- nie awansuje sam Draft do `FINAL`;
- zwraca `RenderReceipt` i dokładne hashe;
- pozostawia finalną decyzję `DOCUMENT_APPROVAL` człowiekowi po obejrzeniu artefaktu.

Pełna orkiestracja release pozostaje poza czystym rendererem.

## Zakres

W zakresie:
- RenderModel,
- LayoutTree,
- RenderProfile,
- RenderReceipt,
- DOCX,
- PDF,
- typografia PL,
- deterministyczność,
- bezpieczeństwo artefaktów,
- testy golden/adversarial,
- regresja,
- exact-SHA CI,
- niezależny review,
- merge i post-merge.

Poza zakresem:
- Legal Semantic IR,
- LegalDraftingPolicy,
- AdvocacyPolicy,
- Legal Surface Realizer,
- edytor,
- Stage 12+.
