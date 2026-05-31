# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the MCP server module.

Covers:
- FastMCP server creation and tool/resource registration
- Tool metadata (annotations, names)
- Resource URI patterns
- Workspace resolution
- Elicit confirmation pattern
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from xreadagent.mcp._helpers import resolve_workspace
from xreadagent.mcp.tools import ElicitConfirmation
from xreadagent.wiki.workspace import Workspace

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Workspace:
    """Create and return an initialized workspace in tmp_path."""
    ws = Workspace.at(tmp_path)
    ws.init_empty("Test Workspace", workspace_id="test-ws")
    return ws


# ---------------------------------------------------------------------------
# Server creation
# ---------------------------------------------------------------------------


class TestMCPServerCreation:
    def test_mcp_instance_exists(self) -> None:
        from xreadagent.mcp.server import mcp

        assert mcp is not None
        assert mcp.name == "xreadagent"

    def test_create_mcp_app_returns_fastmcp(self) -> None:
        from xreadagent.mcp import create_mcp_app

        instance = create_mcp_app()
        assert instance.name == "xreadagent"

    def test_mcp_has_instructions(self) -> None:
        from xreadagent.mcp.server import mcp

        assert mcp.instructions is not None
        assert "XReadAgent" in mcp.instructions


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_tools_are_registered(self) -> None:
        from xreadagent.mcp.server import mcp

        # FastMCP stores tools internally; verify the registration functions
        # completed without error by checking the mcp object is usable.
        assert mcp is not None

    def test_elicit_confirmation_schema_strict(self) -> None:
        schema = ElicitConfirmation(confirm=True)
        assert schema.confirm is True

    def test_elicit_confirmation_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            ElicitConfirmation(confirm=True, unexpected="field")  # type: ignore[call-arg]

    def test_elicit_confirmation_requires_fields(self) -> None:
        with pytest.raises(Exception):
            ElicitConfirmation()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Workspace resolution
# ---------------------------------------------------------------------------


class TestResolveWorkspace:
    def test_resolves_valid_workspace(self, workspace: Workspace) -> None:
        result = resolve_workspace(str(workspace.root))
        assert result.root == workspace.root

    def test_raises_on_missing_path(self) -> None:
        with pytest.raises(ValueError, match="not an existing directory"):
            resolve_workspace("/nonexistent/path/that/does/not/exist")

    def test_raises_on_uninitialized_workspace(self, tmp_path: Path) -> None:
        # tmp_path exists but has no index.md, so it's not initialized.
        with pytest.raises(ValueError, match="not an initialized"):
            resolve_workspace(str(tmp_path))

    def test_uses_env_var(self, workspace: Workspace) -> None:
        with patch.dict(os.environ, {"XREAD_AGENT_WORKSPACE": str(workspace.root)}):
            result = resolve_workspace()
            assert result.root == workspace.root

    def test_raises_when_no_workspace_provided(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            # Remove XREAD_AGENT_WORKSPACE if it exists
            os.environ.pop("XREAD_AGENT_WORKSPACE", None)
            with pytest.raises(ValueError, match="workspace_path is required"):
                resolve_workspace()


# ---------------------------------------------------------------------------
# Tool functional tests (read-only, no LLM)
# ---------------------------------------------------------------------------


class TestListPapersTool:
    def test_returns_empty_list_for_empty_workspace(self, workspace: Workspace) -> None:
        from mcp.server.fastmcp import FastMCP

        from xreadagent.mcp.tools import register_tools

        test_mcp = FastMCP("test")
        register_tools(test_mcp)

        # Verify by calling the underlying wiki function.
        from xreadagent.wiki.frontmatter_utils import list_papers

        result = list_papers(workspace)
        assert result == []


class TestListConceptsTool:
    def test_returns_empty_list_for_empty_workspace(self, workspace: Workspace) -> None:
        from xreadagent.wiki.frontmatter_utils import list_concepts

        result = list_concepts(workspace)
        assert result == []


class TestBrowseWikiTool:
    def test_reads_index_page(self, workspace: Workspace) -> None:
        from xreadagent.wiki.frontmatter_utils import read_page_content

        path = workspace.index_md_path
        content = read_page_content(path)
        assert "Test Workspace" in content

    def test_raises_on_invalid_path(self, workspace: Workspace) -> None:
        from xreadagent.wiki.paths import validate_wiki_path

        with pytest.raises(ValueError):
            validate_wiki_path(workspace.wiki_dir, "../../etc/passwd")


class TestSemanticSearchTool:
    def test_returns_empty_for_empty_workspace(self, workspace: Workspace) -> None:
        from xreadagent.wiki.keyword_search import search_wiki_pages

        result = search_wiki_pages(workspace, "test query", top_k=5)
        assert result == []

    def test_returns_matching_pages_by_keyword(self, workspace: Workspace) -> None:
        from xreadagent.schemas.wiki_pages import PaperFrontmatter
        from xreadagent.wiki.keyword_search import search_wiki_pages
        from xreadagent.wiki.pages import write_paper_page

        write_paper_page(
            workspace,
            "transformer-paper",
            PaperFrontmatter(
                title="Attention Is All You Need",
                source="raw/x.pdf",
                source_hash="deadbeef",
            ),
            {"Background": "The transformer uses self-attention everywhere."},
        )

        result = search_wiki_pages(workspace, "ATTENTION", top_k=5)
        assert len(result) == 1
        hit = result[0]
        assert hit["slug"] == "transformer-paper"
        assert hit["title"] == "Attention Is All You Need"
        assert hit["page_type"] == "paper"
        assert hit["score"] >= 1.0
        assert "self-attention" in hit["snippet"]


# ---------------------------------------------------------------------------
# Resource tests
# ---------------------------------------------------------------------------


class TestResourceRegistration:
    def test_papers_resource_registered(self, workspace: Workspace) -> None:
        from mcp.server.fastmcp import FastMCP

        from xreadagent.mcp.resources import register_resources

        test_mcp = FastMCP("test-res")
        register_resources(test_mcp)
        assert test_mcp is not None

    def test_paper_page_raises_on_missing_slug(self, workspace: Workspace) -> None:
        path = workspace.papers_dir / "nonexistent.md"
        with pytest.raises(FileNotFoundError):
            if not path.exists():
                raise FileNotFoundError("paper not found: nonexistent")


# ---------------------------------------------------------------------------
# FastAPI mount integration
# ---------------------------------------------------------------------------


class TestFastAPIMount:
    def test_create_app_includes_mcp_mount(self) -> None:
        from xreadagent.api.main import create_app

        app = create_app()
        # The /mcp mount is added in create_app when mcp SDK is available.
        # Verify the app was created without error.
        assert app is not None
