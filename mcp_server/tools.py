"""MCP tool implementations: thin adapters over the public HKOS API.

Each tool maps 1:1 to an existing public service call. No business logic
lives here — this layer only marshals arguments and serializes results.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from hkos.context import ContextBuilder, SnapshotLoader
from hkos.core.exceptions import HKOSError
from hkos.core.logger import HKOSLogger
from hkos.core.version import VersionManager
from hkos.mcp_server.context import McpContext
from hkos.repository.models import Knowledge

_PROJECT_HINT = "project id or name (created if missing for save)"


def _resolve_project(ctx: McpContext, project: str, create: bool = False) -> Any:
    """Resolve a project by id or name; optionally auto-create."""
    for p in ctx.projects.list():
        if p.id == project or p.name == project:
            return p
    if create:
        return ctx.projects.create(
            name=project, description="created via hkos-mcp", tags=["mcp"])
    raise HKOSError(f"project not found: {project}")


def tool_retrieve(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Retrieve ranked knowledge with explanations (deterministic)."""
    project = _resolve_project(ctx, str(args["project"]))
    result = ctx.retrieval.retrieve(
        str(args["query"]),
        project_id=project.id,
        campaign_id=str(args.get("campaign_id") or ""),
        top_n=int(args.get("top_n", 20)),
    )
    return {
        "query": result.query,
        "project_id": project.id,
        "duration_ms": round(result.duration_ms, 2),
        "total_candidates": result.total_candidates,
        "item_count": len(result.items),
        "items": [item.as_dict() for item in result.items],
    }


