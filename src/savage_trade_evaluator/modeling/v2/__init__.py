"""V2 modeling: context-aware multilevel with (team, regime) clustering.

Incorporates all five methodology corrections from Phase 1:
- D-24: within-team-variation features only
- D-25/26: rate-based outcomes; credibility = 90% CI + 95% mass
- D-28: (team, regime) cluster structure
- D-29: sell-high vs system-tax decomposition
- D-30: dollar surplus baseline via Spotrac contracts (NEW)

Design doc: ``docs/V2_DESIGN.md``.
"""

from __future__ import annotations
