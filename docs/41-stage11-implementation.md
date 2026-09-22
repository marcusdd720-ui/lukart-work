# Stage 11 — implementacja Rendering Engine

Status: IMPLEMENTATION IN PROGRESS

## Warstwy

```text
SemanticDocument
    ↓
assemble_render_model()
    ↓
RenderModel
    ↓
build_layout()
    ↓
LayoutTree
    ├── render_docx()
    └── render_pdf()
    ↓
RenderReceipt
```

## RenderModel

RenderModel zawiera wyłącznie dane gotowe do przedstawienia:
- role semantyczne,
- tekst,
- powiązania z `Ref`,
- kolejność,
- snapshot i Draft.

Assembler może rozwiązać istniejące canonical refs do nazw stron, treści wniosków,
tytułów sekcji i opisów dowodów. Nie może tworzyć nowych faktów ani zdań prawnych.

## LayoutTree

LayoutTree wiąże każdy blok z semantycznym tokenem stylu.

Przykłady:
- `document.body`,
- `document.heading.primary`,
- `document.heading.secondary`,
- `document.party_block`,
- `document.request`,
- `document.legal_basis`,
- `document.signature`,
- `document.attachment`.

Adaptery DOCX/PDF nie podejmują decyzji o znaczeniu tekstu.

## OFFICIAL_PL_V1

Pierwszy profil:
- A4,
- kontrolowane marginesy,
- jedna logiczna rodzina fontów,
- jawna hierarchia typograficzna,
- kontrolowane odstępy i wcięcia,
- obsługa polskich znaków,
- brak cichej substytucji fontu.

Font produkcyjny jest rozpoznawany po SHA-256 bajtów, a nie wyłącznie po nazwie.

## DOCX

DOCX:
- jest budowany z tych samych bloków co PDF;
- deklaruje font profilu na wszystkich emitowanych runach;
- kontroluje marginesy, interlinię, odstępy i hierarchię;
- normalizuje metadane i ZIP timestamps;
- nie zawiera makr;
- nie może zawierać relacji zewnętrznych.

## PDF

PDF:
- powstaje bez konwersji z DOCX;
- korzysta z dokładnie zweryfikowanych bajtów fontu;
- font jest osadzony;
- metadane i document identity są deterministyczne;
- aktywna zawartość jest zabroniona.

## Tożsamość

`RenderReceipt` rozdziela:
- `semantic_digest`,
- `render_model_digest`,
- `layout_digest`,
- `artifact_hash`.

Pozwala to odróżnić zmianę znaczenia od zmiany prezentacji.

## Fail-closed

Renderer odrzuca:
- brak rekordu,
- cross-case ref,
- drift SemanticDocument względem Draft.sections,
- zły RenderProfile,
- zły hash fontu,
- niejednoznaczny attachment provenance,
- uszkodzony DOCX/PDF,
- aktywną zawartość,
- hash mismatch.


## Semanticzne tokeny projektu dokumentu

Adaptery formatów nie mają własnej ukrytej tabeli typografii. Każdy `LayoutBlock`
wskazuje `style_token`, a pełna polityka wizualna jest zdefiniowana w wersjonowanym
`RenderProfile.styles`.

Każdy `StyleSpec` kontroluje:
- rozmiar i wagę fontu,
- interlinię,
- odstępy,
- wcięcia,
- wyrównanie,
- `keep_with_next`,
- `keep_together`,
- kontrolę wdów/sierot,
- jawny page break.

DOCX i PDF odczytują te same tokeny. Rola semantyczna służy do znaczenia bloku;
parametry wizualne nie są wybierane ponownie przez adapter.

## Nagłówek, stopka i numeracja

`RenderProfile` jawnie określa politykę nagłówka, stopki oraz numeracji stron.
`OFFICIAL_PL_V1` nie dodaje dekoracyjnego nagłówka ani provenance, natomiast włącza
deterministyczną numerację stron. DOCX wykorzystuje kontrolowane pole `PAGE`; PDF
rysuje numer strony w kontrolowanej stopce.

## Powiązanie autoryzacji

`authorization_binding(SemanticDocument, RenderProfile)` wylicza kanoniczne powiązanie
dokładnej reprezentacji semantycznej z dokładnym profilem renderowania. `RenderingEngine`
odrzuca żądanie, jeżeli `RenderRequest.authorization_hash` nie odpowiada temu powiązaniu.
Zmiana nagłówka, treści, referencji, sekcji lub profilu po utworzeniu autoryzacji powoduje
więc fail-closed przed emisją artefaktu.

To powiązanie zapewnia integralność wejścia, ale samo nie jest uwierzytelnieniem użytkownika.
Decyzja, że konkretne wejście może zostać wyrenderowane, nadal należy do zaufanej granicy
pre-render opisanej w `docs/01-specification.md`. Czysty renderer nie może sam sobie
przyznać takiej kompetencji. `RenderReceipt.authorization_hash` zachowuje dokładną tożsamość
autoryzowanego uruchomienia do dalszej kontroli `RenderTarget` / `RequestRelease`.
