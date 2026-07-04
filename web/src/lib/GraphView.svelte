<script>
  import { onMount, onDestroy } from "svelte";

  let { refresh = false } = $props();

  let container;
  let network = null;
  let loading = $state(true);
  let stats = $state({ nodes: 0, predicates: 0, triples: 0 });

  const NODE_COLORS = {
    subject: "#4361ee",
    object: "#2ec4b6",
    literal: "#ff9f1c",
  };

  onMount(async () => {
    await loadGraph();
  });

  $effect(() => {
    if (refresh) {
      loadGraph();
    }
  });

  onDestroy(() => {
    if (network) {
      network.destroy();
      network = null;
    }
  });

  async function loadGraph() {
    loading = true;
    try {
      // Load stats
      const statsRes = await fetch("/api/v1/query/stats");
      stats = await statsRes.json();

      // Load triples for graph
      const triplesRes = await fetch("/api/v1/graph/triples?limit=500");
      const triplesData = await triplesRes.json();
      const triples = triplesData.triples || [];

      // Load nodes for labels
      const nodesRes = await fetch("/api/v1/graph/nodes?limit=500");
      const nodesData = await nodesRes.json();
      const nodeMap = {};
      for (const n of nodesData.nodes || []) {
        try {
          const labels = typeof n.labels === "string" ? JSON.parse(n.labels) : (n.labels || {});
          const label = Object.values(labels).find(v => v) || n.node_id;
          nodeMap[n.node_id] = label;
        } catch { nodeMap[n.node_id] = n.node_id; }
      }

      // Load predicates for edge labels
      const predRes = await fetch("/api/v1/graph/predicates?limit=200");
      const predData = await predRes.json();
      const predMap = {};
      for (const p of predData.predicates || []) {
        try {
          const labels = typeof p.labels === "string" ? JSON.parse(p.labels) : (p.labels || {});
          predMap[p.predicate_id] = Object.values(labels).find(v => v) || p.predicate_id;
        } catch { predMap[p.predicate_id] = p.predicate_id; }
      }

      buildVisGraph(triples, nodeMap, predMap);
    } catch (err) {
      console.error("Failed to load graph:", err);
    }
    loading = false;
  }

  function buildVisGraph(triples, nodeMap, predMap) {
    if (!container) return;

    // Collect unique node IDs
    const nodeIds = new Set();
    const edges = [];
    for (const t of triples) {
      nodeIds.add(t.subject_id);
      if (t.object_type === "uri") {
        nodeIds.add(t.object_value);
      }
    }

    // Create nodes
    const nodes = new vis.DataSet(
      Array.from(nodeIds).map(id => ({
        id,
        label: nodeMap[id] || id.slice(0, 12),
        color: NODE_COLORS.subject,
        shape: "dot",
        size: 20,
        title: `ID: ${id}`,
      }))
    );

    // Create edges
    for (const t of triples) {
      const predLabel = predMap[t.predicate_id] || t.predicate_id;
      edges.push({
        from: t.subject_id,
        to: t.object_type === "uri" ? t.object_value : t.object_value.slice(0, 20),
        label: predLabel,
        arrows: "to",
        color: { color: "#888", highlight: "#4a90d9" },
        font: { size: 10, color: "#666" },
        width: 1,
      });

      // Add literal objects as box nodes
      if (t.object_type !== "uri") {
        const litId = `lit-${t.subject_id}-${t.predicate_id}-${t.object_value.slice(0, 10)}`;
        if (!nodes.get(litId)) {
          nodes.add({
            id: litId,
            label: t.object_value.slice(0, 20),
            color: NODE_COLORS.literal,
            shape: "box",
            size: 15,
          });
        }
      }
    }

    const data = { nodes, edges };

    const options = {
      nodes: {
        borderWidth: 2,
        font: { size: 12, color: "#333" },
      },
      edges: {
        smooth: { type: "continuous" },
      },
      physics: {
        solver: "barnesHut",
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.3,
          springLength: 200,
          springConstant: 0.04,
        },
        stabilization: { iterations: 100 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
      },
    };

    if (network) network.destroy();
    network = new vis.Network(container, data, options);

    // Click handler — expand node
    network.on("click", async function(params) {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        await expandNode(nodeId, nodes, edges, nodeMap, predMap);
      }
    });
  }

  async function expandNode(nodeId, nodes, edges, nodeMap, predMap) {
    try {
      const res = await fetch(`/api/v1/graph/triples/by-subject/${encodeURIComponent(nodeId)}`);
      const data = await res.json();
      const triples = data.triples || [];

      for (const t of triples) {
        if (!nodes.get(t.subject_id)) {
          nodes.add({
            id: t.subject_id,
            label: nodeMap[t.subject_id] || t.subject_id.slice(0, 12),
            color: NODE_COLORS.object,
            shape: "dot",
            size: 18,
          });
        }
        if (t.object_type === "uri" && !nodes.get(t.object_value)) {
          nodes.add({
            id: t.object_value,
            label: nodeMap[t.object_value] || t.object_value.slice(0, 12),
            color: NODE_COLORS.object,
            shape: "dot",
            size: 18,
          });
        }
        const edgeId = `${t.subject_id}-${t.predicate_id}-${t.object_value}`;
        if (!edges.get(edgeId)) {
          edges.add({
            id: edgeId,
            from: t.subject_id,
            to: t.object_type === "uri" ? t.object_value : `lit-${t.subject_id}-${t.predicate_id}-${t.object_value.slice(0, 10)}`,
            label: predMap[t.predicate_id] || t.predicate_id,
            arrows: "to",
            color: { color: "#888" },
            font: { size: 10 },
          });
        }
      }
    } catch (err) {
      console.error("Failed to expand node:", err);
    }
  }
</script>

<div class="graph-view">
  {#if loading}
    <div class="loading">Loading graph…</div>
  {/if}

  <div class="graph-controls">
    <span class="stats">
      {stats.nodes} nodes · {stats.predicates} predicates · {stats.triples} triples
    </span>
    <button onclick={loadGraph}>⟳ Refresh</button>
  </div>

  <div bind:this={container} class="graph-container"></div>
</div>

<style>
  .graph-view {
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .graph-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid #eee;
    font-size: 0.85rem;
    color: #666;
  }
  .graph-controls button {
    padding: 0.25rem 0.75rem;
    border: 1px solid #ccc;
    background: #fff;
    border-radius: 4px;
    cursor: pointer;
  }
  .graph-controls button:hover { background: #f0f0f0; }
  .graph-container {
    flex: 1;
    min-height: 400px;
    border: 1px solid #eee;
  }
  .loading {
    padding: 2rem;
    text-align: center;
    color: #999;
  }
</style>
