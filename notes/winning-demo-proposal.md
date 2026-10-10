# Winning implementation plan

> Archived proposal from `49cd253`. Current build scope: [implementation plan](../IMPLEMENTATION_PLAN.md).

Ja – Pipeline zuerst und 3D als Abschluss ist genau die richtige Reihenfolge. Die stärkste Positionierung wäre:

> Ein „BMW Requirement Twin“, der Kundenevidenz in versionierte, priorisierte und überprüfbare Anforderungen übersetzt – und anschließend am 3D-Fahrzeug zeigt, wo diese Anforderungen das Kundenerlebnis verändern.

Nicht: „AI empfiehlt dem Kunden ein Auto.“<br>
Sondern: „AI hilft dem PM, die nächste Fahrzeuggeneration zu definieren.“

## Meine Analyse

Das bestehende Repository enthält gute Research-Arbeit, Dateninventar und einen konzeptionell sinnvollen Plan. Es enthält aber noch keinen ausführbaren Prototyp: keine Anwendung, Schemas, Datenbank, Pipeline oder Tests. Der größte nächste Schritt ist daher ein vollständiger vertikaler Durchlauf statt weiterer Research-Dokumentation.

BMWs Material beschreibt eindeutig diese Kette:

`Situation Analysis → Structure & Context → Requirement Definition → Prioritization → Documentation & Tracking`

Dazu kommen die wichtigsten Bewertungspunkte: erklärbares Scoring, Human-in-the-loop, vollständige Rückverfolgbarkeit und ehrlicher Umgang mit Unsicherheit.

Quellen: [BMW Product Management Keynote](../materials/261010_BMW_Product_Management_Key_Note.pptx), [BMW Hackathon Briefing](../materials/BMW_Hackathon_Briefing_Short.pdf), [BMW team guidance](bmw-guidance.md) und [authoritative challenge requirements](challenge.md).

## Empfohlener Demo-Scope

Nehmt zunächst:

- Fahrzeug: BMW G60
- Derivative: i5 M60 xDrive
- Markt: USA
- Horizont: Nachfolgegeneration in drei bis fünf Jahren

Warum:

- G60/USA besitzt 4.365 Feedback-Zeilen und 3.610 unterschiedliche Feedback-IDs.
- Die sichtbaren Stärken sind insbesondere Antrieb, Handling und Exterieurdesign.
- Relevante Problemfelder sind Sitze, elektrische Reichweite, öffentliches Laden und Bedienkonzept.
- 72,7 % der US-Feedback-IDs kommen allerdings aus „Source B“. Deshalb dürfen die Zahlen nicht als Marktprävalenz dargestellt werden.

Die Datengrundlage und ihre Einschränkungen sind im [Research Review](../research/RESEARCH.md) dokumentiert. Die BMW-Eingabedaten selbst bleiben gemäß BMWs Vorgabe in `.gitignore`; Dateinamen, Hashes und Source-IDs stehen im [Source Inventory](source-inventory.json).

