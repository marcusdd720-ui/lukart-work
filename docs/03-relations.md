# Macierz relacji i cardinality

Wszystkie relacje są kierunkowe, case-local, do dokładnej rewizji. `1` = required, `0..1` = optional, `0..*` = required collection dopuszczająca [], `1..*` = niepusta kolekcja. Relacja odwrotna jest projekcją i ma 0..*, chyba że wskazano inaczej. Nie zapisujemy ręcznie inverse arrays. Relacje do wcześniejszej rewizji tej samej encji są dozwolone wyłącznie dla historii/akceptacji, nie jako cykliczna dependency wykonawcza.

| Źródło | Pole / cel | Cardinality z jednej rewizji | Ograniczenie |
|---|---|---|---|
| Case | ownership wszystkich encji przez case_id | 0..* dzieci | każde dziecko dokładnie 1 Case; Case.id=case_id |
| Party | identity_evidence → Evidence | 0..* | VERIFIED: decyzja, nie liczba dowodów |
| Party | verification_decision → Decision | 0..1 | VERIFIED: 1 |
| Institution | registry_identifier / provenance anchors | 0..1 / 0..* | identyfikator rejestru nie jest Ref do innego Case |
| Proceeding | institution → Institution | 1 | właściwość weryfikuje procedural validator |
| Proceeding | participants.party → Party | 1..* | rola na Participation; duplikat identycznej party/role zabroniony |
| Proceeding | participants.represented_by → Party | 0..1 na participation | brak automatycznego domniemania pełnomocnictwa |
| Proceeding | parent_proceeding → Proceeding | 0..1 | bez cyklu rodziców |
| Filing | proceeding → Proceeding | 0..1 | przedprocesowe bez proceeding |
| Filing | recipient → Institution lub Party | 1 | dokładnie jeden typ union |
| Filing | authors → Party | 1..* | unikalne Ref |
| Fact | evidence → Evidence | 0..* | SOURCE_BACKED: 1..* |
| Fact | subjects → Party/Institution | 0..* | nie przechowujemy wyłącznie imion w statement |
| Fact | acceptance → Decision | 0..1 | CONFIRMED: 1 |
| Evidence | source → SourceDocument+Locator | 1 | źródłowy supporting record, nie 24. encja kanoniczna |
| Evidence | submitted_in → Proceeding | 0..1 | konkretny kontekst złożenia |
| Issue | facts → Fact; rules → LegalRule | 0..* każde | brak podstaw → UNRESOLVED |
| Issue | resolution → Decision | 0..1 | RESOLVED: 1 |
| LegalSource | registry_pin → registry version | 1 | case-local admission |
| LegalSource | anchor → SourceDocument | 1 | dokładne bytes i hash |
| LegalRule | sources → LegalSource | 1..* | skuteczność temporalna sprawdzana osobno |
| LegalRule | review_decision → Decision | 0..1 | ACTIVE: 1 |
| Claim | claimant → Party | 1 | owner stanowiska |
| Claim | issues → Issue | 1..* | wszystkie unikalne |
| Claim | facts → Fact; rules → LegalRule | 0..* każde | adoption wymaga wystarczającego wsparcia |
| Claim | adoption → Decision | 0..1 | ADOPTED: 1 |
| Defence | claim → Claim; party → Party | 1 każde | przeciwny claim pozostaje osobnym rekordem |
| Defence | facts → Fact; rules → LegalRule | 0..* każde | odrębne podstawy obrony |
| Defence | adoption → Decision | 0..1 | ADOPTED: 1 |
| Argument | target → Claim/Defence | 1 | polarity SUPPORTS/OPPOSES |
| Argument | premises → Fact/Claim/Argument | 1..* | source tracing do podstaw |
| Argument | rules → LegalRule | 0..* | brak prawa nie może być ukryty |
| Argument | assessments.basis → Fact/Evidence/LegalRule/CounterArgument | 0..* | ocena UNKNOWN dozwolona |
| CounterArgument | target_argument → Argument | 1 | CHALLENGES |
| CounterArgument | premises → Fact/Claim/LegalRule | 0..* | brak podstaw oznaczany |
| CounterArgument | response_argument → Argument | 0..1 | ANSWERED: 1 |
| Request | filing → Filing | 1 | granica dokumentu |
| Request | claims → Claim | 1..* | BASED_ON |
| Request | evidence → Evidence | 0..* | wniosek dowodowy wiąże przedmiot dowodu |
| Request | approval → Decision | 0..1 | APPROVED: 1 |
| Deadline | proceeding → Proceeding; filing → Filing | 0..1 każde | docelowo co najmniej jedno, jeżeli znany zakres |
| Deadline | trigger → Fact | 1 | także niepotwierdzony trigger → UNKNOWN |
| Deadline | rules → LegalRule | 0..* | VERIFIED wymaga wyjaśnialnej podstawy |
| Deadline | satisfaction → Filing/Decision | 0..1 | SATISFIED: 1 |
| Risk | affected → dowolna encja | 1..* | scope musi być wspólny |
| Risk | mitigation → Decision/Request; acceptance → Decision | 0..1 każde | ACCEPTED: acceptance=1 |
| Citation | source → LegalSource | 1 | REFERS_TO |
| Citation | supported → LegalRule/Argument/Claim/Section | 1 | może być używane w wielu Statements |
| DocumentPlan | filing → Filing | 1 | 0..* planów na Filing |
| DocumentPlan | recipient → Institution/Party | 1 | zgodny z Filing |
| DocumentPlan | objectives → Request | 1..* | request.filing musi odpowiadać plan.filing |
| DocumentPlan | argument_order → Argument; evidence → Evidence | 0..* każde | listy z unikalnymi referencjami |
| DocumentPlan | section_order → Section | 1..* | kolejność normatywna; Section.filing zgodne |
| DocumentPlan | approval → Decision | 0..1 | APPROVED: 1 |
| DocumentPlan | input_snapshot ID/hash | 1 | accepted snapshot wymagany przed użyciem |
| Section | filing → Filing | 1 | plan używa wersji sekcji, sekcja nie wskazuje wersji planu |
| Section | arguments → Argument | 0..* | USES |
| Section | allowed_inputs / required_inputs → Fact/Evidence/LegalRule/Argument/Claim/Request/Citation | 0..* każde | required⊆allowed |
| Section | allowed_claims → Claim | 0..* | nie rozszerza automatycznie allowed_inputs |
| Draft | plan → DocumentPlan | 1 | approved przed generacją |
| Draft | sections.section → Section | 0..* | GENERATED i później 1..*, zgodne z planem |
| Draft | statements.refs → Fact/Evidence/LegalRule/Claim/Argument/Request | 0..* | significant source-backed: 1..* |
| Draft | statements.citations → Citation | 0..* | prawne statements wymagają zweryfikowanej coverage |
| Draft | supersedes → Draft | 0..1 | bez cyklu; nowe id przy zmianie treści |
| Draft | snapshot ID/hash | 1 | komplet odtwarzalnych inputs |
| ValidationFinding | target → dowolna encja | 1 | target_hash związany z rewizją |
| ValidationFinding | resolution → Decision | 0..1 | RESOLVED/FALSE_POSITIVE: 1 |
| Decision | targets → dowolna encja | 1..* | scope i dokładne rewizje |
| Decision | supersedes → Decision | 0..1 | starej decyzji nie usuwamy |
| wszystkie Entity | provenance.inputs → dowolna encja | 0..* | closure snapshotu obejmuje historię |
| wszystkie Entity | provenance.anchors → SourceDocument | 0..* | sprawdzany scope i source hash |

