# LUKART WORK — Generator Pism
## 00 — Architektura systemu

**Status:** ARCHITECTURE BASELINE  
**Klasa systemu:** Legal Document Engineering / Legal Reasoning / Procedural Automation  
**Docelowa integracja:** LUKART ROS  
**Zasada graficzna:** CLEAN-SLATE — brak dziedziczenia wcześniejszych wzorców UI, dokumentów i layoutów.

---

# 1. Cel systemu

LUKART WORK nie powinien być zwykłym generatorem tekstu ani kolekcją szablonów Word.

Docelowo ma być **systemem inżynierii pism prawnych i procesowych**, który potrafi przejść od materiału sprawy do kontrolowanego, audytowalnego dokumentu końcowego.

System ma obsługiwać m.in.:

| Klasa dokumentu | Przykłady |
|---|---|
| procesowe | pozew, odpowiedź na pozew, apelacja, zażalenie, sprzeciw |
| sądowe | wniosek, stanowisko procesowe, pismo przygotowawcze |
| egzekucyjne | wnioski i skargi dotyczące egzekucji |
| administracyjne | odwołania, zażalenia, wyjaśnienia |
| przedprocesowe | wezwania do zapłaty, reklamacje, odpowiedzi |
| urzędowe | ZUS, UFG, RPO, RF, organy administracji |
| dowodowe | wnioski dowodowe, zestawienia dowodów |
| analityczne | chronologia, memorandum, analiza ryzyk |

Rezultatem nie jest tylko tekst.

Rezultatem jest:

**CASE → ANALYSIS → ARGUMENTATION → DOCUMENT → VALIDATION → RENDER → AUDIT**

---

# 2. Nadrzędna zasada architektoniczna

Generator nie może działać według modelu:

`prompt → LLM → gotowe pismo`

Taki model jest zbyt podatny na:

- pomijanie faktów,
- tworzenie nieistniejących faktów,
- pomieszanie twierdzeń z dowodami,
- błędne podstawy prawne,
- niespójności dat i kwot,
- niekontrolowane zmiany stanowiska,
- brak wykrywania sprzeczności,
- brak kontroli wymogów formalnych.

Architektura docelowa:

```text
MATERIAŁ ŹRÓDŁOWY
        ↓
CASE MODEL
        ↓
FACT / EVIDENCE MODEL
        ↓
LEGAL + PROCEDURAL MODEL
        ↓
ISSUES
        ↓
CLAIMS / DEFENCES
        ↓
ARGUMENT GRAPH
        ↓
DOCUMENT PLAN
        ↓
CONTROLLED DRAFTING
        ↓
VALIDATION
        ↓
RENDERING
        ↓
FINAL DOCUMENT
        ↓
AUDIT PACKAGE
```

LLM jest jednym z wykonawców procesu, a nie źródłem prawdy.

---

# 3. Architektura wysokiego poziomu

System dzielimy na dziewięć domen.

| Warstwa | Odpowiedzialność |
|---|---|
| Case Core | kanoniczny stan sprawy |
| Ingestion | dokumenty i dane wejściowe |
| Legal Knowledge | przepisy, orzecznictwo, źródła |
| Procedural Intelligence | wymogi proceduralne |
| Legal Reasoning | argumentacja i analiza |
| Document Engineering | konstrukcja pisma |
| Validation | kontrola jakości i ryzyka |
| Rendering | DOCX/PDF/HTML |
| Governance & Audit | wersjonowanie, provenance, audyt |

Żadna warstwa prezentacji nie może być źródłem danych dla domeny prawnej.

---

# 4. Case Core — serce systemu

Każde pismo musi należeć do konkretnego **Case**.

Case jest jedynym kanonicznym stanem sprawy.

```text
Case
 ├── Parties
 ├── Institutions
 ├── Proceedings
 ├── Documents
 ├── Facts
 ├── Evidence
 ├── Issues
 ├── Claims
 ├── Defences
 ├── LegalRules
 ├── Arguments
 ├── Requests
 ├── Deadlines
 ├── Risks
 ├── Drafts
 └── Decisions
```

Nie przechowujemy kluczowych informacji wyłącznie w naturalnym tekście.

Przykładowo:

