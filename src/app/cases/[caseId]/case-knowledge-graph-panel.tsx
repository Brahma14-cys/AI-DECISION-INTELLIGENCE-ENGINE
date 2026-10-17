"use client";

import { useCallback, useEffect, useMemo, useState, useRef, type FormEvent, type MouseEvent as ReactMouseEvent } from "react";
import {
  Network,
  RefreshCw,
  Search,
  ZoomIn,
  ZoomOut,
  Maximize2,
  List,
  LayoutGrid,
  X,
  Eye,
  Tag,
  ChevronRight,
  Sparkles,
  Layers,
} from "lucide-react";
import {
  CaseKnowledgeGraphNode,
  CaseKnowledgeGraphEdge,
  CaseKnowledgeGraphResult,
  getLatestCaseKnowledgeGraph,
  searchCaseKnowledgeGraph,
  startCaseKnowledgeGraph,
  type CaseKnowledgeGraphSearchResult,
} from "@/lib/api";
import { PageShell, PageHeader, PageBody } from "@/components/domain/page-shell";
import { EmptyState } from "@/components/domain/empty-state";
import { InlineAlert } from "@/components/domain/inline-alert";
import { CitationChip } from "@/components/domain/citation-chip";
import { formatLabel } from "@/lib/formatters";

type PositionedNode = CaseKnowledgeGraphNode & {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  degree: number;
};

const CANVAS_WIDTH = 1100;
const CANVAS_HEIGHT = 720;

