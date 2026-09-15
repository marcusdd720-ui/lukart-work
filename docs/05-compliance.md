# Architecture 00 compliance matrix

Aktualizacja po remediation: deterministyczne poprawki AGR-01-001–007 i ich regresje opisuje 07-stage01-remediation.md. Poniższa macierz pozostaje opisem zakresu etapów, nie nową decyzją GO. Poprzedni niezależny review zakończył się NO-GO; po naprawie wymagany jest kolejny niezależny review.

D = DESIGNED; I = IMPLEMENTED (lokalny zakres kontraktów); V = wykonane testy tego zakresu. „Boundary” nie oznacza implementacji danego silnika. Ścieżki względne względem pakietu.

| Baseline | Wymóg | Odwzorowanie etapu 01 | Stan / ograniczenie |
|---|---|---|---|
| §1–2 | pipeline, LLM nie jest prawdą | AIProposal, Case→Plan→Draft→ValidationRun | D/I; pipeline produktu nie uruchomiony |
| §3–4 | Case Core i separacja warstw | Entity scope, aggregate matrix, brak UI w modelach | D/I/V |
| §5 | 23 kanoniczne encje | domain/models.py, 23 schemas | D/I/V |
| §6 | KG oddzielny od DAG | KnowledgeEdge, DependencyEdge, KG_PAIRS, affected | D/I/V |
| §7 | candidate nie jest confirmed | Fact statuses, AIProposal, acceptance guard | D/I/V |
| §8 | source registry i wersje prawa | LegalSource + VersionPin + effective_period | D/I; brak resolvera prawa |
| §9 | formalne reguły maszynowe | LegalRule.Requirement | D/I; procedural evaluator poza zakresem |
| §10 | issue/claim/argument/counterargument/request | 6 encji i relacje | D/I; brak automatycznego reasoning engine |
| §11–12 | zatwierdzony plan i section contracts | DocumentPlan, Section, validate_state/validate_ai | D/I; generacja nie uruchomiona |
| §13 | trace do źródła i fragmentu | Provenance, SourceAnchor, Locator, Statement refs | D/I/V; semantyczna coverage później |
| §14–15 | V1–V10 i fail-closed | ValidationRun, Finding, evaluate_release | D/I/V syntetycznych rezultatów |
| §16 | statusy nie są równoważne | Draft lifecycle + ADR-01 | D/I/V |
| §17 | adversarial review | mandatory check adversarial, test specification | D/I kontraktu; review prawnicze nie wykonane |
| §18–20 | semantic rendering i clean slate | SemanticDocument, RenderRequest, profile pin | D/I boundary; żadnego layoutu |
| §21–25 | Case-centric i macierze | classification + relations, Query boundary | D; projekcje UI nieimplementowane |
| §26 | human approval | Decision, ACCEPTANCE guards | D/I/V części guardów |
| §27–28 | audyt i wersjonowanie | AuditEvent, immutable revisions, snapshot | D/I/V; brak trwałego audit store |
| §29–30 | storage i modularny monolit | module boundaries + transaction specification | D; bez zmiany architektury na mikroserwisy |
| §31 | contract-first | 6 command variants, query, result, events | D/I |
| §32–34 | registry pins, AI structured | ReproductionManifest, AIRequest/AIResult | D/I/V |
| §35 | unsupported/inferred/abstain | Support, Statement, AIResult, gate | D/I/V; semantyczny checker poza zakresem |
| §36 | privacy i case isolation | scope in models, tests, RLS/logging requirements | D/I/V kontraktowe; hardening nieukończony |
| §37–38 | tests i golden regression | unittest + synthetic golden + integration spec | I/V lokalne; nie pełny framework produktu |
| §39 | FINAL tylko po wszystkich kontrolach | REQUIRED_CHECKS + hashes/findings/approval/freshness | I/V pure evaluator, nie production release service |
| §40 | ROS przez adapter | brak importu ROS; jawne porty | D boundary; integracja 19 |
| §41 | hierarchy of truth | classification table i źródłowe bytes | D/I |
| §42 | change propagation | affected + FreshnessAssessment | I/V DAG; brak durable invalidation |
| §43–44 | reproducibility i audit package | manifest, snapshot, SemanticDocument | D/I; końcowy audit package pisma niepowstały |
| §45 | trzy profile, jeden pipeline | GenerateDocument.profile | D/I; profile nie zmniejszają minimalnego FINAL gate |
| §46 | DoD pisma | wymagania release service | D; żadne pismo nie zostało ukończone |
| §47 | DoD modułu z merge i post-merge | reports/status.json + 06-status.md | nie spełniono całości |
| §48 | zakazy | strict contracts, scope, immutable, gate | I/V wybranych prób; dalsze I01–I20 |
| §49–51 | P0 i kolejność budowy | tylko domain/contracts + checks | D/I; następny etap 02, nie dashboard |
| §52–54 | architektura referencyjna i baseline | brak nowych domen/silników poza supporting contracts | zgodne na poziomie projektu; brak niezależnego review |
