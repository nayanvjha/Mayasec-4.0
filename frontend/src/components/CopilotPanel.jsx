import React, { useState, useRef, useEffect, useCallback } from 'react';
import './CopilotPanel.css';

const API_TOKEN = process.env.REACT_APP_ADMIN_TOKEN || '';

function CopilotPanel({ apiUrl }) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(scrollToBottom, [messages]);

  // Cmd+K shortcut
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsOpen((prev) => !prev);
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const sendQuery = useCallback(async () => {
    if (!input.trim() || loading) return;

    const userMsg = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const headers = { 'Content-Type': 'application/json' };
      if (API_TOKEN) headers.Authorization = `Bearer ${API_TOKEN}`;

      const res = await fetch(`${apiUrl}/api/v1/copilot/query`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ query: userMsg.content, session_id: 'dashboard' }),
      });
      const data = await res.json();
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer || 'No response from copilot.',
          tool_used: data.tool_used || '',
          latency_ms: data.latency_ms || 0,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, apiUrl]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendQuery();
    }
  };

  if (!isOpen) {
    return (
      <button
        className="copilot-toggle"
        onClick={() => {
          setIsOpen(true);
          setTimeout(() => inputRef.current?.focus(), 100);
        }}
        title="Open Copilot (⌘K)"
      >
        🤖 Copilot
      </button>
    );
  }

  return (
    <div className="copilot-panel">
      <div className="copilot-header">
        <span>🤖 MAYASEC Copilot</span>
        <div className="copilot-header-actions">
          <span className="copilot-shortcut">⌘K</span>
          <button onClick={() => setIsOpen(false)} className="copilot-close">✕</button>
        </div>
      </div>

      <div className="copilot-messages">
        {messages.length === 0 && (
          <div className="copilot-empty">
            <p>Ask me about your security events:</p>
            <ul>
              <li>"Why was 10.0.0.1 flagged?"</li>
              <li>"Show critical events from the last hour"</li>
              <li>"Is the ML model drifting?"</li>
              <li>"List active sessions"</li>
            </ul>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`copilot-msg copilot-msg-${msg.role}`}>
            <div className="copilot-msg-content">{msg.content}</div>
            {msg.tool_used && (
              <div className="copilot-msg-meta">
                🔧 {msg.tool_used} · {msg.latency_ms}ms
              </div>
            )}
          </div>
        ))}

        {loading && <div className="copilot-msg copilot-msg-loading">Thinking...</div>}
        <div ref={messagesEndRef} />
      </div>

      <div className="copilot-input-row">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about security events..."
          disabled={loading}
          className="copilot-input"
        />
        <button onClick={sendQuery} disabled={loading || !input.trim()} className="copilot-send">
          Send
        </button>
      </div>
    </div>
  );
}

export default CopilotPanel;
