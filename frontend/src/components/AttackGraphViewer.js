import { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import './AttackGraphViewer.css';

function AttackGraphViewer({ apiUrl }) {
  const svgRef = useRef(null);
  const [graphData, setGraphData] = useState({ nodes: [], links: [] });
  const [selectedNode, setSelectedNode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchGraph = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/graph/attack`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
      }

      const data = await response.json();
      const normalized = {
        nodes: Array.isArray(data?.nodes) ? data.nodes : [],
        links: Array.isArray(data?.links) ? data.links : [],
      };

      setGraphData(normalized);
      setLoading(false);

      if (normalized.nodes.length === 0) {
        setError(null);
      } else {
        setError(null);
      }
    } catch {
      setError('Graph unavailable');
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    fetchGraph();
    const intervalId = setInterval(fetchGraph, 10000);

    return () => clearInterval(intervalId);
  }, [fetchGraph]);

  useEffect(() => {
    const svgElement = svgRef.current;
    if (!svgElement) {
      return undefined;
    }

    d3.select(svgElement).selectAll('*').remove();

    if (graphData.nodes.length === 0) {
      return undefined;
    }

    const container = svgElement.parentElement;
    const width = container?.clientWidth || 800;
    const height = container?.clientHeight || 500;

    const svg = d3
      .select(svgElement)
      .attr('width', width)
      .attr('height', height);

    svg
      .append('defs')
      .append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 0 10 10')
      .attr('refX', 18)
      .attr('refY', 5)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M 0 0 L 10 5 L 0 10 z')
      .attr('fill', 'rgba(0,255,159,0.6)');

    const graphGroup = svg.append('g');

    const nodes = graphData.nodes.map((node) => ({ ...node }));
    const links = graphData.links.map((link) => ({ ...link }));

    const simulation = d3
      .forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((d) => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collide', d3.forceCollide(30));

    const link = graphGroup
      .append('g')
      .selectAll('line')
      .data(links)
      .enter()
      .append('line')
      .attr('stroke', 'rgba(0, 255, 159, 0.4)')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrowhead)');

    const nodeColor = (type) => {
      if (type === 'AttackerIP') return '#ef5350';
      if (type === 'HoneypotTarget') return '#00bcd4';
      if (type === 'MITRETechnique') return '#ff9800';
      if (type === 'Credential') return '#ffeb3b';
      return '#888888';
    };

    const truncate = (value) => {
      const text = String(value ?? '');
      return text.length > 12 ? `${text.slice(0, 12)}...` : text;
    };

    const drag = d3
      .drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event, d) => {
        d.fx = event.x;
        d.fy = event.y;
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    const node = graphGroup
      .append('g')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .on('click', (_, d) => {
        setSelectedNode(d);
      })
      .call(drag);

    node
      .append('circle')
      .attr('r', 14)
      .attr('fill', (d) => nodeColor(d.type));

    node
      .append('text')
      .text((d) => truncate(d.label))
      .attr('font-size', '10px')
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('fill', '#ffffff')
      .attr('text-anchor', 'middle')
      .attr('y', 22);

    simulation.on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y);

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });

    const zoom = d3
      .zoom()
      .scaleExtent([0.2, 3])
      .on('zoom', (event) => {
        graphGroup.attr('transform', event.transform);
      });

    svg.call(zoom);

    return () => {
      simulation.stop();
    };
  }, [graphData]);

  return (
    <div className="attack-graph-panel">
      {loading && <div className="graph-empty-state">Connecting to graph...</div>}
      {error && <div className="graph-empty-state graph-error">{error}</div>}
      {!loading && !error && graphData.nodes.length === 0 && (
        <div className="graph-empty-state">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#00ff9f" strokeWidth="1.5">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
          <p>No attack graph data yet</p>
          <span>Start an attack simulation or press Ctrl+Shift+D</span>
        </div>
      )}
      <svg ref={svgRef} className="graph-svg" />
      {selectedNode && (
        <div className="node-popup">
          <button className="popup-close" onClick={() => setSelectedNode(null)}>×</button>
          <div className="popup-type">{selectedNode.type}</div>
          <div className="popup-label">{selectedNode.label}</div>
          {selectedNode.properties && Object.entries(selectedNode.properties).map(([k, v]) => (
            <div key={k} className="popup-prop">
              <span className="prop-key">{k}:</span>
              <span className="prop-val">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="graph-legend">
        {[
          { color: '#ef5350', label: 'Attacker IP' },
          { color: '#00bcd4', label: 'Honeypot' },
          { color: '#ff9800', label: 'MITRE TTP' },
          { color: '#ffeb3b', label: 'Credential' },
        ].map(({ color, label }) => (
          <div key={label} className="legend-item">
            <span className="legend-dot" style={{ background: color }} />
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default AttackGraphViewer;
