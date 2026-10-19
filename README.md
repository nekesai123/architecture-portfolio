# Architecture Portfolio

Public showcase of selected architecture work. Source repositories remain private; each case below presents the system context, architecture decisions, quality-engineering evidence, and honest trade-offs.

> **Positioning**: Principal Architect / Principal Solutions roles — the emphasis is on *why* systems are shaped this way and *how* quality is proven, not feature lists.

## Case Studies

| Case | Domain | Stack | Highlights |
|---|---|---|---|
| [Logistics Management SaaS](logistics/) | Multi-tenant freight-forwarding platform | Java 21 · Spring Boot 3.5 · PostgreSQL 18 · jOOQ · React 18 | 15-module monolith, shared-schema tenancy, 8 business chains, 3-tier test system, AI-augmented delivery process |
| [Exam Parser System](exam-parser/) | Document parsing pipeline (exam papers → question banks) | Java 23 · Spring Boot · PaddleOCR fleet · jOOQ/MariaDB | Proprietary binary format (MTEF) reverse engineering with audit-degradation, strategy-chain LaTeX cleanup, fuzz/metamorphic/corpus-baseline testing (~250 test files) |
| [Multi-Agent Web](multi-agent-web/) | LLM task orchestration platform | Node.js · Express · WebSocket | Filesystem-as-source-of-truth artifact reconciliation, verify-before-dispatch gate with caching, open/closed provider abstraction |

## Architecture Themes Across Cases

- **Modular first, distributed only when justified** — modular monolith with enforced boundaries (architecture tests in CI), not microservices by fashion.
- **Quality as a gate, not a report** — layered test systems with build-failing thresholds, dual-green acceptance discipline, regression gates on CI.
- **Tenancy and security designed at the seam** — tenant resolution and permission enforcement at a single choke point, proven by dedicated boundary tests.
- **AI-augmented delivery with human accountability** — multi-agent build process governed by written protocol: separation of write/verify roles, face-disjoint parallel task cards, arbitration and final-review gates. Every deliverable lands with evidence, not verbal claims.

## Privacy Statement

These case studies contain no credentials, no customer data, no internal endpoints. Code excerpts are deliberately minimal and illustrative. Numbers (test counts, latency) are from real verification runs.