Der Annual Report unterstützt diesen Scope: 5er/6er-Auslieferungen stiegen 2025 um 19,5 %, elektrifizierte Fahrzeuge erreichten 26,1 % der Auslieferungen, und fast jeder zehnte BMW war ein M-Modell. Das macht den i5 M60 zu einem plausiblen Demo-Anker – nicht zu einer bewiesenen optimalen Produktentscheidung. Quelle: [BMW Group Report 2025](https://www.bmwgroup.com/content/dam/grpw/websites/bmwgroup_com/ir/downloads/en/2026/bericht/BMW-Group-Report-2025-en.pdf).

## Zielarchitektur

```text
Excel / PDF / Web
        ↓
Raw Source Registry
        ↓
Evidence Spans
        ↓
Consolidated Findings
        ↓
Customer Need
        ↓
Requirement Version
        ↓
Deterministic Score + Evidence Grade
        ↓
PM Decision
        ↓
Append-only Audit Trail
        ↓
3D Requirement Hotspot
```

Empfohlener Stack:

- Next.js, React und TypeScript für die PM-Oberfläche
- FastAPI, Python und Pydantic für Import und AI-Pipeline
- SQLite für den Hackathon, später PostgreSQL
- strukturierte LLM-Ausgaben per JSON-Schema
- React Three Fiber für die abschließende 3D-Ansicht
- Caching anhand von Source-Hash und Prompt-Version, damit API-Credits nicht bei jedem Lauf erneut verbraucht werden

Kein Microservice-Netz, keine Graphdatenbank und kein Multi-Agent-System für den MVP.

## Build-Plan

### P0 – der bewertbare Kern

#### 1. Source Registry bauen

Jede Datei, Tabellenzeile und Webquelle erhält:

- `source_id`
- Datei-Hash
- Fahrzeug und Markt
- Zeile, Seite oder URL
- Importzeitpunkt
- verfügbare Zeitinformation
- Vertrauens- und Abhängigkeitskennzeichen

#### 2. Evidenz extrahieren

Das Modell liefert pro exaktem Textausschnitt:

- Signaltyp: Like, Defect, Difficult to Use, Want, Trend, Competitor Advantage
- Kundenbedürfnis
- Fahrzeugbereich
- Markt und Antrieb
- Schweregrad
- unterstützend oder widersprechend
- exakte Quellenreferenz

Zählen, Filtern und Deduplizieren übernimmt deterministischer Code, nicht das LLM.

#### 3. Anforderungen formulieren

Bedürfnis, Lösung und Messung bleiben getrennt:

- Need: „Der Kunde möchte auf Langstrecken Vertrauen in Reichweite und Laden haben.“
- Candidate response: verbesserte Ladeplanung und zuverlässigere Stationsinformationen.
- Acceptance test: messbarer Kundentest mit klarer Erfolgsgrenze.

Jeder numerische Zielwert muss entweder eine Quelle oder `PM assumption` tragen.

#### 4. Scoring implementieren

Beispiel:

`Priority = 35 % Customer Impact + 25 % Market Relevance + 20 % Strategic Fit + 10 % Differentiation + 10 % Feasibility`

Davon getrennt:

- Evidence Grade A–D
- Source Coverage
- Source Diversity
- Consistency
- Conflict Flag
- Uncertainty Notes

Wichtig: Ein hoher Wert mit schwacher Evidenz muss sichtbar anders aussehen als ein hoher Wert mit starker Evidenz.

#### 5. PM Workspace

Vier Kernaktionen:

- Approve
- Edit
- Reject
- Postpone/Challenge

Eine Änderung erzeugt immer eine neue Requirement-Version. Alte Versionen bleiben unverändert.

#### 6. Audit Trail

Jedes Event speichert:

- Actor: PM, AI oder System
- Action und Timestamp
- Before/After JSON
- Begründung
- betroffene Quellen
- Modell-, Prompt- und Schema-Version
- Score-Gewichte
- relevante Zugriffsereignisse

### P1 – der Winning Layer

- EU/China/USA-Vergleich
- Market-weighted Scoring
- Konflikterkennung zwischen Märkten
- kontrollierter Update-Replay
- Impact Detection: Welche genehmigten Anforderungen müssen neu geprüft werden?

Da die Feedbackdaten keine Zeitstempel enthalten, darf der Replay nicht als historischer Backtest verkauft werden. Zeigt ihn ehrlich als simulierten neuen Feedback-Batch. Genau diese Transparenz wird laut BMW ausdrücklich belohnt.

### P2 – 3D Requirement Twin

Die 3D-Ansicht sollte Anforderungen räumlich erklären:

- Sitz-Hotspot → Komfort, Materialien, Ergonomie
- Cockpit-Hotspot → iDrive, Displays, Bedienbarkeit
- Ladeport/Batterie → Reichweiten- und Ladeerlebnis
- Karosserie → Raumgefühl und Design
- Farben zeigen Priorität, Status oder Evidenzniveau
- Klick öffnet Quellen, Score, Annahmen und Audit-Historie

Der Prompt „make it more luxurious“ sollte nicht bloß das Auto von i5 auf i7 wechseln. Besser:

1. System interpretiert „luxury“ als Seat Comfort, Material Quality, Acoustic Comfort, Rear Experience und Digital Experience.
2. G60-Anforderungen werden gegen G70-Evidenz verglichen.
3. Betroffene Hotspots leuchten auf.
4. Der PM entscheidet, welche Anforderungen für den G60-Nachfolger übernommen werden.

Das G70-Kundenstudium eignet sich dabei als Benchmark für Sitzkomfort und Fond-Erlebnis. Die zugrunde liegende Arbeitsmappe `F70_G60_G68_G70_customer_studies.xlsx` bleibt als BMW-Eingabedatei aus Git ausgeschlossen und ist im [Source Inventory](source-inventory.json) verzeichnet.

Kleine Modellkorrektur: Die elektrischen Performance-Modelle heißen i5 M60 xDrive und i7 M70 xDrive.

## Beispielanforderung

**REQ-G60-US-CHG-001**

> The successor vehicle shall enable a first-time EV customer in the US to identify a compatible and available public charging location and integrate it into an active route without leaving the BMW navigation experience.

Dazu:

- Evidence: 38 Feedback-IDs zu Public Charging, weitere 46 zu Electric Range
- Acceptance: beispielsweise 90 % erfolgreicher Abschluss eines validierten Reiseplanungs-Tests
- Assumption: Der Wert von 90 % ist PM-definiert, nicht aus den Feedbackdaten abgeleitet
- Uncertainty: ausgewähltes, undatiertes Feedback; Quellenabhängigkeit
- Status: Proposed
- 3D hotspot: Ladeport/Cockpit
- PM action: Edit target → Approve
- Audit: vollständiger Before/After-Diff

## Fünf-Minuten-Demo

1. G60 / i5 M60 / USA auswählen.
2. Stärken, Pain Points und Datenlimits zeigen.
3. Ein Originalfeedback öffnen und daraus die Requirement-Kette verfolgen.
4. Score, Evidence Grade und Konflikte erklären.
5. PM ändert Acceptance Target und genehmigt die Anforderung.
6. Neuer Feedback-Batch verändert die Priorität und erzeugt „Needs review“.
7. 3D-Modell zeigt die betroffenen Fahrzeugbereiche.

Damit treffen wir alle fünf BMW-Bewertungskategorien direkt.

## Bewertungskriterien und Demonstrationsbeleg

| BMW-Kriterium | Was wir im Prototyp zeigen |
| --- | --- |
| Decision and Scoring Logic | Deterministische Gewichtung, getrenntes Evidence Grade, Konflikte, Unsicherheiten und nachvollziehbare Score-Runs. |
| Workflow and Human Decision-Making | Klare PM-Gates für Edit, Approve, Reject und Postpone sowie eine gezielte erneute Prüfung bei relevanten Updates. |
| Traceability and Auditability | Rückverfolgung vom 3D-Hotspot und Requirement über Finding und Evidence Span bis zur Originalquelle; append-only Before/After-Historie. |
| Solution Quality, Usability, and Feasibility | Ein enger G60/US-Vertical-Slice mit realer Datenpipeline, wenigen klaren PM-Screens und einem relationalen Datenmodell. |
| Innovation, Scalability, and Business Impact | Kontinuierlicher Requirement Twin über zwei Jahre, marktübergreifender Vergleich, Change Impact und räumliche 3D-Erklärung. |

## Qualitäts- und Abnahmekriterien

- 100 % der demonstrierten Requirements lassen sich auf konkrete Evidence Spans zurückführen.
- Gleiche Eingaben, Gewichtungen und Versionen erzeugen denselben Score.
- Kein numerischer Zielwert ohne Quelle oder explizite `PM assumption`.
- Jede PM-Änderung erzeugt eine neue unveränderliche Version und ein Audit Event.
- Ein kontrollierter Update-Batch verändert nur tatsächlich betroffene Findings, Requirements und Score-Runs.
- Materiale AI-Claims werden vor der Demo manuell auf Quellenunterstützung geprüft.
- Die Demonstration unterscheidet klar zwischen Sample Counts, Marktprävalenz, Annahmen und bestätigten Fakten.

## Bewusste Kürzungen

Für den MVP nicht bauen:

- keinen vollständigen offenen Web-Crawler
- keine autonome Requirement-Freigabe
- keine erfundenen Kunden- oder Marktwahrscheinlichkeiten
- keine technischen Komponenten- oder Architekturanforderungen
- keine Preis-, Kosten- oder Business-Case-Berechnung
- keine vollständige BMW-Modellpalette
- keine fotorealistische generative 3D-Geometrie
- keine zusätzliche Agenten- oder Graph-Infrastruktur ohne belegbaren Demo-Nutzen

Die 3D-Idee ist stark – aber nur als visuelle Oberfläche für ein glaubwürdiges Requirement- und Decision-System. Der eigentliche Winning-Moment ist, wenn ein Juror auf einen Hotspot klickt und innerhalb von Sekunden von der Fahrzeugstelle bis zum Originalfeedback, Score, PM-Entscheid und Audit-Ereignis zurückgehen kann.