```yaml
fact:
  id: FACT-0041
  statement: "Pozwany dokonał wpłaty 600 zł."
  date: 2026-02-10
  status: confirmed
  source:
    - EVID-0017
  confidence: 1.0
```

Dzięki temu zmiana faktu propaguje się przez cały system.

---

# 5. Kanoniczny model domenowy

Minimalny model powinien obejmować:

| Encja | Znaczenie |
|---|---|
| `Case` | sprawa |
| `Party` | strona/osoba |
| `Institution` | sąd, urząd, organ |
| `Proceeding` | postępowanie |
| `Filing` | pismo procesowe |
| `Fact` | twierdzenie o stanie faktycznym |
| `Evidence` | dowód |
| `Issue` | zagadnienie wymagające rozstrzygnięcia |
| `LegalSource` | źródło prawa |
| `LegalRule` | norma lub reguła |
| `Claim` | twierdzenie/roszczenie |
| `Defence` | stanowisko przeciwne |
| `Argument` | argument |
| `CounterArgument` | kontrargument |
| `Request` | żądanie/wniosek |
| `Deadline` | termin |
| `Risk` | ryzyko |
| `Citation` | odwołanie do źródła |
| `DocumentPlan` | plan dokumentu |
| `Section` | sekcja pisma |
| `Draft` | konkretna wersja |
| `ValidationFinding` | wynik kontroli |
| `Decision` | decyzja człowieka/systemu |

---

# 6. Relacje wiedzy

Relacje muszą być typowane.

Przykłady:

```text
FACT ──SUPPORTED_BY────► EVIDENCE

CLAIM ──SUPPORTED_BY───► FACT

CLAIM ──GOVERNED_BY────► LEGAL_RULE

ARGUMENT ──SUPPORTS────► CLAIM

ARGUMENT ──OPPOSES─────► CLAIM

COUNTERARGUMENT ───────► ARGUMENT

REQUEST ──BASED_ON─────► CLAIM

DOCUMENT_SECTION ──────► ARGUMENT

CITATION ──REFERS_TO───► LEGAL_SOURCE
```

Należy utrzymywać osobno:

**Knowledge Graph** — semantyka sprawy.

**Dependency DAG** — zależności wykonawcze i propagacja zmian.

Nie powinny być tym samym mechanizmem.

---

# 7. Ingestion Layer

Warstwa importu odpowiada za przekształcanie materiałów użytkownika do ustandaryzowanej postaci.

Źródła mogą obejmować:

PDF, DOCX, e-mail, obrazy, skany, tekst, ZIP akt, formularze oraz dane wprowadzone ręcznie.

Pipeline:

```text
UPLOAD
  ↓
FILE IDENTIFICATION
  ↓
TEXT / STRUCTURE EXTRACTION
  ↓
DOCUMENT CLASSIFICATION
  ↓
ENTITY EXTRACTION
  ↓
DATES / AMOUNTS / PARTIES
  ↓
FACT CANDIDATES
  ↓
EVIDENCE CANDIDATES
  ↓
CONTRADICTION CHECK
  ↓
HUMAN / MACHINE ACCEPTANCE
  ↓
CASE CORE
```

Informacja wydobyta przez AI nie staje się automatycznie faktem potwierdzonym.

Statusy przykładowe:

```text
CANDIDATE
EXTRACTED
REVIEWED
CONFIRMED
DISPUTED
REJECTED
```

---

# 8. Legal Knowledge Layer

Warstwa wiedzy prawnej nie może być zwykłym RAG-iem.

Powinna posiadać rejestr źródeł:

```text
LegalSourceRegistry
```

Każde źródło powinno przechowywać m.in.:

```text
source_id
jurisdiction
source_type
title
identifier
version
effective_from
effective_to
retrieved_at
source_uri
content_hash
authority_level
```

Oddzielamy:

```text
LAW
CASE LAW
OFFICIAL GUIDANCE
DOCTRINE
SECONDARY SOURCE
USER MATERIAL
```

System musi wiedzieć, jaka jest **siła źródła**, a nie tylko jego podobieństwo semantyczne.

---

# 9. Procedural Intelligence Engine

To jedna z najważniejszych warstw całego produktu.

Silnik proceduralny odpowiada na pytania:

