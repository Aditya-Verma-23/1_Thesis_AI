import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';
import FilterPanel from './components/FilterPanel';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';

const BACKEND_URL = 'http://localhost:8888';

const TAB_CONFIG = {
  qa: {
    greeting: 'What would you like to research today?',
    placeholder: 'Ask any research question…',
    chips: [
      'What are the main causes of climate change?',
      'How does CRISPR gene editing work?',
      'What is the latest research on transformer efficiency?',
    ],
  },
  lit: {
    greeting: 'Generate a comprehensive literature review',
    placeholder: 'Enter your research topic for a literature review…',
    chips: [
      'Literature review on deep learning in medical imaging',
      'Literature review on climate change adaptation strategies',
      'Summarise the literature on large language models',
    ],
  },
  sys: {
    greeting: 'Run a systematic review with PRISMA methodology',
    placeholder: 'Describe your systematic review question (PICO format recommended)…',
    chips: [
      'Systematic review: effectiveness of CBT for depression in adults',
      'PRISMA review on mRNA vaccines safety and efficacy',
      'Systematic review of renewable energy adoption barriers',
    ],
  },
  data: {
    greeting: 'Analyse and visualise research data',
    placeholder: 'Describe what data you want to analyse or visualise…',
    chips: [
      'Analyse publication trends in AI research 2015–2024',
      'Compare citation counts across climate science journals',
      'Visualise co-authorship networks in machine learning',
    ],
  },
  gaps: {
    greeting: 'Identify open research gaps in your field',
    placeholder: 'Enter a research area to find unexplored gaps…',
    chips: [
      'Research gaps in federated learning for healthcare',
      'Unexplored areas in quantum computing error correction',
      'What are the open problems in multi-modal LLMs?',
    ],
  },
  chat: {
    greeting: 'Chat with a specific paper or document',
    placeholder: 'Paste a DOI, arXiv ID, or URL — then ask questions about it…',
    chips: [
      'arxiv:2303.08774 — summarise key contributions',
      'doi:10.1038/s41586-021-03819-2 — explain the methods',
      'https://arxiv.org/abs/2005.14165 — what are the limitations?',
    ],
  },
};

function timeStr() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

function domainOf(url) {
  try { return new URL(url).hostname.replace('www.', ''); } catch { return ''; }
}

