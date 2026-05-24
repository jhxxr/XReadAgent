# SPDX-License-Identifier: AGPL-3.0-or-later
"""Wiki directory contract, path helpers, and on-disk state managers."""

from xreadagent.wiki.distillation import (
    DistillationPayload,
    load_distillation,
    save_distillation,
)
from xreadagent.wiki.index_regen import regenerate_index, write_index
from xreadagent.wiki.log import WikiConversationLog, WikiLog
from xreadagent.wiki.pages import (
    CONCEPT_SECTIONS,
    PAPER_SECTIONS,
    QUERY_SECTIONS,
    read_page_frontmatter,
    write_concept_page,
    write_paper_page,
    write_query_page,
)
from xreadagent.wiki.paths import (
    WORKSPACE_LAYOUT,
    concept_slug,
    kebab_slug,
    stable_source_slug,
    validate_wiki_path,
)
from xreadagent.wiki.sources import SourcesIndex, compute_content_hash
from xreadagent.wiki.workspace import Workspace

__all__ = [
    "CONCEPT_SECTIONS",
    "DistillationPayload",
    "PAPER_SECTIONS",
    "QUERY_SECTIONS",
    "SourcesIndex",
    "WORKSPACE_LAYOUT",
    "WikiConversationLog",
    "WikiLog",
    "Workspace",
    "compute_content_hash",
    "concept_slug",
    "kebab_slug",
    "load_distillation",
    "read_page_frontmatter",
    "regenerate_index",
    "save_distillation",
    "stable_source_slug",
    "validate_wiki_path",
    "write_concept_page",
    "write_index",
    "write_paper_page",
    "write_query_page",
]
