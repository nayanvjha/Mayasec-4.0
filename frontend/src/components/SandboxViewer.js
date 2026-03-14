import React from 'react';
import './SandboxViewer.css';

function SandboxViewer({ htmlContent }) {
  return (
    <div className="sandbox-container">
      <iframe
        title="Honeypot Environment"
        sandbox="allow-same-origin allow-scripts"
        srcDoc={htmlContent || ''}
        className="sandbox-frame"
      />
    </div>
  );
}

export default SandboxViewer;
