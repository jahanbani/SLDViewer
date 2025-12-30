import { useState } from 'react'
import GraphViewer from './components/GraphViewer'

function App() {
  const [fileId, setFileId] = useState<string>('')
  const [inputFileId, setInputFileId] = useState<string>('')

  const handleLoad = () => {
    if (inputFileId.trim()) {
      setFileId(inputFileId.trim())
    }
  }

  return (
    <div style={{ width: '100vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '20px', borderBottom: '1px solid #ddd', background: '#f5f5f5' }}>
        <h1 style={{ margin: '0 0 10px 0' }}>SLD Viewer</h1>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <label>
            File ID:
            <input
              type="text"
              value={inputFileId}
              onChange={(e) => setInputFileId(e.target.value)}
              placeholder="Enter file ID (UUID)"
              style={{ marginLeft: '8px', padding: '6px 12px', fontSize: '14px', width: '300px' }}
              onKeyPress={(e) => e.key === 'Enter' && handleLoad()}
            />
          </label>
          <button
            onClick={handleLoad}
            style={{
              padding: '6px 16px',
              fontSize: '14px',
              background: '#4285f4',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Load Graph
          </button>
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {fileId ? (
          <GraphViewer fileId={fileId} />
        ) : (
          <div
            style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              height: '100%',
              color: '#666',
            }}
          >
            Enter a file ID and click "Load Graph" to view
          </div>
        )}
      </div>
    </div>
  )
}

export default App