```text
Czy właściwy jest ten sąd?
Czy pismo wymaga określonych elementów?
Czy istnieje termin?
Czy potrzebne są załączniki?
Czy należy podać wartość przedmiotu sporu?
Czy wymagany jest podpis?
Czy trzeba wskazać dowody?
Czy żądanie jest prawidłowo sformułowane?
```

Reguły powinny być maszynowo reprezentowane.

Przykład:

```yaml
rule:
  id: PROC-PL-CPC-001
  applies_to:
    document_type: civil_claim
  requirement:
    type: mandatory_field
    field: court
  severity: BLOCKER
```

Procedura nie może być pozostawiona wyłącznie ocenie LLM.

---

# 10. Legal Reasoning Engine

Silnik analizy prawnej powinien wykonywać sześć oddzielnych operacji:

```text
ISSUE SPOTTING

FACT-TO-LAW MAPPING

CLAIM CONSTRUCTION

ARGUMENT CONSTRUCTION

COUNTERARGUMENT ANALYSIS

REMEDY / REQUEST ANALYSIS
```

Wynik nie powinien być jednym tekstem.

Powstaje **Argument Graph**.

Przykład:

```text
ISSUE-07
│
├── CLAIM-12
│   ├── FACT-17
│   │   └── EVIDENCE-21
│   ├── FACT-19
│   │   └── EVIDENCE-29
│   └── LAW-08
│
├── ARGUMENT-14
│
├── COUNTERARGUMENT-06
│
└── RESPONSE-03
```

Dzięki temu dokument jest renderowaniem istniejącego rozumowania, a nie miejscem, w którym rozumowanie powstaje przypadkowo.

---

# 11. Document Planning Engine

Przed napisaniem pierwszego zdania musi powstać `DocumentPlan`.

Przykładowa struktura:

```yaml
document:
  type: response_to_claim

  objective:
    - dismissal

  sections:
    - heading
    - procedural_requests
    - position
    - factual_background
    - legal_arguments
    - evidence_requests
    - conclusion
    - attachments

  argument_order:
    - ARG-001
    - ARG-014
    - ARG-008
```

Plan określa:

- cel pisma,
- adresata,
- procesową funkcję dokumentu,
- zakres stanowiska,
- kolejność argumentów,
- dowody,
- żądania,
- strukturę.

Dopiero zatwierdzony plan trafia do generatora treści.

---

# 12. Controlled Drafting Engine

Drafting Engine pisze sekcjami, a nie jednym gigantycznym promptem.

Pipeline:

```text
DocumentPlan
    ↓
Section Contract
    ↓
Required Facts
    ↓
Required Evidence
    ↓
Required Legal Rules
    ↓
Allowed Claims
    ↓
Draft Section
    ↓
Citation Binding
    ↓
Validation
```

Każda sekcja otrzymuje jawny `SectionContract`.

Przykład:

```yaml
section:
  type: factual_background

  allowed_sources:
    - FACT
    - EVIDENCE

  forbidden:
    - unsupported_legal_conclusion

  required:
    - chronological_order
```

Minimalizuje to halucynacje i niekontrolowane rozszerzanie materiału sprawy.

---

# 13. Provenance Engine

Każde znaczące twierdzenie dokumentu powinno być możliwe do prześledzenia.

```text
Zdanie w dokumencie
        ↓
Argument
        ↓
Fact
        ↓
Evidence
        ↓
Source Document
        ↓
Page / paragraph / fragment
```

Analogicznie:

```text
Twierdzenie prawne
        ↓
LegalRule
        ↓
LegalSource
        ↓
Article / paragraph / decision
```

System powinien potrafić odpowiedzieć:

> „Skąd wzięło się to zdanie?”

Brak odpowiedzi oznacza defekt jakościowy.

---

# 14. Validation Engine

Walidacja powinna działać wielowarstwowo.

### V1 — Schema Validation

Sprawdzenie kompletności modeli danych.

### V2 — Fact Validation

Daty, kwoty, strony, zdarzenia.

### V3 — Evidence Validation

Czy twierdzenia mają wsparcie dowodowe.

### V4 — Legal Validation

Czy podstawa prawna istnieje i rzeczywiście wspiera twierdzenie.

### V5 — Procedural Validation

