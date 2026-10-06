# Requirements and design documents

These documents define the intended product. They were written on the `docs/production-architecture-v2` branch (PR #1),
which could not be merged because it carried a competing code line. They are brought over here **unchanged apart from a
status banner**, so the requirements live next to the code they describe.

| Document | What it is |
|---|---|
| [PRD.md](PRD.md) | The frozen product requirements (sections 1-21). The longer original is `FMCG Competitor Promotion.md` at the repo root. |
| [DATA_MODEL.md](DATA_MODEL.md) | Target PostgreSQL data model |
| [DATA_QUALITY.md](DATA_QUALITY.md) | Trust, provenance and quality gates |
| [SOURCE_STRATEGY.md](SOURCE_STRATEGY.md) | Source discovery, registry and collection policy |
| [UI_UX_DESIGN.md](UI_UX_DESIGN.md) | Dashboard information architecture and views |
| [RUNBOOK.md](RUNBOOK.md) | Operations and troubleshooting guide |
| [ROADMAP.md](ROADMAP.md) | Phased implementation plan (statuses are not current) |

**What is actually built, and what is not:** [`docs/PRD_ALIGNMENT.md`](../PRD_ALIGNMENT.md).

Not carried over: `IMPLEMENTATION_AUDIT.md` (a status report on the other code line, not accurate for this one). It remains on the
`docs/production-architecture-v2` branch.