export default function App() {
  const [activeTab, setActiveTab]         = useState('qa');
  const [chatStarted, setChatStarted]     = useState(false);
  const [query, setQuery]                 = useState('');
  const [messages, setMessages]           = useState([]);
  const [isLoading, setIsLoading]         = useState(false);
  const [stage, setStage]                 = useState('');
  const [sources, setSources]             = useState(['papers', 'web']);
  const [isFilterOpen, setIsFilterOpen]   = useState(false);
  const [filters, setFilters]             = useState(null);
  const [isBackendReady, setIsBackendReady] = useState(false);
  const [backendStatusMsg, setBackendStatusMsg] = useState('Connecting to backend…');
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [recentQueries, setRecentQueries] = useState(() =>
    JSON.parse(localStorage.getItem('thesisai_recent') || '[]')
  );

  const chatEndRef = useRef(null);

  // Backend health check
  useEffect(() => {
    let tid;
    const check = async () => {
      try {
        const ctrl = new AbortController();
        const id = setTimeout(() => ctrl.abort(), 3000);
        const res = await fetch(`${BACKEND_URL}/health`, { signal: ctrl.signal });
        clearTimeout(id);
        if (res.ok) setIsBackendReady(true);
        else { setBackendStatusMsg('Backend not ready yet…'); tid = setTimeout(check, 2000); }
      } catch {
        setBackendStatusMsg('Backend is offline. Please start it (port 8888).');
        tid = setTimeout(check, 2000);
      }
    };
    check();
    return () => clearTimeout(tid);
  }, []);

  // Auto-scroll
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, stage]);

  const toggleSource = (src) =>
    setSources(prev => prev.includes(src) ? prev.filter(s => s !== src) : [...prev, src]);

  const submitQuery = useCallback(async (text) => {
    const q = text.trim();
    if (!q || isLoading) return;

    setChatStarted(true);
    setIsLoading(true);
    setQuery('');
    setStage('Connecting to backend…');

    setMessages(prev => [
      ...prev,
      { role: 'user',      content: q },
      { role: 'assistant', content: '', results: [], sessionId: null },
    ]);

    // Save to recents
    const newRecents = [{ text: q, time: timeStr() }, ...recentQueries.filter(r => r.text !== q)].slice(0, 10);
    setRecentQueries(newRecents);
    localStorage.setItem('thesisai_recent', JSON.stringify(newRecents));

    try {
      const res = await fetch(`${BACKEND_URL}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, filters: filters, sources: sources }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let   buffer  = '';

      const updateLast = (fn) =>
        setMessages(prev => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], ...fn(next[next.length - 1]) };
          return next;
        });

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(part.slice(6));
            if (data.type === 'stage')  { setStage(data.message); }
            else if (data.type === 'result') { updateLast(p => ({ ...p, results: data.results || [] })); setStage(''); }
            else if (data.type === 'token')  { updateLast(p => ({ ...p, content: p.content + data.content })); }
            else if (data.type === 'done')   { updateLast(p => ({ ...p, sessionId: data.session_id })); setStage(''); setIsLoading(false); }
            else if (data.type === 'error')  { setStage(`Error: ${data.message}`); setIsLoading(false); }
          } catch { /* skip */ }
        }
      }
    } catch (err) {
      setStage(`Connection failed: ${err.message}`);
      setIsLoading(false);
    }
  }, [isLoading, recentQueries]);

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuery(query); }
  };

  const handleDownload = (sessionId) => {
    if (sessionId) window.open(`${BACKEND_URL}/api/download/${sessionId}`, '_blank');
  };

  const resetChat = () => { setChatStarted(false); setMessages([]); setStage(''); setQuery(''); };

  const cfg = TAB_CONFIG[activeTab];

  return (
    <div className="app">

      {/* Backend overlay */}
      {!isBackendReady && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(253,243,245,0.97)',
          zIndex: 9999, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 12,
        }}>
          <div style={{
            width: 52, height: 52, borderRadius: 14, background: 'var(--maroon)',
            color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 26, fontWeight: 700, marginBottom: 8,
          }}>T</div>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{backendStatusMsg}</h2>
          <p style={{ color: 'var(--ink-soft)', maxWidth: 440, textAlign: 'center', fontSize: 13.5 }}>
            Run the command below in a terminal, then this screen will disappear.
          </p>
          <code style={{
            background: 'var(--pink-tint-2)', border: '1px solid var(--line)',
            borderRadius: 8, padding: '8px 14px', fontSize: 12, color: 'var(--maroon)',
          }}>
            cd backend &amp;&amp; .venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 8888 --reload
          </code>
          <div style={{
            width: 10, height: 10, borderRadius: '50%', background: 'var(--maroon)',
            marginTop: 8, animation: 'pulse 1.1s infinite ease-in-out',
          }} />
        </div>
      )}

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">T</div>
          <div className="brand-name">Thesis<em>AI</em></div>
        </div>

        <button className="new-chat-btn" onClick={resetChat}>
          <span className="new-chat-icon">+</span>
          <span className="nav-label">New chat</span>
        </button>

        <div className="nav-group">
          <div className="nav-item"><span className="icon">✎</span><span className="nav-label">AI Writer</span></div>
          <div className="nav-item"><span className="icon">▤</span><span className="nav-label">Library</span></div>
          <div className="nav-item"><span className="icon">⚗</span><span className="nav-label">Systematic Review</span></div>
          <div className="nav-item active"><span className="icon">◷</span><span className="nav-label">Recents</span></div>
        </div>

        <div className="nav-divider" />

        <div className="sidebar-search">
          <span className="icon">🔍</span>
          <input
            type="text"
            className="nav-label"
            placeholder="Search…"
            value={sidebarSearch}
            onChange={e => setSidebarSearch(e.target.value)}
            style={{ border: 'none', background: 'transparent', outline: 'none', width: '100%', fontSize: '13px', color: 'var(--ink)' }}
          />
        </div>

        {recentQueries
          .filter(r => r.text.toLowerCase().includes(sidebarSearch.toLowerCase()))
          .slice(0, 6)
          .map((r, i) => (
            <div key={i} className="recent-item" onClick={() => submitQuery(r.text)}>
              <div>
                <div className="recent-text">{r.text}</div>
                <div className="recent-meta">{r.time}</div>
              </div>
            </div>
          ))}

        {recentQueries.length === 0 && (
          <div className="sidebar-empty">No queries yet</div>
        )}
      </aside>

      {/* Main */}
      <main className="main">
        <div className="topbar">
          <div className="avatar">AV</div>
        </div>

        <div className="content">
          <div className="content-inner">

            {!chatStarted ? (
              /* Home view */
              <div id="homeView">
                <div className="watermark">THESIS</div>
                <h1 className="greeting" id="greeting">Welcome back, Aditya</h1>
                <p className="sub-greeting">{cfg.greeting}</p>

                {/* Workflow tabs */}
                <div className="workflow-tabs" id="workflowTabs">
                  {Object.keys(TAB_CONFIG).map(key => (
                    <div
                      key={key}
                      className={`tab ${activeTab === key ? 'active' : ''}`}
                      onClick={() => setActiveTab(key)}
                    >
                      {key === 'qa'   && '🎯 Quick Q/A'}
                      {key === 'lit'  && '📚 Literature review'}
                      {key === 'sys'  && '⚗ Systematic review'}
                      {key === 'data' && '📈 Data analysis'}
                      {key === 'gaps' && '🔍 Research gaps'}
                      {key === 'chat' && '💬 Paper chat'}
                    </div>
                  ))}
                </div>

                {/* Composer */}
                <div className="composer">
                  <textarea
                    id="queryInput"
                    placeholder={cfg.placeholder}
                    rows="3"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKey}
                  />
                  <div className="composer-toolbar">
                    <div className="toolbar-left">
                      <button
                        className={`toolbar-btn ${sources.includes('papers') ? 'selected' : ''}`}
                        onClick={() => toggleSource('papers')}
                      >
                        📄 Papers {sources.includes('papers') ? '✓' : ''}
                      </button>
                      <button
                        className={`toolbar-btn ${sources.includes('web') ? 'selected' : ''}`}
                        onClick={() => toggleSource('web')}
                      >
                        🌐 Internet {sources.includes('web') ? '✓' : ''}
                      </button>
                      <button className="toolbar-btn" onClick={() => setIsFilterOpen(true)}>
                        ⚙ Filters
                      </button>
                    </div>
                    <div className="toolbar-right">
                      <button
                        id="sendBtn"
                        className="send-btn"
                        onClick={() => submitQuery(query)}
                        disabled={isLoading || !query.trim()}
                      >↑</button>
                    </div>
                  </div>
                </div>

                {/* Suggestion chips */}
                <div className="try-row">
                  {cfg.chips.map((chip, i) => (
                    <div key={i} className="try-chip" onClick={() => setQuery(chip)}>{chip}</div>
                  ))}
                </div>
              </div>

            ) : (
              /* Chat view */
              <div id="chatView" className="chat-view">
                {messages.map((msg, idx) => (
                  <div key={idx}>
                    {msg.role === 'user' ? (
                      <div className="msg-row-user">
                        <div className="msg-user">{msg.content}</div>
                      </div>
                    ) : (
                      <>
                        {/* Stage spinner */}
                        {msg.content === '' && stage && (
                          <div className="stage-line">
                            <span className="stage-dot" />
                            <span className="stage-text">{stage}</span>
                          </div>
                        )}

                        {/* Top-10 source cards */}
                        {msg.results && msg.results.length > 0 && (
                          <>
                            <div className="sources-header">
                              📄 Research Sources
                              <span className="sources-count">{msg.results.length} found</span>
                            </div>
                            <div className="sources-grid">
                              {msg.results.map((r, i) => (
                                <div key={i} className="source-card">
                                  <span className="src-badge">[{r.index}] {r.source}</span>
                                  <div className="src-title">
                                    {r.url
                                      ? <a href={r.url} target="_blank" rel="noopener noreferrer">{r.title || r.url}</a>
                                      : (r.title || 'Untitled')
                                    }
                                  </div>
                                  {r.snippet && <div className="src-snippet">{r.snippet.slice(0, 160)}…</div>}
                                  {r.url && <div className="src-url">{domainOf(r.url)}</div>}
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {/* AI synthesis */}
                        {msg.content && (
                          <div className="msg-assistant" style={{ marginTop: msg.results?.length ? '18px' : 0 }}>
                            <ReactMarkdown rehypePlugins={[rehypeRaw]}>
                              {msg.content.replace(/\[(\d+)\](?!\()/g, '<span class="cite-chip">[$1]</span>')}
                            </ReactMarkdown>
                          </div>
                        )}

                        {/* Download button */}
                        {msg.sessionId && msg.content && (
                          <button
                            id={`downloadBtn-${idx}`}
                            className="download-btn"
                            onClick={() => handleDownload(msg.sessionId)}
                          >
                            ⬇ Download Synthesis Paper
                          </button>
                        )}
                      </>
                    )}
                  </div>
                ))}

                {/* Stage during streaming */}
                {stage && isLoading && messages[messages.length - 1]?.content !== '' && (
                  <div className="stage-line">
                    <span className="stage-dot" /><span>{stage}</span>
                  </div>
                )}

                <div ref={chatEndRef} />
              </div>
            )}

            {/* Docked composer when chatting */}
            {chatStarted && (
              <div className="chat-composer-dock" id="dockedComposer">
                <div className="composer">
                  <textarea
                    id="queryInputDocked"
                    placeholder="Ask a follow-up question"
                    rows="1"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKey}
                  />
                  <div className="composer-toolbar">
                    <div className="toolbar-left">
                      <button
                        className={`toolbar-btn ${sources.includes('papers') ? 'selected' : ''}`}
                        onClick={() => toggleSource('papers')}
                      >
                        📄 Papers {sources.includes('papers') ? '✓' : ''}
                      </button>
                      <button
                        className={`toolbar-btn ${sources.includes('web') ? 'selected' : ''}`}
                        onClick={() => toggleSource('web')}
                      >
                        🌐 Internet {sources.includes('web') ? '✓' : ''}
                      </button>
                      <button className="toolbar-btn" onClick={() => setIsFilterOpen(true)}>⚙ Filters</button>
                    </div>
                    <div className="toolbar-right">
                      <button
                        id="dockedSendBtn"
                        className="send-btn"
                        onClick={() => submitQuery(query)}
                        disabled={isLoading || !query.trim()}
                      >↑</button>
                    </div>
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      </main>

      <FilterPanel
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        sources={sources}
        toggleSource={toggleSource}
        onFiltersChange={setFilters}
      />
    </div>
  );
}