Czy spełnione są wymogi formalne.

### V6 — Logical Validation

Czy argumentacja nie zawiera sprzeczności.

### V7 — Document Validation

Czy struktura pisma jest kompletna.

### V8 — Linguistic Validation

Język, precyzja, profesjonalizm, redundancja.

### V9 — Adversarial Review

System próbuje podważyć własne pismo.

### V10 — Final Gate

Kontrola przed dopuszczeniem dokumentu do renderowania jako FINAL.

---

# 15. Severity Model

Każdy problem ma klasyfikację.

| Severity | Skutek |
|---|---|
| `INFO` | informacja |
| `WARNING` | potencjalny problem |
| `ERROR` | wymaga poprawy |
| `BLOCKER` | zakaz FINAL |
| `CRITICAL` | dokument procesowo niebezpieczny |

System działa **fail-closed**.

Jeżeli występuje `BLOCKER`, dokument nie otrzymuje statusu FINAL.

---

# 16. Status dokumentu

Należy jednoznacznie rozróżnić:

```text
PLANNED
GENERATED
VALIDATED
APPROVED
RENDERED
CERTIFIED
```

Nigdy:

```text
GENERATED == VALIDATED
```

ani:

```text
VALIDATED == CERTIFIED
```

---

# 17. Adversarial Legal Review

Przed finalizacją system powinien wykonać kontrolę z punktu widzenia:

```text
przeciwnika procesowego
sądu
organu
pełnomocnika profesjonalnego
audytora formalnego
```

Pytania kontrolne:

```text
Który argument jest najsłabszy?

Które twierdzenie można łatwo zakwestionować?

Które żądanie nie ma podstawy?

Jakich dowodów brakuje?

Czy dokument sam sobie przeczy?

Czy przeciwnik posiada oczywistą ripostę?

Czy argument faktyczny został przedstawiony jako prawny?

Czy w dokumencie pojawia się fakt niewystępujący w aktach?
```

---

# 18. Renderer Architecture

Renderer nie zna logiki prawnej.

Otrzymuje wyłącznie:

```text
SemanticDocument
+
RenderProfile
```

Przykład:

```text
SemanticDocument
 ├── Header
 ├── Parties
 ├── Requests
 ├── Sections
 ├── Paragraphs
 ├── Quotes
 ├── EvidenceReferences
 ├── Attachments
 └── Signature
```

Renderer odpowiada tylko za reprezentację.

Formaty docelowe:

```text
DOCX
PDF
HTML
TXT / Markdown
```

W przyszłości:

```text
ePUAP-ready
e-Doręczenia
court electronic filing
```

---

# 19. Nowy system wizualny

Nie ustanawiamy obecnie żadnego poprzedniego wzorca jako standardu.

Powstaje niezależny:

```text
LUKART Legal Document Design System
```

Rozdzielony na dwa obszary.

### A. Application Design System

Interfejs programu.

### B. Legal Document Design System

Wygląd wygenerowanych pism.

To dwie różne rzeczy.

Dokument prawny nie powinien wyglądać jak interfejs aplikacji.

---

# 20. Legal Document Design Tokens

Zamiast twardego formatowania:

```text
font_size = 11
margin = 22 mm
bold = true
```

stosujemy tokeny semantyczne:

```text
document.body
document.heading.primary
document.heading.secondary
document.metadata
document.party_block
document.request
document.legal_basis
document.quote
document.signature
document.attachment
```

Dopiero `RenderProfile` przypisuje im parametry wizualne.

Pozwala to stworzyć np.:

```text
COURT_PL
OFFICIAL_PL
PRE_LITIGATION_PL
INTERNAL_LEGAL_MEMO
```

bez zmiany danych ani argumentacji.

---

# 21. Interfejs użytkownika

Workbench powinien być **case-centric**, nie „chat-centric”.

Główny ekran:

```text
CASE
│
├── Overview
├── Timeline
├── Parties
├── Documents
├── Facts
├── Evidence
├── Legal Issues
├── Arguments
├── Deadlines
├── Documents to Generate
└── Audit
```

Chat AI może istnieć jako narzędzie pomocnicze.

Nie może być centralnym modelem aplikacji.

---

# 22. Generator Workflow

Docelowy przepływ użytkownika:

