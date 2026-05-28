from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.knowledge_graph import KnowledgeGraphResponse
from app.services.knowledge_graph import KnowledgeGraphService

router = APIRouter(tags=["knowledge-graph"])

knowledge_graph_service = KnowledgeGraphService()


@router.get("/api/knowledge-graph", response_model=KnowledgeGraphResponse)
async def get_knowledge_graph(
    document_id: int | None = Query(None, description="Filter by document ID"),
    group_id: int | None = Query(None, description="Filter by group ID"),
    entity: str | None = Query(None, description="Filter by entity name"),
    relationship_type: str | None = Query(None, description="Filter by relationship type"),
    limit: int = Query(500, ge=1, le=2000, description="Maximum number of document nodes"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeGraphResponse:
    """Get knowledge graph data with optional filters."""
    return await knowledge_graph_service.build_graph(
        db=db,
        document_id=document_id,
        group_id=group_id,
        entity=entity,
        relationship_type=relationship_type,
        limit=limit,
    )


@router.get("/api/knowledge-graph/view", response_class=HTMLResponse)
async def knowledge_graph_view(
    current_user: User = Depends(get_current_user),
) -> HTMLResponse:
    """Return an HTML page with interactive vis.js knowledge graph."""
    html_content = _build_knowledge_graph_html()
    return HTMLResponse(content=html_content)


def _build_knowledge_graph_html() -> str:
    """Build the interactive knowledge graph HTML page."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knowledge Graph</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        #graph-container { width: 100%; height: 600px; border: 1px solid #ccc; background: #fff; }
        .controls { margin-bottom: 15px; display: flex; gap: 10px; flex-wrap: wrap; }
        .controls input, .controls select, .controls button {
            padding: 8px 12px; border: 1px solid #ccc; border-radius: 4px;
        }
        .controls button { background: #4f46e5; color: #fff; border: none; cursor: pointer; }
        .controls button:hover { background: #4338ca; }
        h1 { margin-top: 0; }
    </style>
</head>
<body>
    <h1>Knowledge Graph</h1>
    <div class="controls">
        <input type="number" id="filter-doc-id" placeholder="Document ID" />
        <input type="number" id="filter-group-id" placeholder="Group ID" />
        <input type="text" id="filter-entity" placeholder="Entity" />
        <select id="filter-rel-type">
            <option value="">All Relationship Types</option>
            <option value="parent">Parent</option>
            <option value="child">Child</option>
            <option value="related">Related</option>
            <option value="supersedes">Supersedes</option>
            <option value="references">References</option>
            <option value="cites">Cites</option>
        </select>
        <button onclick="loadGraph()">Load Graph</button>
    </div>
    <div id="graph-container"></div>

    <script>
        let network = null;

        const nodeColors = {
            document: '#4f46e5',
            group: '#059669',
            entity: '#d97706',
            topic: '#dc2626'
        };

        async function loadGraph() {
            const docId = document.getElementById('filter-doc-id').value;
            const groupId = document.getElementById('filter-group-id').value;
            const entity = document.getElementById('filter-entity').value;
            const relType = document.getElementById('filter-rel-type').value;

            const params = new URLSearchParams();
            if (docId) params.append('document_id', docId);
            if (groupId) params.append('group_id', groupId);
            if (entity) params.append('entity', entity);
            if (relType) params.append('relationship_type', relType);

            try {
                const response = await fetch('/api/knowledge-graph?' + params.toString());
                if (!response.ok) {
                    alert('Failed to load graph data');
                    return;
                }
                const data = await response.json();
                renderGraph(data);
            } catch (err) {
                alert('Error loading graph: ' + err.message);
            }
        }

        function renderGraph(data) {
            const nodes = new vis.DataSet(
                data.nodes.map(n => ({
                    id: n.id,
                    label: n.label,
                    color: nodeColors[n.type] || '#6b7280',
                    title: n.type + ': ' + n.label,
                    shape: n.type === 'group' ? 'box' : (n.type === 'document' ? 'dot' : 'diamond')
                }))
            );

            const edges = new vis.DataSet(
                data.edges.map((e, i) => ({
                    id: i,
                    from: e.source,
                    to: e.target,
                    label: e.label,
                    arrows: 'to',
                    title: e.type
                }))
            );

            const container = document.getElementById('graph-container');
            const graphData = { nodes: nodes, edges: edges };
            const options = {
                physics: { stabilization: { iterations: 100 } },
                interaction: { hover: true, tooltipDelay: 200 },
                edges: { font: { size: 10 }, smooth: { type: 'continuous' } },
                nodes: { font: { size: 14 } }
            };

            if (network) {
                network.destroy();
            }
            network = new vis.Network(container, graphData, options);
        }

        // Load graph on page load
        loadGraph();
    </script>
</body>
</html>"""