export function CaseKnowledgeGraphPanel({ caseId }: { caseId: string }) {
  const [graph, setGraph] = useState<CaseKnowledgeGraphResult | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [showEvidence, setShowEvidence] = useState(false);
  const [labelDensity, setLabelDensity] = useState<"smart" | "all" | "minimal">("smart");
  const [viewMode, setViewMode] = useState<"graph" | "list">("graph");

  // Selection & Hover
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  // Node Dragging
  const [draggingNodeId, setDraggingNodeId] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Canvas Zoom & Pan
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Simulation node positions state
  const [nodePositions, setNodePositions] = useState<Map<string, { x: number; y: number }>>(new Map());

  const graphStatus = graph?.run.status;
  const isPending = graphStatus !== undefined && ["queued", "processing"].includes(graphStatus);

  const refreshGraph = useCallback(async () => {
    const result = await getLatestCaseKnowledgeGraph(caseId);
    setGraph(result);
    return result;
  }, [caseId]);

  useEffect(() => {
    let active = true;
    void getLatestCaseKnowledgeGraph(caseId)
      .then((result) => {
        if (active) setGraph(result);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [caseId]);

  useEffect(() => {
    if (!graphStatus || !["queued", "processing"].includes(graphStatus)) return;
    const timer = window.setInterval(() => {
      void refreshGraph().catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [graphStatus, refreshGraph]);

  async function buildGraph() {
    setStarting(true);
    setError(null);
    try {
      const run = await startCaseKnowledgeGraph(caseId);
      setGraph({ run, nodes: [], edges: [] });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Failed to build graph.");
    } finally {
      setStarting(false);
    }
  }

  // Filtered nodes
  const displayNodes = useMemo(() => {
    if (!graph?.nodes) return [];
    return graph.nodes.filter((n) => {
      if (!showEvidence && n.node_type === "evidence") return false;
      if (typeFilter !== "all" && n.node_type !== typeFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return n.label.toLowerCase().includes(q) || (n.text && n.text.toLowerCase().includes(q));
      }
      return true;
    });
  }, [graph?.nodes, typeFilter, showEvidence, searchQuery]);

  const displayEdges = useMemo(() => {
    if (!graph?.edges) return [];
    const validNodeIds = new Set(displayNodes.map((n) => n.node_id));
    return graph.edges.filter((e) => validNodeIds.has(e.source_id) && validNodeIds.has(e.target_id));
  }, [graph?.edges, displayNodes]);

  // Degrees computation
  const degreeMap = useMemo(() => {
    const map: Record<string, number> = {};
    displayEdges.forEach((e) => {
      map[e.source_id] = (map[e.source_id] || 0) + 1;
      map[e.target_id] = (map[e.target_id] || 0) + 1;
    });
    return map;
  }, [displayEdges]);

  // Physics simulation to compute non-overlapping, well-spaced coordinates
  useEffect(() => {
    if (displayNodes.length === 0) {
      setNodePositions(new Map());
      return;
    }

    const clusterTargets: Record<string, { x: number; y: number }> = {
      issue: { x: CANVAS_WIDTH * 0.5, y: CANVAS_HEIGHT * 0.2 },
      party: { x: CANVAS_WIDTH * 0.8, y: CANVAS_HEIGHT * 0.38 },
      provision: { x: CANVAS_WIDTH * 0.2, y: CANVAS_HEIGHT * 0.4 },
      fact: { x: CANVAS_WIDTH * 0.5, y: CANVAS_HEIGHT * 0.65 },
      evidence: { x: CANVAS_WIDTH * 0.5, y: CANVAS_HEIGHT * 0.88 },
    };

    // Initialize simulation nodes
    const simNodes: PositionedNode[] = displayNodes.map((node, i) => {
      const degree = degreeMap[node.node_id] || 0;
      const radius = node.node_type === "issue" ? 22 : Math.min(10 + degree * 2, 20);
      const target = clusterTargets[node.node_type] || { x: CANVAS_WIDTH * 0.5, y: CANVAS_HEIGHT * 0.5 };
      
      // Slight deterministic jitter to avoid pure colinearity
      const angle = (i * 2.39996) % (2 * Math.PI); // golden angle
      const spread = 70 + (i % 7) * 25;
      const initX = target.x + Math.cos(angle) * spread;
      const initY = target.y + Math.sin(angle) * spread;

      return {
        ...node,
        x: Math.max(radius + 20, Math.min(CANVAS_WIDTH - radius - 20, initX)),
        y: Math.max(radius + 20, Math.min(CANVAS_HEIGHT - radius - 20, initY)),
        vx: 0,
        vy: 0,
        radius,
        degree,
      };
    });

    const nodeIndexMap = new Map<string, number>();
    simNodes.forEach((n, idx) => nodeIndexMap.set(n.node_id, idx));

    const edgePairs: [number, number, string][] = [];
    displayEdges.forEach((e) => {
      const u = nodeIndexMap.get(e.source_id);
      const v = nodeIndexMap.get(e.target_id);
      if (u !== undefined && v !== undefined && u !== v) {
        edgePairs.push([u, v, e.relation]);
      }
    });

    // Run 100 relaxation steps
    const iterations = 120;
    for (let step = 0; step < iterations; step++) {
      const temperature = Math.max(0.05, 1 - step / iterations);

      // 1. Repulsion between all pairs + strict collision avoidance
      for (let i = 0; i < simNodes.length; i++) {
        for (let j = i + 1; j < simNodes.length; j++) {
          const a = simNodes[i];
          const b = simNodes[j];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let dist = Math.sqrt(dx * dx + dy * dy);
          if (dist === 0) {
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
            dist = 1;
          }

          const minDist = a.radius + b.radius + 44; // Minimum comfortable padding
          if (dist < minDist) {
            // Strong push apart
            const overlap = (minDist - dist) / dist;
            const force = overlap * 1.8 * temperature;
            a.vx -= dx * force;
            a.vy -= dy * force;
            b.vx += dx * force;
            b.vy += dy * force;
          } else {
            // Standard Coulomb repulsion
            const force = (1200 / (dist * dist)) * temperature;
            a.vx -= (dx / dist) * force;
            a.vy -= (dy / dist) * force;
            b.vx += (dx / dist) * force;
            b.vy += (dy / dist) * force;
          }
        }
      }

      // 2. Spring force along edges
      for (const [u, v] of edgePairs) {
        const a = simNodes[u];
        const b = simNodes[v];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const idealDist = a.radius + b.radius + 90;
        const delta = (dist - idealDist) / dist;
        const springForce = delta * 0.12 * temperature;

        a.vx += dx * springForce;
        a.vy += dy * springForce;
        b.vx -= dx * springForce;
        b.vy -= dy * springForce;
      }

      // 3. Cluster gravity anchor
      for (const node of simNodes) {
        const target = clusterTargets[node.node_type] || { x: CANVAS_WIDTH * 0.5, y: CANVAS_HEIGHT * 0.5 };
        const gx = (target.x - node.x) * 0.035 * temperature;
        const gy = (target.y - node.y) * 0.035 * temperature;
        node.vx += gx;
        node.vy += gy;

        // Apply velocity with damping
        node.x += node.vx * 0.6;
        node.y += node.vy * 0.6;
        node.vx *= 0.4;
        node.vy *= 0.4;

        // Boundary clamping
        node.x = Math.max(node.radius + 24, Math.min(CANVAS_WIDTH - node.radius - 24, node.x));
        node.y = Math.max(node.radius + 24, Math.min(CANVAS_HEIGHT - node.radius - 24, node.y));
      }
    }

    const resultMap = new Map<string, { x: number; y: number }>();
    simNodes.forEach((n) => resultMap.set(n.node_id, { x: n.x, y: n.y }));
    setNodePositions(resultMap);
  }, [displayNodes, displayEdges, degreeMap]);

  // Merged positioned nodes
  const positionedNodes: PositionedNode[] = useMemo(() => {
    return displayNodes.map((node) => {
      const pos = nodePositions.get(node.node_id) || { x: CANVAS_WIDTH / 2, y: CANVAS_HEIGHT / 2 };
      const degree = degreeMap[node.node_id] || 0;
      const radius = node.node_type === "issue" ? 22 : Math.min(10 + degree * 2, 20);
      return {
        ...node,
        x: pos.x,
        y: pos.y,
        vx: 0,
        vy: 0,
        radius,
        degree,
      };
    });
  }, [displayNodes, nodePositions, degreeMap]);

  const activeFocusId = hoveredNodeId || selectedNodeId;

  // Selected & Neighbor Set for high-contrast path isolation
  const activeNeighborIds = useMemo(() => {
    if (!activeFocusId || !graph?.edges) return new Set<string>();
    const neighbors = new Set<string>([activeFocusId]);
    graph.edges.forEach((e) => {
      if (e.source_id === activeFocusId) neighbors.add(e.target_id);
      if (e.target_id === activeFocusId) neighbors.add(e.source_id);
    });
    return neighbors;
  }, [activeFocusId, graph?.edges]);

  const selectedNode = useMemo(
    () => positionedNodes.find((n) => n.node_id === selectedNodeId) || null,
    [positionedNodes, selectedNodeId]
  );

  const selectedNeighbors = useMemo(() => {
    if (!selectedNode || !graph?.edges) return [];
    const neighbors: { node: PositionedNode; relation: string; isSource: boolean }[] = [];
    const allNodeMap = new Map(positionedNodes.map((n) => [n.node_id, n]));

    graph.edges.forEach((edge) => {
      if (edge.source_id === selectedNode.node_id) {
        const target = allNodeMap.get(edge.target_id);
        if (target) neighbors.push({ node: target, relation: edge.relation, isSource: true });
      } else if (edge.target_id === selectedNode.node_id) {
        const source = allNodeMap.get(edge.source_id);
        if (source) neighbors.push({ node: source, relation: edge.relation, isSource: false });
      }
    });
    return neighbors;
  }, [selectedNode, graph?.edges, positionedNodes]);

  // Color mapping
  function getNodeFill(type: string): string {
    switch (type) {
      case "issue":
        return "var(--primary)"; // Oxblood Burgundy
      case "party":
        return "var(--brass)"; // Warm Brass
      case "provision":
        return "#3B82F6"; // Cobalt / Blue Provision
      case "fact":
        return "#EFECE6"; // Ivory / Linen
      case "evidence":
      default:
        return "var(--surface-2)";
    }
  }

  function getNodeStroke(type: string): string {
    switch (type) {
      case "issue":
        return "#FFFFFF";
      case "party":
        return "var(--surface)";
      case "provision":
        return "var(--surface)";
      case "fact":
        return "var(--border-strong)";
      case "evidence":
      default:
        return "var(--brass)";
    }
  }

  // Node Drag handlers
  function handleNodeMouseDown(e: ReactMouseEvent, node: PositionedNode) {
    e.stopPropagation();
    setDraggingNodeId(node.node_id);
    setDragOffset({ x: e.clientX - node.x * zoom - pan.x, y: e.clientY - node.y * zoom - pan.y });
  }

  function handleSvgMouseMove(e: ReactMouseEvent) {
    if (draggingNodeId) {
      const newX = (e.clientX - dragOffset.x - pan.x) / zoom;
      const newY = (e.clientY - dragOffset.y - pan.y) / zoom;
      setNodePositions((prev) => {
        const next = new Map(prev);
        next.set(draggingNodeId, {
          x: Math.max(30, Math.min(CANVAS_WIDTH - 30, newX)),
          y: Math.max(30, Math.min(CANVAS_HEIGHT - 30, newY)),
        });
        return next;
      });
      return;
    }

    if (isPanning) {
      setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
    }
  }

  function handleSvgMouseUp() {
    setDraggingNodeId(null);
    setIsPanning(false);
  }

  function handleSvgWheel(e: React.WheelEvent) {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
    setZoom((z) => Math.max(0.4, Math.min(2.5, +(z * zoomFactor).toFixed(2))));
  }

  const counts = useMemo(() => {
    if (!graph?.nodes) return { issue: 0, fact: 0, party: 0, provision: 0 };
    return {
      issue: graph.nodes.filter((n) => n.node_type === "issue").length,
      fact: graph.nodes.filter((n) => n.node_type === "fact").length,
      party: graph.nodes.filter((n) => n.node_type === "party").length,
      provision: graph.nodes.filter((n) => n.node_type === "provision").length,
    };
  }, [graph?.nodes]);

  return (
    <PageShell>
      {/* 1. Header */}
      <PageHeader
        title="Knowledge graph"
        description="Structured network of facts, issues, parties, and legal provisions."
        actions={
          <div className="flex items-center gap-3">
            {graph && graph.nodes.length > 0 && (
              <span className="text-xs text-[var(--text-muted)] font-mono hidden sm:inline">
                {graph.nodes.length} nodes · {graph.edges.length} connections
              </span>
            )}
            <button
              type="button"
              disabled={starting || isPending}
              onClick={buildGraph}
              className={graph?.nodes.length ? "btn-secondary text-xs" : "btn-primary text-xs"}
            >
              {isPending ? (
                <>
                  <RefreshCw className="size-3.5 animate-spin" />
                  <span>Building graph…</span>
                </>
              ) : graph?.nodes.length ? (
                <span>Rebuild graph</span>
              ) : (
                <span>Build graph</span>
              )}
            </button>
          </div>
        }
      />

      {error && <InlineAlert type="error" message={error} />}

      {graph?.nodes.length && graph.capabilities?.semantic_embeddings !== "available" ? (
        <InlineAlert
          type="warning"
          message="Semantic embeddings are unavailable for this graph. Relationship links are available, and graph search is using lexical matching only."
        />
      ) : null}

      {/* Empty State */}
      {!graph?.nodes.length && !isPending && (
        <EmptyState
          icon={Network}
          title="No graph generated yet"
          description="Build a connected knowledge network of facts, issues, parties, and statutory provisions extracted across all case documents."
          action={
            <button
              type="button"
              disabled={starting}
              onClick={buildGraph}
              className="btn-primary"
            >
              <Network className="size-4" />
              <span>Build graph</span>
            </button>
          }
        />
      )}

      {/* Building State */}
      {isPending && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-8 text-center space-y-3">
          <div className="flex items-center justify-center gap-2 text-xs font-medium text-[var(--primary)]">
            <RefreshCw className="size-4 animate-spin" />
            <span>Constructing entity and relationship graph in Neo4j…</span>
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Organizing core claims, contradictions, evidence passages, and relevant statutes.
          </p>
        </div>
      )}

      {/* Main Graph Content */}
      {graph && graph.nodes.length > 0 && (
        <PageBody variant="fill" className="space-y-3">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
            {/* Left: Search input & Type Filter buttons */}
            <div className="flex flex-wrap items-center gap-2 flex-1 min-w-[280px]">
              <div className="relative w-56 sm:w-64">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 size-4 text-[var(--text-faint)] pointer-events-none" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter nodes by text…"
                  className="input-field h-8 w-full pl-10 text-xs"
                />
              </div>

              {/* Type Category Pills */}
              <div className="flex items-center gap-1 rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface)] overflow-x-auto">
                <button
                  type="button"
                  onClick={() => setTypeFilter("all")}
                  className={`rounded px-2.5 py-1 text-xs transition ${
                    typeFilter === "all"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold shadow-xs"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  All ({displayNodes.length})
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter("issue")}
                  className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs transition ${
                    typeFilter === "issue"
                      ? "bg-[var(--primary-tint)] text-[var(--primary)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  <span className="size-2 rounded-full bg-[var(--primary)]" />
                  <span>Issues ({counts.issue})</span>
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter("party")}
                  className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs transition ${
                    typeFilter === "party"
                      ? "bg-[var(--brass)]/10 text-[var(--brass)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  <span className="size-2 rounded-full bg-[var(--brass)]" />
                  <span>Parties ({counts.party})</span>
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter("provision")}
                  className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs transition ${
                    typeFilter === "provision"
                      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  <span className="size-2 rounded-full bg-[#3B82F6]" />
                  <span>Provisions ({counts.provision})</span>
                </button>
                <button
                  type="button"
                  onClick={() => setTypeFilter("fact")}
                  className={`flex items-center gap-1.5 rounded px-2 py-1 text-xs transition ${
                    typeFilter === "fact"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  <span className="size-2 rounded-full bg-[var(--text-muted)]" />
                  <span>Facts ({counts.fact})</span>
                </button>
              </div>
            </div>

            {/* Right: Label Density & Zoom Controls */}
            <div className="flex items-center gap-2 shrink-0">
              {/* Labels Toggle */}
              <div className="flex items-center rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface)] text-[11px]">
                <button
                  type="button"
                  onClick={() => setLabelDensity("smart")}
                  className={`rounded px-2 py-0.5 transition ${
                    labelDensity === "smart"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                      : "text-[var(--text-muted)]"
                  }`}
                  title="Show labels for key hubs and hovered nodes"
                >
                  Smart labels
                </button>
                <button
                  type="button"
                  onClick={() => setLabelDensity("all")}
                  className={`rounded px-2 py-0.5 transition ${
                    labelDensity === "all"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                      : "text-[var(--text-muted)]"
                  }`}
                  title="Show all labels"
                >
                  All
                </button>
                <button
                  type="button"
                  onClick={() => setLabelDensity("minimal")}
                  className={`rounded px-2 py-0.5 transition ${
                    labelDensity === "minimal"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-semibold"
                      : "text-[var(--text-muted)]"
                  }`}
                  title="Hide labels except on hover"
                >
                  Minimal
                </button>
              </div>

              <div className="h-4 w-px bg-[var(--border)] mx-1" />

              {/* Zoom Controls */}
              <button
                type="button"
                onClick={() => setZoom((z) => Math.min(z + 0.2, 2.5))}
                className="btn-ghost p-1.5 h-8 w-8 text-[var(--text-muted)]"
                title="Zoom in"
              >
                <ZoomIn className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => setZoom((z) => Math.max(z - 0.2, 0.4))}
                className="btn-ghost p-1.5 h-8 w-8 text-[var(--text-muted)]"
                title="Zoom out"
              >
                <ZoomOut className="size-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  setZoom(1);
                  setPan({ x: 0, y: 0 });
                }}
                className="btn-ghost p-1.5 h-8 w-8 text-[var(--text-muted)]"
                title="Reset canvas"
              >
                <Maximize2 className="size-3.5" />
              </button>

              <div className="h-4 w-px bg-[var(--border)] mx-1" />

              {/* View Switcher */}
              <div className="flex items-center rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface)]">
                <button
                  type="button"
                  onClick={() => setViewMode("graph")}
                  className={`rounded px-2 py-0.5 text-xs transition ${
                    viewMode === "graph"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-medium"
                      : "text-[var(--text-muted)]"
                  }`}
                  title="Interactive network canvas"
                >
                  <LayoutGrid className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("list")}
                  className={`rounded px-2 py-0.5 text-xs transition ${
                    viewMode === "list"
                      ? "bg-[var(--surface-2)] text-[var(--text)] font-medium"
                      : "text-[var(--text-muted)]"
                  }`}
                  title="Tabular list view"
                >
                  <List className="size-3.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Graph Canvas */}
          {viewMode === "graph" ? (
            <div className="relative flex-1 min-h-[580px] rounded-lg border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
              <svg
                viewBox={`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`}
                className="w-full h-full cursor-grab active:cursor-grabbing select-none"
                onWheel={handleSvgWheel}
                onMouseDown={(e) => {
                  if (e.target === e.currentTarget) {
                    setIsPanning(true);
                    setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
                    setSelectedNodeId(null);
                  }
                }}
                onMouseMove={handleSvgMouseMove}
                onMouseUp={handleSvgMouseUp}
                onMouseLeave={handleSvgMouseUp}
              >
                <defs>
                  {/* Subtle Grid Pattern for spatial orientation */}
                  <pattern id="graph-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                    <circle cx="20" cy="20" r="1" fill="var(--border)" opacity="0.4" />
                  </pattern>

                  {/* Glow filter for hovered / selected nodes */}
                  <filter id="node-glow" x="-30%" y="-30%" width="160%" height="160%">
                    <feDropShadow dx="0" dy="2" stdDeviation="4" floodColor="var(--brass)" floodOpacity="0.4" />
                  </filter>
                  <filter id="issue-glow" x="-30%" y="-30%" width="160%" height="160%">
                    <feDropShadow dx="0" dy="2" stdDeviation="5" floodColor="var(--primary)" floodOpacity="0.5" />
                  </filter>
                </defs>

                {/* Canvas Background */}
                <rect width={CANVAS_WIDTH} height={CANVAS_HEIGHT} fill="var(--surface)" />
                <rect width={CANVAS_WIDTH} height={CANVAS_HEIGHT} fill="url(#graph-grid)" />

                <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
                  {/* Semantic Cluster Region Labels */}
                  <g opacity="0.35" className="pointer-events-none select-none font-sans font-semibold text-[11px] uppercase tracking-widest fill-[var(--text-muted)]">
                    <text x={CANVAS_WIDTH * 0.5} y={40} textAnchor="middle">
                      Case Issues & Findings
                    </text>
                    <text x={120} y={CANVAS_HEIGHT * 0.4} textAnchor="start">
                      Statutory Provisions
                    </text>
                    <text x={CANVAS_WIDTH - 120} y={CANVAS_HEIGHT * 0.38} textAnchor="end">
                      Parties & Authorities
                    </text>
                    <text x={CANVAS_WIDTH * 0.5} y={CANVAS_HEIGHT - 35} textAnchor="middle">
                      Grounded Facts & Timeline
                    </text>
                  </g>

                  {/* Edges */}
                  {displayEdges.map((edge) => {
                    const src = nodePositions.get(edge.source_id);
                    const tgt = nodePositions.get(edge.target_id);
                    if (!src || !tgt) return null;

                    const isConnectedToFocus =
                      activeFocusId === edge.source_id || activeFocusId === edge.target_id;
                    const isDimmed = activeFocusId !== null && !isConnectedToFocus;

                    let strokeDash = "none";
                    let strokeColor = "var(--border-strong)";
                    let strokeWidth = 1;

                    if (edge.relation === "contradicts") {
                      strokeDash = "5,4";
                      strokeColor = "var(--danger)";
                      strokeWidth = isConnectedToFocus ? 2.5 : 1.5;
                    } else if (edge.relation === "applies_to") {
                      strokeDash = "3,3";
                      strokeColor = "#3B82F6";
                      strokeWidth = isConnectedToFocus ? 2 : 1.2;
                    } else if (edge.relation === "supports") {
                      strokeColor = "var(--brass)";
                      strokeWidth = isConnectedToFocus ? 2 : 1.2;
                    } else if (isConnectedToFocus) {
                      strokeColor = "var(--primary)";
                      strokeWidth = 2;
                    }

                    // Curved quadratic bezier curve for aesthetic clarity
                    const midX = (src.x + tgt.x) / 2;
                    const midY = (src.y + tgt.y) / 2;
                    const dx = tgt.x - src.x;
                    const dy = tgt.y - src.y;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const curveOffset = Math.min(25, dist * 0.08);
                    const ctrlX = midX - (dy / dist) * curveOffset;
                    const ctrlY = midY + (dx / dist) * curveOffset;

                    return (
                      <g key={edge.edge_id} opacity={isDimmed ? 0.12 : isConnectedToFocus ? 1 : 0.65} className="transition-opacity duration-150">
                        <path
                          d={`M ${src.x} ${src.y} Q ${ctrlX} ${ctrlY} ${tgt.x} ${tgt.y}`}
                          fill="none"
                          stroke={strokeColor}
                          strokeWidth={strokeWidth}
                          strokeDasharray={strokeDash}
                        />

                        {/* Edge Label on hover / focus */}
                        {isConnectedToFocus && (
                          <g transform={`translate(${ctrlX}, ${ctrlY})`}>
                            <rect
                              x="-34"
                              y="-9"
                              width="68"
                              height="18"
                              rx="4"
                              fill="var(--surface)"
                              stroke="var(--border)"
                              strokeWidth="1"
                            />
                            <text
                              textAnchor="middle"
                              dy="3.5"
                              fontSize="9.5"
                              fill="var(--text-muted)"
                              className="font-mono uppercase font-semibold pointer-events-none"
                            >
                              {edge.relation.replace(/[_-]+/g, " ")}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                  {/* Nodes */}
                  {positionedNodes.map((node) => {
                    const isSelected = selectedNodeId === node.node_id;
                    const isHovered = hoveredNodeId === node.node_id;
                    const isFocus = isSelected || isHovered;
                    const isDimmed = activeFocusId !== null && !activeNeighborIds.has(node.node_id);

                    const fill = getNodeFill(node.node_type);
                    const stroke = getNodeStroke(node.node_type);

                    // Determine whether to show text badge
                    const isHub = node.node_type === "issue" || (node.degree && node.degree >= 3);
                    const showLabel =
                      labelDensity === "all" ||
                      (labelDensity === "smart" && (isHub || isFocus || activeNeighborIds.has(node.node_id))) ||
                      (labelDensity === "minimal" && isFocus);

                    const cleanLabel =
                      node.label.length > 28 ? `${node.label.slice(0, 28)}…` : node.label;
                    const labelBadgeWidth = Math.min(220, cleanLabel.length * 6.8 + 14);

                    return (
                      <g
                        key={node.node_id}
                        transform={`translate(${node.x}, ${node.y})`}
                        opacity={isDimmed ? 0.18 : 1}
                        onMouseEnter={() => setHoveredNodeId(node.node_id)}
                        onMouseLeave={() => setHoveredNodeId(null)}
                        onMouseDown={(e) => handleNodeMouseDown(e, node)}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedNodeId(isSelected ? null : node.node_id);
                        }}
                        className="cursor-pointer group transition-opacity duration-150"
                      >
                        {/* Selected / Hover Halo */}
                        {isFocus && (
                          <circle
                            r={node.radius + 7}
                            fill="none"
                            stroke={node.node_type === "issue" ? "var(--primary)" : "var(--brass)"}
                            strokeWidth="2"
                            strokeDasharray="3,3"
                            className="animate-spin-slow"
                          />
                        )}

                        {/* Node Circle */}
                        <circle
                          r={node.radius}
                          fill={fill}
                          stroke={isFocus ? "var(--brass)" : stroke}
                          strokeWidth={isFocus ? 3 : node.node_type === "issue" ? 2.5 : 1.5}
                          filter={node.node_type === "issue" ? "url(#issue-glow)" : isFocus ? "url(#node-glow)" : undefined}
                          className="transition-transform duration-100"
                        />

                        {/* Node Type Icon / Monogram for prominent nodes */}
                        {node.node_type === "issue" && (
                          <text
                            textAnchor="middle"
                            dy="4"
                            fontSize="11"
                            fontWeight="bold"
                            fill="#FFFFFF"
                            className="pointer-events-none select-none font-sans"
                          >
                            §
                          </text>
                        )}

                        {/* Clean Pill Badge for Label */}
                        {showLabel && (
                          <g
                            transform={`translate(0, ${node.radius + 12})`}
                            className="pointer-events-none select-none"
                          >
                            <rect
                              x={-labelBadgeWidth / 2}
                              y="-8"
                              width={labelBadgeWidth}
                              height="18"
                              rx="5"
                              fill="var(--surface)"
                              stroke={isFocus ? "var(--brass)" : "var(--border)"}
                              strokeWidth={isFocus ? "1.5" : "1"}
                              className="shadow-xs"
                            />
                            <text
                              textAnchor="middle"
                              dy="4.5"
                              fontSize="10"
                              fill="var(--text)"
                              fontWeight={isFocus || node.node_type === "issue" ? "600" : "500"}
                              className="font-sans"
                            >
                              {cleanLabel}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}
                </g>
              </svg>

              {/* Legend & Instructions (Bottom Left) */}
              <div className="absolute bottom-3 left-3 bg-[var(--surface)]/95 backdrop-blur-md border border-[var(--border)] rounded-lg p-3 text-xs space-y-2 z-10 shadow-[var(--shadow-drawer)] max-w-xs">
                <div className="font-semibold text-[var(--text)] text-[11px] flex items-center justify-between">
                  <span>Knowledge Map</span>
                  <span className="text-[10px] font-normal text-[var(--text-muted)]">Drag nodes to arrange</span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px]">
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full bg-[var(--primary)] shrink-0" />
                    <span className="text-[var(--text)]">Case Issues</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full bg-[var(--brass)] shrink-0" />
                    <span className="text-[var(--text)]">Parties & Entities</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full bg-[#3B82F6] shrink-0" />
                    <span className="text-[var(--text)]">Legal Provisions</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full bg-[#EFECE6] border border-[var(--border-strong)] shrink-0" />
                    <span className="text-[var(--text)]">Extracted Facts</span>
                  </div>
                </div>
              </div>

              {/* Right Side Inspector Drawer: 360px */}
              {selectedNode && (
                <div className="absolute top-0 right-0 bottom-0 w-[360px] border-l border-[var(--border)] bg-[var(--surface)] p-5 overflow-y-auto space-y-4 shadow-[var(--shadow-drawer)] z-20">
                  <div className="flex items-center justify-between pb-3 border-b border-[var(--border)]">
                    <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 text-[11px] font-medium text-[var(--text)] capitalize">
                      {formatLabel(selectedNode.node_type)}
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedNodeId(null)}
                      className="text-[var(--text-muted)] hover:text-[var(--text)] p-1 rounded hover:bg-[var(--surface-2)]"
                      title="Close inspector"
                    >
                      <X className="size-4" />
                    </button>
                  </div>

                  <div>
                    <h3 className="font-serif text-base font-medium text-[var(--text)] leading-snug">
                      {selectedNode.label}
                    </h3>
                    {selectedNode.source_filename && (
                      <div className="mt-2">
                        <CitationChip
                          caseId={caseId}
                          documentId={selectedNode.source_document_id}
                          filename={selectedNode.source_filename}
                          locator={selectedNode.source_locator}
                          quote={selectedNode.evidence_quote || selectedNode.text || selectedNode.label}
                        />
                      </div>
                    )}
                  </div>

                  {selectedNode.text && selectedNode.text !== selectedNode.label && (
                    <div className="text-xs text-[var(--text-muted)] leading-relaxed bg-[var(--surface-2)] p-3 rounded-md border border-[var(--border)]">
                      {selectedNode.text}
                    </div>
                  )}

                  {/* Connected Neighbors */}
                  <div className="space-y-2 pt-2 border-t border-[var(--border)]">
                    <div className="text-xs font-semibold text-[var(--text)]">
                      Connected Nodes ({selectedNeighbors.length})
                    </div>
                    {selectedNeighbors.length === 0 ? (
                      <p className="text-xs text-[var(--text-muted)]">No direct connections.</p>
                    ) : (
                      <div className="space-y-1.5">
                        {selectedNeighbors.map(({ node, relation }, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => setSelectedNodeId(node.node_id)}
                            className="flex w-full items-center justify-between p-2 rounded bg-[var(--surface-2)] text-left text-xs hover:bg-[var(--primary-tint)] transition group"
                          >
                            <span className="font-medium text-[var(--text)] group-hover:text-[var(--primary)] truncate max-w-[200px]">
                              {node.label}
                            </span>
                            <span className="text-[10px] text-[var(--text-muted)] uppercase font-mono">
                              {relation.replace(/[_-]+/g, " ")}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Accessible List View */
            <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--surface)]">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-[var(--border)] text-xs text-[var(--text-muted)] font-medium bg-[var(--surface-2)]">
                  <tr>
                    <th className="py-2.5 px-4 font-medium">Node Label</th>
                    <th className="py-2.5 px-4 font-medium">Type</th>
                    <th className="py-2.5 px-4 font-medium text-right">Connections</th>
                    <th className="py-2.5 px-4 font-medium">Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {positionedNodes.map((n) => (
                    <tr
                      key={n.node_id}
                      onClick={() => {
                        setSelectedNodeId(n.node_id);
                        setViewMode("graph");
                      }}
                      className="cursor-pointer hover:bg-[var(--surface-2)] h-11 text-xs"
                    >
                      <td className="py-2 px-4 font-medium text-[var(--text)]">{n.label}</td>
                      <td className="py-2 px-4 capitalize text-[var(--text-muted)]">{formatLabel(n.node_type)}</td>
                      <td className="py-2 px-4 font-mono text-right text-[var(--text-muted)]">{n.degree || 0}</td>
                      <td className="py-2 px-4 text-[var(--text-muted)]">
                        {n.source_filename ? `${n.source_filename} · ${n.source_locator || ""}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </PageBody>
      )}
    </PageShell>
  );
}