```text
1. Utwórz / otwórz sprawę

2. Dodaj materiały

3. System wydobywa dane

4. Użytkownik zatwierdza kluczowe fakty

5. System identyfikuje problemy prawne

6. Powstaje Fact–Evidence Matrix

7. Powstaje Legal Matrix

8. Powstaje Argument Graph

9. Użytkownik wybiera cel dokumentu

10. Generator przygotowuje DocumentPlan

11. Powstaje pierwszy draft

12. Walidacja

13. Adversarial Review

14. Poprawki

15. Human Approval

16. Rendering

17. Final Validation

18. Final / Certified
```

---

# 23. Fact–Evidence Matrix

Jeden z głównych ekranów systemu powinien przedstawiać:

| Fact | Status | Evidence | Opponent disputes | Used in |
|---|---|---|---|---|
| FACT-01 | confirmed | EVID-02 | no | ARG-03 |
| FACT-02 | disputed | EVID-08 | yes | ARG-05 |
| FACT-03 | unsupported | — | unknown | — |

To szybko pokazuje, czego brakuje w sprawie.

---

# 24. Issue Matrix

Drugim kluczowym artefaktem będzie:

| Issue | Our position | Opponent | Law | Evidence | Risk |
|---|---|---|---|---|---|
| ISSUE-01 | positive | negative | LAW-04 | EVID-06 | medium |

Pozwala oceniać sprawę przed napisaniem dokumentu.

---

# 25. Argument Matrix

Każdy argument otrzymuje ocenę:

```text
LEGAL SUPPORT
FACTUAL SUPPORT
EVIDENCE SUPPORT
COUNTERARGUMENT EXPOSURE
PROCEDURAL RELEVANCE
OVERALL CONFIDENCE
```

Nie chodzi o sztuczne „87% szans na wygraną”.

Chodzi o mierzalną jakość konstrukcji argumentu.

---

# 26. Human-in-the-loop

Człowiek powinien zatwierdzać przede wszystkim:

```text
tożsamość stron
kluczowe fakty
strategię procesową
żądania
sporne interpretacje
finalny dokument
```

System może automatyzować operacje techniczne i analityczne, ale nie powinien ukrywać istotnych decyzji prawnych.

---

# 27. Audit Trail

Każda istotna operacja powinna generować zapis:

```text
event_id
case_id
actor
timestamp
operation
input_hash
output_hash
model/provider
rule_version
source_versions
```

Dzięki temu możliwe jest odtworzenie:

> kto, kiedy, na jakiej podstawie i przy użyciu jakiej wersji systemu wygenerował określony fragment.

---

# 28. Versioning

Wersjonowane muszą być niezależnie:

```text
Case
Facts
Evidence
Legal Sources
Rules
Prompts
Models
Document Plans
Drafts
Render Profiles
Validators
```

Dokument finalny musi wskazywać dokładny snapshot danych, z których powstał.

---

# 29. Storage Architecture

Rekomendowana architektura danych:

```text
PostgreSQL
    ↓
canonical structured state

Object Storage
    ↓
original files / generated artifacts

Search Index
    ↓
full-text retrieval

Vector Index
    ↓
semantic retrieval

Knowledge Graph
    ↓
semantic relationships

Audit Store
    ↓
immutable operation history
```

Vector database nie jest źródłem prawdy.

Jest indeksem pomocniczym.

---

# 30. Architektura aplikacyjna

Na etapie budowy rekomendowany jest:

**modularny monolit z rygorystycznymi granicami domenowymi**.

Nie mikroserwisy.

Proponowany podział:

```text
lukart_work/
│
├── domain/
│   ├── case/
│   ├── facts/
│   ├── evidence/
│   ├── legal/
│   ├── argumentation/
│   └── documents/
│
├── ingestion/
│
├── knowledge/
│
├── procedural/
│
├── reasoning/
│
├── planning/
│
├── drafting/
│
├── validation/
│
├── rendering/
│
├── audit/
│
├── registry/
│
├── integrations/
│
├── api/
│
└── ui/
```

Granice modułów muszą być silniejsze niż wygoda importów.

---

# 31. Contract-first architecture

Komunikacja między modułami powinna odbywać się poprzez jawne kontrakty.

Przykład:

