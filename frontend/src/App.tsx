/**
 * Main App component for SLD Viewer.
 */
import { useState, useCallback } from 'react';
import { CaseLoader } from './components/CaseLoader';
import { GraphViewer } from './components/GraphViewer';
import { ErrorBoundary } from './components/ErrorBoundary';
import { CaseSummary } from './utils/api';

// Types for selection
type SelectionType = 'node' | 'edge';
interface SelectedElement {
  type: SelectionType;
  id: string;
  data: Record<string, unknown>;
}

export function App() {
  const [fileId, setFileId] = useState<string | null>(null);
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [centerBusNumber, setCenterBusNumber] = useState<number | null>(null);
  const [selectedElement, setSelectedElement] = useState<SelectedElement | null>(null);

  const handleCaseLoaded = useCallback((newFileId: string, newSummary: CaseSummary) => {
    setFileId(newFileId);
    setSummary(newSummary);
    setCenterBusNumber(null); // Reset center bus
    setSelectedElement(null);
  }, []);

  const handleBusSelected = useCallback((busNumber: number) => {
    setCenterBusNumber(busNumber);
    setSelectedElement(null);
  }, []);

  const handleNodeSelect = useCallback((nodeId: string, data: Record<string, unknown>) => {
    setSelectedElement({ type: 'node', id: nodeId, data });
  }, []);

  const handleEdgeSelect = useCallback((edgeId: string, data: Record<string, unknown>) => {
    setSelectedElement({ type: 'edge', id: edgeId, data });
  }, []);

  return (
    <div style={styles.app}>
      <header style={styles.header}>
        <h1 style={styles.title}>SLD Viewer</h1>
        {summary && (
          <span style={styles.summaryText}>
            {summary.bus_count} buses | {summary.ac_branch_count} branches | {summary.substation_count} substations
          </span>
        )}
      </header>

      <CaseLoader
        onCaseLoaded={handleCaseLoaded}
        onBusSelected={handleBusSelected}
        fileId={fileId}
      />

      <main style={styles.main}>
        <div style={styles.viewerContainer}>
          <ErrorBoundary>
            <GraphViewer
              fileId={fileId}
              centerBusNumber={centerBusNumber}
              onNodeSelect={handleNodeSelect}
              onEdgeSelect={handleEdgeSelect}
            />
          </ErrorBoundary>
        </div>

        {selectedElement && (
          <aside style={styles.sidebar}>
            <h3 style={styles.sidebarTitle}>
              {selectedElement.type === 'node' ? 'Selected Node' : 'Selected Edge'}
            </h3>
            <div style={styles.elementDetails}>
              {/* Common fields */}
              <p><strong>ID:</strong> {selectedElement.id}</p>
              {selectedElement.data.kind !== undefined && (
                <p><strong>Kind:</strong> {String(selectedElement.data.kind)}</p>
              )}

              {/* In Service status */}
              {selectedElement.data.inService !== undefined && (
                <p>
                  <strong>In Service:</strong>{' '}
                  <span style={{ color: selectedElement.data.inService ? '#28a745' : '#dc3545' }}>
                    {selectedElement.data.inService ? 'Yes' : 'No'}
                  </span>
                </p>
              )}

              {/* Bus-specific fields */}
              {selectedElement.data.kind === 'bus' && (
                <>
                  {selectedElement.data.psse_number !== undefined && (
                    <p><strong>Bus #:</strong> {selectedElement.data.psse_number as number}</p>
                  )}
                  {selectedElement.data.name !== undefined && selectedElement.data.name !== null && (
                    <p><strong>Name:</strong> {String(selectedElement.data.name)}</p>
                  )}
                  {selectedElement.data.base_kv !== undefined && (
                    <p><strong>Base kV:</strong> {selectedElement.data.base_kv as number}</p>
                  )}
                  {selectedElement.data.bfs_depth !== undefined && (
                    <p><strong>BFS Depth:</strong> {selectedElement.data.bfs_depth as number}</p>
                  )}
                </>
              )}

              {/* Equipment-specific fields (generator, load, shunt) */}
              {selectedElement.data.kind === 'equipment' && (
                <>
                  {selectedElement.data.equipment_type && (
                    <p><strong>Type:</strong> {String(selectedElement.data.equipment_type)}</p>
                  )}
                  {selectedElement.data.psse_id && (
                    <p><strong>PSSE ID:</strong> {String(selectedElement.data.psse_id)}</p>
                  )}
                  {selectedElement.data.bus_number !== undefined && (
                    <p><strong>Bus #:</strong> {selectedElement.data.bus_number as number}</p>
                  )}
                  {selectedElement.data.mw !== undefined && (
                    <p><strong>MW:</strong> {(selectedElement.data.mw as number).toFixed(2)}</p>
                  )}
                  {selectedElement.data.mvar !== undefined && (
                    <p><strong>Mvar:</strong> {(selectedElement.data.mvar as number).toFixed(2)}</p>
                  )}
                  {selectedElement.data.mva !== undefined && (
                    <p><strong>MVA:</strong> {(selectedElement.data.mva as number).toFixed(2)}</p>
                  )}
                </>
              )}

              {/* Transformer fields */}
              {(selectedElement.data.kind === 'transformer' || selectedElement.data.kind === 'transformer3') && (
                <>
                  {selectedElement.data.name && (
                    <p><strong>Name:</strong> {String(selectedElement.data.name)}</p>
                  )}
                  {selectedElement.data.psse_id && (
                    <p><strong>PSSE ID:</strong> {String(selectedElement.data.psse_id)}</p>
                  )}
                  {selectedElement.data.mva_rating !== undefined && (
                    <p><strong>MVA Rating:</strong> {(selectedElement.data.mva_rating as number).toFixed(1)}</p>
                  )}
                </>
              )}

              {/* Terminal fields */}
              {selectedElement.data.kind === 'terminal' && (
                <>
                  {selectedElement.data.parentBusId && (
                    <p><strong>Parent Bus:</strong> {String(selectedElement.data.parentBusId)}</p>
                  )}
                  {selectedElement.data.side && (
                    <p><strong>Side:</strong> {String(selectedElement.data.side)}</p>
                  )}
                  {selectedElement.data.slotIndex !== undefined && (
                    <p><strong>Slot:</strong> {selectedElement.data.slotIndex as number}</p>
                  )}
                </>
              )}

              {/* Edge-specific fields (branch, transformer leg) */}
              {selectedElement.type === 'edge' && (
                <>
                  {selectedElement.data.source && (
                    <p><strong>Source:</strong> {String(selectedElement.data.source)}</p>
                  )}
                  {selectedElement.data.target && (
                    <p><strong>Target:</strong> {String(selectedElement.data.target)}</p>
                  )}
                  {selectedElement.data.from_bus !== undefined && (
                    <p><strong>From Bus:</strong> {selectedElement.data.from_bus as number}</p>
                  )}
                  {selectedElement.data.to_bus !== undefined && (
                    <p><strong>To Bus:</strong> {selectedElement.data.to_bus as number}</p>
                  )}
                  {selectedElement.data.circuit_id && (
                    <p><strong>Circuit ID:</strong> {String(selectedElement.data.circuit_id)}</p>
                  )}
                  {selectedElement.data.length_km !== undefined && (
                    <p><strong>Length:</strong> {(selectedElement.data.length_km as number).toFixed(2)} km</p>
                  )}
                  {selectedElement.data.r_pu !== undefined && (
                    <p><strong>R (pu):</strong> {(selectedElement.data.r_pu as number).toFixed(5)}</p>
                  )}
                  {selectedElement.data.x_pu !== undefined && (
                    <p><strong>X (pu):</strong> {(selectedElement.data.x_pu as number).toFixed(5)}</p>
                  )}
                  {selectedElement.data.rate_a !== undefined && (
                    <p><strong>Rate A:</strong> {(selectedElement.data.rate_a as number).toFixed(1)} MVA</p>
                  )}
                </>
              )}
            </div>
          </aside>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    height: '100%',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
    padding: '10px 20px',
    backgroundColor: '#343a40',
    color: 'white',
  },
  title: {
    margin: 0,
    fontSize: '20px',
    fontWeight: 600,
  },
  summaryText: {
    fontSize: '14px',
    opacity: 0.8,
  },
  main: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },
  viewerContainer: {
    flex: 1,
    overflow: 'hidden',
  },
  sidebar: {
    width: '280px',
    borderLeft: '1px solid #ddd',
    backgroundColor: '#fff',
    padding: '15px',
    overflowY: 'auto',
  },
  sidebarTitle: {
    margin: '0 0 15px 0',
    fontSize: '16px',
    fontWeight: 600,
    color: '#333',
  },
  elementDetails: {
    fontSize: '14px',
    lineHeight: 1.6,
  },
};
