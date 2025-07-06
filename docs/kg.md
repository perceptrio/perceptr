# Product Requirements Document

## 1. Document Control

| Field            | Value                                                 |
| ---------------- | ----------------------------------------------------- |
| **Title**        | Session‑Insight Pipeline (rrweb → Knowledge Graph)    |
| **Author**       | Emad (AI Engineering)                                 |
| **Stakeholders** | Product Analytics, UX Research, Data Engineering, SRE |
| **Version**      | 0.9‑draft                                             |
| **Last updated** | 30 May 2025                                           |

---

## 2. Problem Statement

We record front‑end user sessions with **rrweb**.  Raw JSON or video does not support fast, precise queries such as:

* *"Which users clicked **Add to Cart** but never saw **Checkout**?"*
* *"Did the 2025‑05‑01 banner A/B test hurt conversion?"*
* *"Why did rage‑clicks spike after release v2.14?"*

An **incrementally‑updated knowledge graph** backed by Neo4j/**Graphiti** (pronounced *graf‑ih‑tee*, [https://github.com/getzep/graphiti](https://github.com/getzep/graphiti)), plus a thin search layer (GraphRAG), will provide millisecond answers and serve as ground truth for LLM‑powered insights.

---

## 3. Goals & Success Criteria

|  ID | Goal                                           | KPI / Target                                      |
| --- | ---------------------------------------------- | ------------------------------------------------- |
|  G1 | *Exact* behavioural filters in <200 ms         | p95 Cypher query latency <200 ms on 10 M sessions |
|  G2 | 95 %+ precision / 90 %+ recall for CTA queries | Manual QA test‑set each sprint                    |
|  G3 | Support natural‑language analytics             | 80 % of top‑20 FAQ answered via GraphRAG          |

---

## 4. Out of Scope (v1)

* Mobile native SDKs (iOS/Android) – defer to v2.
* Heat‑map visualisation.
* Automated visual‑layout audits (VLM) – integrate as plug‑in later.

---

## 5. High‑Level Architecture

```mermaid
graph TD
  subgraph Ingestion
    A(rrweb events) -->|Kafka| B(Event Processor)
  end
  B --> C[Page Blueprint
  (structural hash)]
  B --> D[Click  ➜  Element
  map]
  C & D -->|Episodes| E(Graphiti API)
  E --> F[Neo4j KG]
  F -->|Cypher / GraphRAG| G(Analytics API)
  G --> H(BI & LLM apps)
```

---

## 6. Data Model (Graph)

### 6.1 Entities

| Label                 | Purpose (sample questions it answers)                 | Key properties (✱ = recommended index)                                                |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **User**              | "Which cohort churned after checkout?"                | ✱user\_id, first\_seen, last\_seen, plan, country, device\_count                      |
| **Device**            | "Do crashes spike on Android 14?"                     | ✱device\_id, type (mobile/desktop), os, browser, screen\_res, ua\_string              |
| **Session**           | "Show me sessions that added‑to‑cart then abandoned." | ✱session\_id, start\_ts, end\_ts, duration, ip, geo, is\_authenticated                |
| **PageView**          | One visit to a URL inside a session                   | ✱pv\_id, timestamp, order\_in\_session, referrer, dom\_hash, viewport\_h, viewport\_w |
| **Page**              | "Where does the CTA live today?"                      | ✱path, title, dom\_hash, template, section (marketing / checkout / etc.)              |
| **Element**           | "Which exact button was clicked?"                     | ✱eid, selector, label, tag, category (CTA/nav/form), synonyms\[]                      |
| **Action**            | Low‑level interaction                                 | ✱action\_id, type (click/input/scroll/hover), ts, x, y, value                         |
| **CustomEvent**       | App‑level semantic event                              | ✱cust\_id, event_name (add\_to\_cart), payload (JSON), ts                                   |
| **NetworkRequest**    | "Did slow API calls precede rage‑clicks?"             | ✱req\_id, url, method, status, latency\_ms, ts                                        |
| **ErrorEvent**        | JS or server error                                    | ✱err\_id, message, stack, severity, ts                                                |
| **PerformanceMetric** | Web Vitals / paint                                    | ✱metric\_id, metric_name (LCP/FID), value, ts                                                |

*Dom hash* = fast **SHA‑1** of the first **FullSnapshot**. Rebuild **Page** and its **Element** children only when it changes.

### 6.2 Relationships (edges)

| Edge                                               | Cardinality     | Meaning                               |
| -------------------------------------------------- | --------------- | ------------------------------------- |
| (User) ‑\[:USES]‑> (Device)                        | 1 : N           | same user on many devices             |
| (User) ‑\[:INITIATED]‑> (Session)                  | 1 : N           | browsing sessions                     |
| (Device) ‑\[:PART\_OF]‑> (Session)                 | 1 : N           | device context for the session        |
| (Session) ‑\[:HAS\_PAGEVIEW]‑> (PageView)          | 1 : N (ordered) | timeline of visited pages             |
| (PageView) ‑\[:OF\_PAGE]‑> (Page)                  | N : 1           | materialised page template            |
| (Page) ‑\[:HAS\_ELEMENT]‑> (Element)               | 1 : N           | clickable inventory                   |
| (Session) ‑\[:PERFORMED]‑> (Action)                | 1 : N           | raw rrweb interactions                |
| (Action) ‑\[:ON]‑> (Element)                       | N : 1           | which DOM node                        |
| (Action) ‑\[:EMITTED]‑> (CustomEvent)              | 0 / 1           | map low‑level action → semantic event |
| (CustomEvent) ‑\[:BELONGS\_TO]‑> (Session)         | N : 1           |                                       |
| (Action) ‑\[:TRIGGERED]‑> (NetworkRequest)         | 0 / 1           | action → API call                     |
| (NetworkRequest) ‑\[:IN\_SESSION]‑> (Session)      | N : 1           |                                       |
| (ErrorEvent) ‑\[:OCCURRED\_IN]‑> (Session)         | N : 1           |                                       |
| (ErrorEvent) ‑\[:ON\_PAGE]‑> (Page)                | N : 1           |                                       |
| (PerformanceMetric) ‑\[:MEASURED\_IN]‑> (PageView) | N : 1           |                                       |

## 7. Event‑Processing Flow (Graphiti‑powered)

All ingestion and updates use **Graphiti** Episodes. Every event is converted to an Episode object, deduplicated via the `id_fields` defined in §6, and persisted to Neo4j through the Graphiti SDK.

| Step  | Trigger                                                  | Graphiti Episode(s)                          | Relationships added                                                                                              |
| ----- | -------------------------------------------------------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **1** | **FullSnapshot** (first in session)                      | `PageTemplate`  ✚  `PageInstance`            | `(Session)-[:VISITED_AT]->(PageTemplate)`<br>`(PageTemplate)-[:HAS_ELEMENT]->(Element)` (one‑off per template)   |
| **2** | **MouseInteraction**                                     | `Action` (type="click" / "hover" / …)        | `(Session)-[:PERFORMED]->(Action)-[:ON]->(Element)`                                                              |
| **3** | **CustomEvent** (e.g. `add_to_cart`, `checkout_started`) | `CustomEvent`                                | `(Session)-[:PERFORMED]->(CustomEvent)`<br>`(Action)-[:EMITTED]->(CustomEvent)` when emitted from a prior Action |
| **4** | **NetworkRequest**                                       | `NetworkRequest`                             | `(Action)-[:TRIGGERED]->(NetworkRequest)`                                                                        |
| **5** | **Flush / end‑of‑file**                                  | `PerformanceMetric`, `ErrorEvent` (optional) | metric & error edges to the relevant `PageView` / `Session`                                                      |

> Deduplication: Graphiti merges on `id_fields` (e.g., `path+struct_hash` for PageTemplate, `action_id` for Action) ensuring idempotent, horizontally‑scalable ingestion.

---

## 8. Search & Retrieval (Cypher + GraphRAG over Graphiti data)

### 8.1 Cypher API Example

```cypher
MATCH (s:Session)-[:PERFORMED]->(a:Action {type:'click'})-[:ON]->(e:Element)
WHERE e.label =~ '(?i).*add.*cart.*'
  AND NOT (s)-[:PERFORMED]->(:CustomEvent {event_name:'checkout_started'})
RETURN s.session_id AS session, count(*) AS clicks
ORDER BY clicks DESC;
```

*Finds every session where a **click** on an Element matching "add to cart" occurred and **no** semantic checkout event was recorded.*

### 8.2 GraphRAG Endpoint (Graphiti Hybrid Search)

`POST /query`  

```json
{
  "question": "Show sessions that added to cart and abandoned",
  "top_k": 100
}
```

Pipeline:

1. **LLM → Cypher** via GraphRAG router (schema from Neo4j introspection).
2. Execute Cypher; obtain sub‑graph of ≤ `top_k` sessions.
3. **Graphiti hybrid re‑rank**: combine BM25, `Element.text_vec`, and structural distance.
4. Return either JSON (list of `session_id`s) or a summarised natural‑language answer.

GraphRAG uses the **same Graphiti vectors** stored on `Element`, `CustomEvent`, and `Page` nodes, ensuring embeddings never drift between ingestion and retrieval.

---

## 9. Non‑Functional Requirements Non‑Functional Requirements

| Category        | Requirement                                           |
| --------------- | ----------------------------------------------------- |
| **Latency**     | p95 <200 ms for top‑10 Cypher queries (10 M sessions) |
| **Throughput**  | 5 k events/s ingestion sustained                      |
| **Consistency** | Eventual (<5 s) graph update visibility               |
| **Scalability** | Horizontal Kafka consumers; Neo4j Aura DS‑4           |
| **Security**    | Sessions keyed; user PII hashed (GDPR)                |
| **Reliability** | ≥99.9 % uptime, monitored via Prometheus              |

---

## 10. Open Questions

1. Do we ingest JS **ErrorEvent** in v1 or v2?
2. Which VLM (Gemini vs Qwen‑VL) for visual edge‑cases?
3. Rollback strategy for erroneous template hash causing cascade?

---

## 11. Timeline (T‑shirt)

| Milestone                   | Wk of  | Owner             |
| --------------------------- | ------ | ----------------- |
|  Schema & constraints live  | Jun 10 | Data Eng          |
|  Ingestion MVP (Kafka → KG) | Jun 24 | Data Eng          |
|  Cypher API GA              | Jul 08 | Backend           |
|  GraphRAG endpoint          | Jul 22 | AI Platform       |
|  Dashboard integration      | Aug 05 | Product Analytics |

---

## 12. Success Metrics & Reporting

* Daily job calculates precision/recall on labelled test‑set; fails pipeline if < targets.
* Grafana dashboard: ingestion lag, graph node/edge counts, query p95.
* Quarterly adoption survey among Product & UX teams.

---

## 13. Future Enhancements

* **Visual‑diff VLM plug‑in** → auto‑tag overlaps, colour‑contrast issues.
* **Real‑time anomaly detector** → PageRank delta alerts.
* **Mobile SDK support** (RRWeb's sibling libs).

---

> **Appendix A – Glossary**
> *KG* = Knowledge Graph.  *VLM* = Vision‑Language Model.