```python
class GenerateDocumentCommand:
    case_id: UUID
    document_type: DocumentType
    objective_ids: list[UUID]
    snapshot_id: UUID
```

a nie:

```python
generate_document(case)
```

Kontrakt musi określać, czego operacja faktycznie potrzebuje.

---

# 32. Model Registry

Wykorzystanie AI powinno być kontrolowane przez:

```text
ModelRegistry
ProviderRegistry
CapabilityRegistry
PromptRegistry
```

Generator nie powinien być związany z jednym modelem.

Dla operacji można określać profile:

```text
EXTRACTION
LEGAL_REASONING
DRAFTING
ADVERSARIAL_REVIEW
LANGUAGE_REVIEW
```

Każdy profil może używać innego modelu i parametrów.

---

# 33. Prompt Registry

Prompty są elementem systemu i podlegają wersjonowaniu.

```text
prompt_id
version
task
input_contract
output_contract
model_constraints
hash
tests
status
```

Zmiana promptu jest zmianą produkcyjną.

Nie edycją tekstu „gdzieś w kodzie”.

---

# 34. Structured AI Output

AI powinno zwracać obiekty zgodne ze schematami.

Nie:

```text
„Moim zdaniem należałoby...”
```

lecz:

```json
{
  "issue_id": "ISSUE-14",
  "arguments": [],
  "missing_evidence": [],
  "risks": [],
  "confidence": "medium"
}
```

Tekst naturalny jest generowany dopiero tam, gdzie jest faktycznie potrzebny.

---

# 35. Safety / No-Hallucination Architecture

System powinien posiadać trzy klasy twierdzeń:

```text
SOURCE_BACKED
INFERRED
UNSUPPORTED
```

`UNSUPPORTED` nie może po cichu znaleźć się w dokumencie finalnym.

Inference musi być oznaczone.

Przy braku wystarczających danych system powinien używać:

```text
ABSTAIN
```

zamiast wymyślania odpowiedzi.

---

# 36. Privacy Architecture

Dane prawne wymagają traktowania jako danych wysokiej wrażliwości.

Wymagane architektonicznie:

```text
case isolation
role-based access
encryption at rest
encryption in transit
secret management
audit trail
controlled model routing
data retention rules
artifact deletion
PII-aware logging
```

Pełna treść dokumentów nie może trafiać do zwykłych logów aplikacyjnych.

---

# 37. Test Architecture

Testowanie powinno obejmować więcej niż unit testy.

```text
UNIT
DOMAIN CONTRACT
RULE TESTS
PIPELINE
REGRESSION
GOLDEN CASE
ADVERSARIAL
RENDER
SECURITY
END-TO-END
```

Szczególnie ważny będzie katalog:

```text
tests/golden_cases/
```

Każdy przypadek zawiera:

```text
input
expected facts
expected issues
expected procedural requirements
expected document structure
forbidden outputs
```

---

# 38. Golden Case Regression

Każda istotna zmiana modelu, promptu lub reguły musi być testowana na historycznych sprawach.

System powinien móc powiedzieć:

```text
wersja A:
12/12 procedural requirements PASS

wersja B:
11/12 PASS

REGRESSION DETECTED
```

Ocena „tekst wygląda lepiej” nie jest wystarczającym testem.

---

# 39. Quality Gate dokumentu

Dokument otrzymuje status FINAL tylko wtedy, gdy:

| Kontrola | Warunek |
|---|---|
| schema | PASS |
| facts | PASS |
| evidence | PASS |
| legal basis | PASS |
| procedure | PASS |
| contradictions | PASS |
| citations | PASS |
| requests | PASS |
| language | PASS |
| render | PASS |
| blockers | 0 |

W przeciwnym przypadku pozostaje DRAFT.

---

# 40. Integracja z LUKART ROS

LUKART WORK powinien być autonomiczną domeną produktową, ale wykorzystywać LUKART ROS przez kontrakty.

```text
                 LUKART ROS
                     │
              Integration Boundary
                     │
          ┌──────────┴───────────┐
          │                      │
   LUKART WORK CORE        External Providers
```

Istniejące komponenty ROS mogą zostać wykorzystane przez adaptery, ale nie mogą być kopiowane bezpośrednio do nowej domeny.