Pola o max=1 oznaczają pojedynczą wartość, nie listę. Wielokrotne przypisanie źródła do różnego pisma przez Evidence może wymagać kolejnego case-local Evidence record lub supporting association na etapie 05; nie kopiujemy ani nie nadpisujemy oryginalnych bytes. LegalSource do Evidence nie ma implicit relacji: źródło prawa i dowód faktyczny mają odrębne role.

Typed KG projection: FACT SUPPORTED_BY EVIDENCE; CLAIM SUPPORTED_BY FACT; CLAIM GOVERNED_BY LEGAL_RULE; ARGUMENT SUPPORTS/OPPOSES CLAIM/DEFENCE; COUNTERARGUMENT CHALLENGES ARGUMENT; REQUEST BASED_ON CLAIM; SECTION USES ARGUMENT; CITATION REFERS_TO LEGAL_SOURCE. Pozostałe relacje są ownership, provenance lub association, nie domyślną zależnością wykonawczą.

## Doprecyzowanie po AGR-01-001–007

Unikalność zagnieżdżonych refs obowiązuje osobno w każdej kolekcji liściowej, np. Statement.refs i Statement.citations. To samo Fact/Citation może wystąpić w wielu zdaniach. Participation ma klucz (party Ref, role); wspólny represented_by jest dozwolony. Reguła typów nie implikuje globalnej unikalności po spłaszczeniu całej encji.

SectionContract required/allowed obejmuje sumę Statement.refs i Statement.citations. Citation pozostaje wyłącznie w citations; nie dopuszczamy go w refs. AI i domena używają tego samego guardu, a AI musi dodatkowo pozostać w request.input_refs.

Decision.snapshot_target wiąże scope i snapshot ID/hash; targets zawiera dokładnie jeden Case Ref należący do snapshotu. Decision.render_target wiąże scope, snapshot ID/hash, Draft Ref/hash i uporządkowane unikalne hashe artefaktów; targets zawiera dokładnie ten Draft Ref. Te value objects nie powiększają zbioru 23 encji. ReleaseReceipt utrwala tę podstawę wraz z decyzją, runami, policy i case_sequence. Szczegóły: 07-stage01-remediation.md.