def tool_context(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Build an optimized context document (retrieval + budget profile)."""
    project = _resolve_project(ctx, str(args["project"]))
    query = str(args.get("query") or args.get("task") or "").strip()
    if not query:
        raise HKOSError("context requires 'query' or 'task'")
    result = ctx.retrieval.retrieve(query, project_id=project.id, top_n=50)
    profile = str(args.get("profile", "MEDIUM")).upper()
    builder = ContextBuilder(
        ctx.cfg, HKOSLogger(),
        loader=SnapshotLoader(ctx.snapshot_persistence.latest),
    )
    doc = builder.build(result, project.id, profile=profile)
    sections = {
        name: [{"id": item.entity.id, "title": item.entity.title}
               for item in items]
        for name, items in doc.sections.items()
    }
    return {
        "project_id": project.id,
        "profile": doc.profile,
        "item_count": len(doc.items),
        "excluded_count": len(doc.excluded),
        "estimates": asdict(doc.estimates),
        "sections": sections,
    }


def tool_save(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Write knowledge through the Librarian (the only write path)."""
    project = _resolve_project(ctx, str(args["project"]), create=True)
    knowledge = Knowledge(
        title=str(args["title"]),
        body=str(args.get("body") or ""),
        tags=[str(t) for t in (args.get("tags") or [])],
        category=str(args.get("category") or ""),
        kind=str(args.get("kind") or "fact"),
        confidence=int(args.get("confidence", 95)),
    )
    registered = ctx.librarian.register(project.id, knowledge)
    if args.get("canonicalize", True):
        ctx.librarian.canonicalize(project.id, registered.id)
        ctx.index.update(project.id, registered.id, "knowledge")
    entity = ctx.repos.knowledge.load(project.id, registered.id)
    return {
        "id": entity.id,
        "project_id": project.id,
        "title": entity.title,
        "category": entity.category,
        "kind": entity.kind,
        "status": entity.status,
    }


def tool_snapshot(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Create or read project snapshots (derived, versioned state)."""
    project = _resolve_project(ctx, str(args["project"]))
    action = str(args.get("action", "create"))
    if action == "create":
        snap = ctx.snapshots.create(
            project.id,
            reason=str(args.get("reason") or "mcp"),
            comment=str(args.get("comment") or ""),
            author="hkos-mcp",
            force=bool(args.get("force", True)),
        )
        return {
            "action": "create",
            "snapshot_id": snap.snapshot_id,
            "statistics": snap.statistics,
        }
    if action == "latest":
        latest_snap = ctx.snapshots.load(project.id)
        if latest_snap is None:
            return {"action": "latest", "snapshot": None}
        return {
            "action": "latest",
            "snapshot_id": latest_snap.snapshot_id,
            "statistics": latest_snap.statistics,
        }
    if action == "history":
        return {
            "action": "history",
            "entries": ctx.snapshots.history(project.id),
        }
    raise HKOSError(f"unknown snapshot action: {action}")


def tool_doctor(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Run the consistency doctor: repository vs index vs snapshot."""
    project = _resolve_project(ctx, str(args["project"]))
    report = ctx.doctor.check(project.id)
    return {
        "project_id": project.id,
        "verdict": report.verdict,
        "checks": [
            {
                "check": issue.check,
                "status": issue.status,
                "expected": issue.expected,
                "actual": issue.actual,
                "detail": issue.detail,
            }
            for issue in report.issues
        ],
    }


def tool_status(ctx: McpContext, args: dict[str, Any]) -> dict[str, Any]:
    """Server status: version, data root, profile, corpus size."""
    projects = ctx.projects.list()
    knowledge_total = sum(ctx.repos.knowledge.count(p.id) for p in projects)
    return {
        "ready": True,
        "version": VersionManager().version_string,
        "profile": ctx.profile,
        "data_root": ctx.data_root,
        "projects": len(projects),
        "knowledge_total": knowledge_total,
        "repository_available": True,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "retrieve",
        "description": (
            "Deterministic retrieval from the engineering knowledge base. "
            "Returns ranked knowledge items with per-item explanations "
            "(reason/score). Negative knowledge (past failures) ranks first."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "search query"},
                "project": {"type": "string", "description": _PROJECT_HINT},
                "top_n": {"type": "integer", "default": 20, "minimum": 1,
                          "maximum": 500},
                "campaign_id": {"type": "string", "default": ""},
            },
            "required": ["query", "project"],
        },
    },
    {
        "name": "context",
        "description": (
            "Build an optimized, budgeted context document for a task: "
            "retrieval + ContextBuilder + profile (SMALL/MEDIUM/LARGE/FULL). "
            "Returns sectioned context with token estimates."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": _PROJECT_HINT},
                "query": {"type": "string", "description": "search query"},
                "task": {"type": "string",
                         "description": "task description (query fallback)"},
                "profile": {"type": "string", "default": "MEDIUM",
                            "enum": ["SMALL", "MEDIUM", "LARGE", "FULL"]},
            },
            "required": ["project"],
        },
    },
    {
        "name": "save",
        "description": (
            "Write a knowledge item through the Librarian (the only write "
            "path), canonicalize it and index it. The deterministic "
            "classifier may override the suggested category."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": _PROJECT_HINT},
                "title": {"type": "string"},
                "body": {"type": "string", "default": ""},
                "tags": {"type": "array", "items": {"type": "string"},
                         "default": []},
                "category": {"type": "string", "default": "",
                             "description": "hint; classifier may override"},
                "kind": {"type": "string", "default": "fact",
                         "enum": ["fact", "negative"]},
                "confidence": {"type": "number", "default": 95},
                "canonicalize": {"type": "boolean", "default": True},
            },
            "required": ["project", "title"],
        },
    },
    {
        "name": "snapshot",
        "description": (
            "Create or read project snapshots (derived, versioned state of "
            "the repository). Actions: create (new version), latest, history."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": _PROJECT_HINT},
                "action": {"type": "string", "default": "create",
                           "enum": ["create", "latest", "history"]},
                "reason": {"type": "string", "default": "mcp"},
                "comment": {"type": "string", "default": ""},
                "force": {"type": "boolean", "default": True},
            },
            "required": ["project"],
        },
    },
    {
        "name": "doctor",
        "description": (
            "Run the consistency doctor on a project: repository vs index vs "
            "snapshot counters, orphan detection. Verdict PASS/FAIL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": _PROJECT_HINT},
            },
            "required": ["project"],
        },
    },
    {
        "name": "status",
        "description": "HKOS server status: version, data root, profile, "
                       "project and knowledge counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS: dict[str, Callable[[McpContext, dict[str, Any]], dict[str, Any]]] = {
    "retrieve": tool_retrieve,
    "context": tool_context,
    "save": tool_save,
    "snapshot": tool_snapshot,
    "doctor": tool_doctor,
    "status": tool_status,
}