Przykładowe interfejsy:

```text
KnowledgeProvider
ValidationProvider
ReasoningProvider
DocumentProvider
ModelProvider
EvidenceProvider
```

To pozwala korzystać z możliwości ROS bez trwałego sprzężenia obu produktów.

---

# 41. Source of Truth

Hierarchia prawdy:

```text
SOURCE DOCUMENT
        ↓
CANONICAL CASE DATA
        ↓
LEGAL / PROCEDURAL KNOWLEDGE
        ↓
ARGUMENT GRAPH
        ↓
DOCUMENT MODEL
        ↓
RENDERED DOCUMENT
```

DOCX ani PDF nie są źródłem prawdy.

Są artefaktem wynikowym.

---

# 42. Change Propagation

Zmiana faktu:

```text
FACT-17 changed
       ↓
affected evidence relations
       ↓
affected claims
       ↓
affected arguments
       ↓
affected sections
       ↓
draft marked STALE
```

System musi wskazywać dokumenty wymagające ponownej generacji.

Nie wolno pozostawiać starego argumentu po zmianie danych wejściowych.

---

# 43. Reproducibility

Każdy draft powinien posiadać:

```text
case_snapshot_hash
knowledge_snapshot
rule_set_version
prompt_versions
model_versions
render_profile_version
generator_version
```

Dzięki temu możliwe jest odtworzenie warunków jego powstania.

---

# 44. Wewnętrzny pakiet wynikowy

Generator nie powinien produkować tylko:

```text
pismo.pdf
```

Powinien generować:

```text
CASE-0001/
│
├── final.docx
├── final.pdf
├── document.json
├── validation.json
├── sources.json
├── evidence-map.json
├── argument-map.json
└── audit.json
```

Dla użytkownika może być widoczny tylko DOCX/PDF.

Pozostałe artefakty zapewniają audytowalność.

---

# 45. Poziomy działania generatora

System powinien obsługiwać trzy tryby.

| Tryb | Cel |
|---|---|
| QUICK | proste pismo z kontrolą podstawową |
| PROFESSIONAL | pełna analiza i walidacja |
| FORENSIC | maksymalny audyt, kontrargumentacja i provenance |

Nie należy jednak budować trzech różnych generatorów.

To jeden pipeline z różną głębokością wykonania.

---

# 46. Definition of Done dla pojedynczego pisma

Pismo jest zakończone dopiero wtedy, gdy istnieje:

```text
zaakceptowany Case Snapshot
zaakceptowany DocumentPlan
Draft
Fact Validation
Evidence Validation
Legal Validation
Procedural Validation
Adversarial Review
Final Render
Audit Record
```

Samo wygenerowanie treści oznacza jedynie:

```text
DRAFT CREATED
```

---

# 47. Definition of Done dla funkcji systemu

Nowy moduł generatora jest ukończony dopiero po:

```text
IMPLEMENTED
        ↓
UNIT TESTED
        ↓
INTEGRATION TESTED
        ↓
GOLDEN CASE TESTED
        ↓
REGRESSION TESTED
        ↓
DOCUMENTED
        ↓
ARCHITECTURE REVIEWED
        ↓
MERGED
        ↓
POST-MERGE VALIDATED
```

---

# 48. Architektoniczne zakazy

System nie powinien dopuszczać następujących wzorców:

```text
LLM → FINAL DOCUMENT

PDF → źródło prawdy

UI state → Case state

prompt → nieustrukturyzowany JSON „na słowo honoru”

cytat bez source_id

fakt bez provenance

podstawa prawna bez wersji źródła

FINAL przy istniejącym BLOCKER

automatyczna zmiana strategii procesowej bez śladu

kopiowanie poprzedniego layoutu jako standardu
```

---

# 49. Minimalna architektura pierwszej wersji

Pierwsza realnie użyteczna wersja nie potrzebuje wszystkich docelowych mechanizmów.

P0 powinien zawierać:

```text
Case Core
Document ingestion
Facts
Evidence
Timeline
Document type registry
DocumentPlan
Controlled Drafting
Basic procedural rules
Validation Engine
DOCX Renderer
PDF Renderer
Audit Trail
```

Dopiero później:

```text
advanced Legal Knowledge
argument graph automation
case-law reasoning
adversarial agents
advanced strategy analysis
automated change propagation
electronic filing integrations
```

---

# 50. Kolejność budowy

Rekomendowana sekwencja realizacji:

```text
00  Architecture
01  Domain Model
02  Case Core
03  Storage + Versioning
04  Ingestion
05  Facts / Evidence
06  Document Registry
07  Procedural Engine
08  Document Planner
09  Drafting Engine
10  Validation Engine
11  Rendering Engine
12  Audit / Provenance
13  Workbench UI
14  Legal Knowledge
15  Argument Engine
16  Adversarial Review
17  Golden Case Framework
18  Security / Privacy Hardening
19  ROS Integration
20  Production Certification
```

---

# 51. Pierwszy techniczny milestone

Pierwszym pełnym end-to-end scenariuszem powinien być:

```text
CASE-0001
     ↓
dodanie dokumentów
     ↓
ekstrakcja stron / dat / faktów
     ↓
zatwierdzenie danych
     ↓
wybór rodzaju pisma
     ↓
DocumentPlan
     ↓
draft
     ↓
walidacja
     ↓
DOCX
     ↓
PDF
     ↓
audit package
```

Nie zaczynamy od rozbudowanego dashboardu.

Nie zaczynamy od designu PDF.

Nie zaczynamy od kilkudziesięciu agentów.

Najpierw dowodzimy pełny przepływ produktu.

---

# 52. Decyzja dotycząca architektury bazowej

Dla LUKART WORK przyjmuję następującą architekturę referencyjną:

```text
                 ┌─────────────────────┐
                 │       WORKBENCH     │
                 └──────────┬──────────┘
                            │
                     Application API
                            │
       ┌────────────────────┼─────────────────────┐
       │                    │                     │
   CASE CORE          DOCUMENT ENGINE        AUDIT CORE
       │                    │                     │
       ├────────────┐       │                     │
       │            │       │                     │
 FACT/EVIDENCE   PROCEDURAL │                     │
       │            │       │                     │
       └─────┬──────┘       │                     │
             │              │                     │
        REASONING ─────► DOCUMENT PLAN            │
             │              │                     │
             │          DRAFT ENGINE              │
             │              │                     │
             └────────► VALIDATION ◄──────────────┘
                            │
                      SEMANTIC DOCUMENT
                            │
                         RENDERER
                       ┌────┴─────┐
                      DOCX       PDF
```

Pod spodem:

```text
Canonical Store
Knowledge Store
Object Store
Search Index
Audit Store
Model Registry
Rule Registry
Prompt Registry
```

---

# 53. Fundamentalna właściwość produktu

Największą wartością LUKART WORK nie powinno być:

> „AI potrafi napisać pozew.”

Takie rozwiązania można zbudować stosunkowo łatwo.

Przewagą systemu powinno być:

> **LUKART WORK potrafi wykazać, dlaczego każdy istotny element pisma się w nim znajduje, na jakich faktach, dowodach i źródłach prawa się opiera, jakie posiada słabości oraz czy dokument spełnia warunki dopuszczenia do użycia.**

To zmienia produkt z generatora tekstu w **Legal Document Engineering System**.

---

# 54. Status architektury 00

Na poziomie architektury bazowej przyjmujemy:

```text
ARCHITECTURE BASELINE: ESTABLISHED

CASE-CENTRIC: YES
EVIDENCE-AWARE: YES
LAW-AWARE: YES
PROCEDURE-AWARE: YES
PROVENANCE-AWARE: YES
FAIL-CLOSED: YES
AUDITABLE: YES
VERSIONED: YES
MODEL-INDEPENDENT: YES
RENDERER-INDEPENDENT: YES
CLEAN-SLATE VISUAL SYSTEM: YES
ROS-INTEGRATION READY: YES
```

**Następny etap: `01 — Domain Model & Contracts`.**

Powinien on zamienić powyższą architekturę w konkretne, wersjonowane modele `Case`, `Fact`, `Evidence`, `Issue`, `Claim`, `Argument`, `Request`, `LegalSource`, `DocumentPlan`, `Draft` i `ValidationFinding`, wraz z relacjami, identyfikatorami, lifecycle oraz kontraktami wejścia/wyjścia.