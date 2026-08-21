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
  const [activeTab, setActiveTab] = useState('qa');
  const [chatStarted, setChatStarted] = useState(false);
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [stage, setStage] = useState('');
  const [sources, setSources] = useState(['papers', 'web']);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [filters, setFilters] = useState(null);
  const [isBackendReady, setIsBackendReady] = useState(false);
  const [backendStatusMsg, setBackendStatusMsg] = useState('Connecting to backend…');
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [editingMessageIdx, setEditingMessageIdx] = useState(null);
  const [editContent, setEditContent] = useState('');
  const [splitView, setSplitView] = useState(false);
  const [thesisEditMode, setThesisEditMode] = useState(false);
  const [thesisEditContent, setThesisEditContent] = useState('');
  const [leftPanelWidth, setLeftPanelWidth] = useState(60); // percentage
  const isDragging = useRef(false);
  const splitContainerRef = useRef(null);
  const thesisRef = useRef(null);
  const [recentQueries, setRecentQueries] = useState(() => {
    try { return JSON.parse(localStorage.getItem('thesisai_recent') || '[]'); }
    catch { return []; }
  });
  const [activeChat, setActiveChat] = useState(null); // text key of the currently open chat
  const [editingChatKey, setEditingChatKey] = useState(null);
  const [editingChatTitle, setEditingChatTitle] = useState('');
  const [openMenuKey, setOpenMenuKey] = useState(null);
  const [showScrollDown, setShowScrollDown] = useState(false);

  const chatEndRef = useRef(null);
  const contentRef = useRef(null);

  // ── Resizer drag logic ──────────────────────────────────────────
  const handleResizerMouseDown = useCallback((e) => {
    e.preventDefault();
    isDragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (ev) => {
      if (!isDragging.current || !splitContainerRef.current) return;
      const container = splitContainerRef.current;
      const containerRect = container.getBoundingClientRect();
      let newLeftPct = ((ev.clientX - containerRect.left) / containerRect.width) * 100;
      // Clamp: neither panel less than 30%
      newLeftPct = Math.max(30, Math.min(70, newLeftPct));
      setLeftPanelWidth(newLeftPct);
    };

    const onMouseUp = () => {
      isDragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, []);

  // Persist active chat on refresh
  useEffect(() => {
    const savedActive = localStorage.getItem('thesisai_active');
    if (savedActive) {
      try {
        const recents = JSON.parse(localStorage.getItem('thesisai_recent') || '[]');
        const entry = recents.find(r => r.text === savedActive);
        if (entry && entry.messages && entry.messages.length > 0) {
          setMessages(entry.messages);
          setChatStarted(true);
          setActiveChat(entry.text);
          setSplitView(true);
        }
      } catch {}
    }
  }, []);

  useEffect(() => {
    if (activeChat) {
      localStorage.setItem('thesisai_active', activeChat);
    } else {
      localStorage.removeItem('thesisai_active');
    }
  }, [activeChat]);

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

  // Close options menu on outside click
  useEffect(() => {
    const handleClick = () => setOpenMenuKey(null);
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, []);

  const handleScroll = () => {
    if (!contentRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    if (isAtBottom) {
      setShowScrollDown(false);
    } else {
      if (chatStarted && messages.length > 0) {
        setShowScrollDown(true);
      }
    }
  };

  // Auto-resize composer
  useEffect(() => {
    const resize = (id) => {
      const el = document.getElementById(id);
      if (el) {
        el.style.height = 'auto';
        el.style.height = `${el.scrollHeight}px`;
      }
    };
    resize('queryInput');
    resize('queryInputDocked');
  }, [query, chatStarted]);

  const toggleSource = (src) =>
    setSources(prev => prev.includes(src) ? prev.filter(s => s !== src) : [...prev, src]);

  const submitEditedQuery = (text, index) => {
    setMessages(prev => prev.slice(0, index));
    setEditingMessageIdx(null);
    setTimeout(() => submitQuery(text), 0);
  };

  const submitQuery = useCallback(async (text) => {
    const q = text.trim();
    if (!q || isLoading) return;

    setChatStarted(true);
    setIsLoading(true);
    setQuery('');
    setStage('Connecting to backend…');

    setMessages(prev => [
      ...prev,
      { role: 'user', content: q },
      { role: 'assistant', content: '', results: [], sessionId: null },
    ]);

    // Track this as the active chat
    setActiveChat(q);

    // Save to recents — messages will be updated once the query finishes
    const newRecents = [
      { text: q, time: timeStr(), messages: [] },
      ...recentQueries.filter(r => r.text !== q)
    ];
    setRecentQueries(newRecents);
    localStorage.setItem('thesisai_recent', JSON.stringify(newRecents));

    // Helper: persist final messages into the matching recent entry
    const persistMessages = (finalMessages) => {
      setRecentQueries(prev => {
        const updated = prev.map(r => r.text === q ? { ...r, messages: finalMessages } : r);
        localStorage.setItem('thesisai_recent', JSON.stringify(updated));
        return updated;
      });
    };

    try {
      const res = await fetch(`${BACKEND_URL}/api/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, filters: filters, sources: sources }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

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
            if (data.type === 'stage') { setStage(data.message); }
            else if (data.type === 'result') { updateLast(p => ({ ...p, results: data.results || [] })); setStage(''); }
            else if (data.type === 'token') { updateLast(p => ({ ...p, content: p.content + data.content })); }
            else if (data.type === 'done') {
              updateLast(p => ({ ...p, sessionId: data.session_id }));
              setStage('');
              setIsLoading(false);
              setSplitView(true);
              // Persist finished messages into history
              setMessages(prev => { persistMessages(prev); return prev; });
            }
            else if (data.type === 'error') { setStage(`Error: ${data.message}`); setIsLoading(false); }
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

  const handleDownload = (content, sessionId) => {
    const text = content || '';
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `ThesisAI_${sessionId || Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleCopyThesis = (content) => {
    navigator.clipboard.writeText(content || '');
  };

  const getLatestThesis = () => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant' && messages[i].sessionId && messages[i].content) {
        return messages[i];
      }
    }
    return null;
  };

  const resetChat = () => { setChatStarted(false); setMessages([]); setStage(''); setQuery(''); setActiveChat(null); setSplitView(false); setThesisEditMode(false); };

  const deleteChat = (e, q) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this chat?")) return;

    setRecentQueries(prev => {
      const updated = prev.filter(r => r.text !== q);
      localStorage.setItem('thesisai_recent', JSON.stringify(updated));
      return updated;
    });

    if (activeChat === q) {
      resetChat();
    }
  };

  const renameChat = (e, q) => {
    e.stopPropagation();
    const entry = recentQueries.find(r => r.text === q);
    if (!entry) return;
    setEditingChatKey(q);
    setEditingChatTitle(entry.title || entry.text);
  };

  const saveChatTitle = (q) => {
    if (editingChatTitle.trim()) {
      setRecentQueries(prev => {
        const updated = prev.map(r => r.text === q ? { ...r, title: editingChatTitle.trim() } : r);
        localStorage.setItem('thesisai_recent', JSON.stringify(updated));
        return updated;
      });
    }
    setEditingChatKey(null);
    setEditingChatTitle('');
  };

  const handleRenameKeyDown = (e, q) => {
    if (e.key === 'Enter') saveChatTitle(q);
    if (e.key === 'Escape') {
      setEditingChatKey(null);
      setEditingChatTitle('');
    }
  };

  const togglePinChat = (e, q) => {
    e.stopPropagation();
    setRecentQueries(prev => {
      const updated = prev.map(r => r.text === q ? { ...r, pinned: !r.pinned } : r);
      localStorage.setItem('thesisai_recent', JSON.stringify(updated));
      return updated;
    });
  };

  const loadChat = (recentEntry) => {
    // Always reset current chat first — never mix with existing messages
    setChatStarted(false);
    setMessages([]);
    setStage('');
    setQuery('');
    setEditingMessageIdx(null);

    if (recentEntry.messages && recentEntry.messages.length > 0) {
      // Restore cached chat instantly — no backend call needed
      setTimeout(() => {
        setMessages(recentEntry.messages);
        setChatStarted(true);
        setActiveChat(recentEntry.text);
        setSplitView(true);
      }, 0);
    } else {
      // No cache yet — submit as a fresh query (submitQuery sets activeChat itself)
      setTimeout(() => submitQuery(recentEntry.text), 0);
    }
  };

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

        {[...recentQueries.filter(r => r.pinned), ...recentQueries.filter(r => !r.pinned)]
          .filter(r => (r.title || r.text).toLowerCase().includes(sidebarSearch.toLowerCase()))
          .map((r, i) => (
            <div
              key={i}
              className={`recent-item${r.text === activeChat ? ' active' : ''}`}
              onClick={() => {
                if (editingChatKey !== r.text) loadChat(r);
              }}
            >
              <div className="recent-info">
                {editingChatKey === r.text ? (
                  <input
                    autoFocus
                    type="text"
                    className="rename-input"
                    value={editingChatTitle}
                    onChange={(e) => setEditingChatTitle(e.target.value)}
                    onBlur={() => saveChatTitle(r.text)}
                    onKeyDown={(e) => handleRenameKeyDown(e, r.text)}
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      width: '100%', fontSize: '13.5px', color: 'var(--ink)',
                      border: '1px solid var(--maroon)', borderRadius: '4px',
                      padding: '2px 4px', outline: 'none', background: '#fff'
                    }}
                  />
                ) : (
                  <div className="recent-text" title={r.title || r.text}>
                    {r.pinned && <span style={{ marginRight: 4 }}>📌</span>}
                    {r.title || r.text}
                  </div>
                )}
                <div className="recent-meta">{r.time}</div>
              </div>
              <div className="recent-actions" style={{ position: 'relative' }}>
                {editingChatKey !== r.text && (
                  <>
                    <button className="action-btn" onClick={(e) => togglePinChat(e, r.text)} title={r.pinned ? "Unpin" : "Pin"}>{r.pinned ? '📍' : '📌'}</button>
                    <button className="action-btn" onClick={(e) => { e.stopPropagation(); setOpenMenuKey(openMenuKey === r.text ? null : r.text); }} title="Options">⋮</button>

                    {openMenuKey === r.text && (
                      <div className="chat-options-menu" onClick={e => e.stopPropagation()}>
                        <div className="chat-option" onClick={(e) => { setOpenMenuKey(null); renameChat(e, r.text); }}>✏️ Rename</div>
                        <div className="chat-option delete" onClick={(e) => { setOpenMenuKey(null); deleteChat(e, r.text); }}>🗑️ Delete</div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ))}

        {recentQueries.length === 0 && (
          <div className="sidebar-empty">No queries yet</div>
        )}
      </aside>

      {/* Main */}
      <main className={`main${splitView ? ' split-active' : ''}`}>

        {/* ─── SPLIT VIEW: Thesis Left + Sources/Chat Right ─── */}
        {splitView && (() => {
          const thesis = getLatestThesis();
          if (!thesis) return null;
          const displayContent = thesisEditMode ? thesisEditContent : thesis.content;
          return (
            <div className="split-container" ref={splitContainerRef}>

              {/* ─── LEFT PANEL: Thesis Document ─── */}
              <div className="thesis-doc-panel" style={{ flex: `0 0 ${leftPanelWidth}%`, width: `${leftPanelWidth}%` }}>
                {/* Document Toolbar */}
                <div className="doc-toolbar">
                  <div className="doc-toolbar-left">
                    <select className="doc-style-select">
                      <option>Normal Text</option>
                      <option>Heading 1</option>
                      <option>Heading 2</option>
                      <option>Heading 3</option>
                    </select>
                    <div className="doc-format-btns">
                      <button className="doc-fmt-btn" title="Bold"><b>B</b></button>
                      <button className="doc-fmt-btn" title="Italic"><i>I</i></button>
                      <button className="doc-fmt-btn" title="Underline" style={{textDecoration:'underline'}}>U</button>
                      <button className="doc-fmt-btn" title="Code">&lt;&gt;</button>
                      <span className="doc-fmt-divider"/>
                      <button className="doc-fmt-btn" title="Link">🔗</button>
                    </div>
                  </div>
                  <div className="doc-toolbar-right">
                    {thesisEditMode ? (
                      <>
                        <span className="doc-edit-badge">Editing…</span>
                        <button className="doc-action-btn primary" onClick={() => {
                          const editableDiv = document.getElementById('thesis-editable');
                          const updatedContent = editableDiv ? editableDiv.innerText : thesisEditContent;
                          setMessages(prev => {
                            const next = [...prev];
                            for (let i = next.length - 1; i >= 0; i--) {
                              if (next[i].role === 'assistant' && next[i].sessionId) {
                                next[i] = { ...next[i], content: updatedContent };
                                break;
                              }
                            }
                            return next;
                          });
                          setThesisEditMode(false);
                        }}>✓ Done Editing</button>
                        <button className="doc-action-btn" onClick={() => setThesisEditMode(false)}>✕ Cancel</button>
                      </>
                    ) : (
                      <>
                        <button className="doc-action-btn" title="Click Edit, then click anywhere in the document to edit" onClick={() => {
                          setThesisEditContent(thesis.content);
                          setThesisEditMode(true);
                          setTimeout(() => {
                            const el = document.getElementById('thesis-editable');
                            if (el) { el.focus(); }
                          }, 50);
                        }}>✏️ Edit</button>
                        <button className="doc-action-btn" title="Copy thesis" onClick={() => handleCopyThesis(thesis.content)}>📋 Copy</button>
                        <button className="doc-action-btn primary" onClick={() => handleDownload(thesis.content, thesis.sessionId)}>⬇ Download</button>
                      </>
                    )}
                  </div>
                </div>


                {/* Document Body */}
                <div className={`thesis-doc-body${thesisEditMode ? ' thesis-edit-active' : ''}`} ref={thesisRef}>
                  <div
                    id="thesis-editable"
                    className={`thesis-doc-content${thesisEditMode ? ' thesis-doc-editable' : ''}`}
                    contentEditable={thesisEditMode}
                    suppressContentEditableWarning
                    spellCheck={thesisEditMode}
                    onInput={(e) => setThesisEditContent(e.currentTarget.innerText)}
                  >
                    <ReactMarkdown rehypePlugins={[rehypeRaw]}>
                      {thesis.content.replace(/\[(\d+)\](?!\()/g, '<span class="cite-chip">[$1]</span>')}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>

              {/* ─── RESIZER ─── */}
              <div
                className="panel-resizer"
                onMouseDown={handleResizerMouseDown}
                title="Drag to resize panels"
              >
                <div className="panel-resizer-handle">
                  <span/><span/><span/><span/><span/>
                </div>
              </div>

              {/* ─── RIGHT PANEL: Sources + Chat ─── */}
              <div className="sources-chat-panel" style={{ flex: `0 0 ${100 - leftPanelWidth}%`, width: `${100 - leftPanelWidth}%` }}>

                {/* Sources section */}
                {thesis.results && thesis.results.length > 0 && (
                  <div className="right-sources-section">
                    <div className="sources-header">
                      📄 Research Sources
                      <span className="sources-count">{thesis.results.length} found</span>
                    </div>
                    <div className="right-sources-list">
                      {thesis.results.map((r, i) => (
                        <div key={i} className="source-card source-card-compact">
                          <div className="src-header-row">
                            <span className="src-badge">[{r.index}] {r.source}</span>
                            {r.year && <span className="src-year">{r.year}</span>}
                          </div>
                          <div className="src-title">
                            {r.url
                              ? <a href={r.url} target="_blank" rel="noopener noreferrer">{r.title || r.url}</a>
                              : (r.title || 'Untitled')
                            }
                          </div>
                          {r.authors && <div className="src-authors">{r.authors}</div>}
                          {r.venue && <div className="src-venue">{r.venue}{r.citationCount != null ? ` • ${r.citationCount} citations` : ''}</div>}
                          {r.url && <div className="src-url">{domainOf(r.url)}</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Follow-up chat messages */}
                <div className="right-chat-messages" ref={contentRef} onScroll={handleScroll}>
                  {messages.filter(m => m.role === 'user' || (m.role === 'assistant' && !m.sessionId)).map((msg, idx) => (
                    <div key={idx}>
                      {msg.role === 'user' && (
                        <div className="right-user-msg">{msg.content}</div>
                      )}
                      {msg.role === 'assistant' && msg.content && !msg.sessionId && (
                        <div className="right-assistant-msg">
                          <ReactMarkdown rehypePlugins={[rehypeRaw]}>{msg.content}</ReactMarkdown>
                        </div>
                      )}
                    </div>
                  ))}
                  {stage && isLoading && (
                    <div className="stage-line">
                      <span className="stage-dot" /><span>{stage}</span>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* Docked follow-up composer */}
                <div className="right-composer">
                  <textarea
                    id="rightQueryInput"
                    className="right-composer-textarea"
                    placeholder="Ask a follow-up question or request an edit…"
                    rows="2"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKey}
                  />
                  <div className="right-composer-actions">
                    <div className="toolbar-left" style={{gap:'6px'}}>
                      <button className={`toolbar-btn ${sources.includes('papers') ? 'selected' : ''}`} onClick={() => toggleSource('papers')}>📄 Papers</button>
                      <button className={`toolbar-btn ${sources.includes('web') ? 'selected' : ''}`} onClick={() => toggleSource('web')}>🌐 Web</button>
                    </div>
                    <button
                      className="send-btn"
                      onClick={() => submitQuery(query)}
                      disabled={isLoading || !query.trim()}
                    >↑</button>
                  </div>
                </div>
              </div>
            </div>
          );
        })()}

        {/* ─── NORMAL VIEW (Home / Loading) ─── */}
        {!splitView && (
          <>
            <div className="topbar"><div className="avatar">AV</div></div>
            <div className="content" ref={contentRef} onScroll={handleScroll}>
              <div className="content-inner">
                {!chatStarted ? (
                  <div id="homeView">
                    <div className="watermark">THESIS</div>
                    <h1 className="greeting" id="greeting">Welcome back, Aditya</h1>
                    <p className="sub-greeting">{cfg.greeting}</p>

                    <div className="workflow-tabs" id="workflowTabs">
                      {Object.keys(TAB_CONFIG).map(key => (
                        <div key={key} className={`tab ${activeTab === key ? 'active' : ''}`} onClick={() => setActiveTab(key)}>
                          {key === 'qa' && '🎯 Quick Q/A'}
                          {key === 'lit' && '📚 Literature review'}
                          {key === 'sys' && '⚗ Systematic review'}
                          {key === 'data' && '📈 Data analysis'}
                          {key === 'gaps' && '🔍 Research gaps'}
                          {key === 'chat' && '💬 Paper chat'}
                        </div>
                      ))}
                    </div>

                    <div className="composer">
                      <textarea id="queryInput" placeholder={cfg.placeholder} rows="3" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={handleKey} />
                      <div className="composer-toolbar">
                        <div className="toolbar-left">
                          <button className={`toolbar-btn ${sources.includes('papers') ? 'selected' : ''}`} onClick={() => toggleSource('papers')}>📄 Papers {sources.includes('papers') ? '✓' : ''}</button>
                          <button className={`toolbar-btn ${sources.includes('web') ? 'selected' : ''}`} onClick={() => toggleSource('web')}>🌐 Internet {sources.includes('web') ? '✓' : ''}</button>
                          <button className="toolbar-btn" onClick={() => setIsFilterOpen(true)}>⚙ Filters</button>
                        </div>
                        <div className="toolbar-right">
                          <button id="sendBtn" className="send-btn" onClick={() => submitQuery(query)} disabled={isLoading || !query.trim()}>↑</button>
                        </div>
                      </div>
                    </div>

                    <div className="try-row">
                      {cfg.chips.map((chip, i) => (
                        <div key={i} className="try-chip" onClick={() => setQuery(chip)}>{chip}</div>
                      ))}
                    </div>
                  </div>

                ) : (
                  /* Loading / Streaming view */
                  <div id="chatView" className="chat-view">
                    {messages.map((msg, idx) => (
                      <div key={idx}>
                        {msg.role === 'user' ? (
                          <div className="msg-row-user">
                            <div className="msg-user-wrapper">
                              <div className="msg-user">{msg.content}</div>
                            </div>
                          </div>
                        ) : (
                          <>
                            {msg.content === '' && stage && (
                              <div className="stage-line">
                                <span className="stage-dot" />
                                <span className="stage-text">{stage}</span>
                              </div>
                            )}
                            {msg.results && msg.results.length > 0 && (
                              <>
                                <div className="sources-header">📄 Research Sources <span className="sources-count">{msg.results.length} found</span></div>
                                <div className="sources-grid">
                                  {msg.results.map((r, i) => (
                                    <div key={i} className="source-card">
                                      <span className="src-badge">[{r.index}] {r.source}</span>
                                      <div className="src-title">{r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer">{r.title || r.url}</a> : (r.title || 'Untitled')}</div>
                                      {r.snippet && <div className="src-snippet">{r.snippet.slice(0, 160)}…</div>}
                                      {r.url && <div className="src-url">{domainOf(r.url)}</div>}
                                    </div>
                                  ))}
                                </div>
                              </>
                            )}
                            {msg.content && (
                              <div className="msg-assistant">
                                <ReactMarkdown rehypePlugins={[rehypeRaw]}>
                                  {msg.content.replace(/\[(\d+)\](?!\()/g, '<span class="cite-chip">[$1]</span>')}
                                </ReactMarkdown>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                    {stage && isLoading && <div className="stage-line"><span className="stage-dot" /><span>{stage}</span></div>}
                    <div ref={chatEndRef} />
                  </div>
                )}

                {chatStarted && (
                  <div className="chat-composer-dock" id="dockedComposer">
                    <div className="composer">
                      <textarea id="queryInputDocked" placeholder="Ask a follow-up question" rows="1" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={handleKey} />
                      <div className="composer-toolbar">
                        <div className="toolbar-left">
                          <button className={`toolbar-btn ${sources.includes('papers') ? 'selected' : ''}`} onClick={() => toggleSource('papers')}>📄 Papers {sources.includes('papers') ? '✓' : ''}</button>
                          <button className={`toolbar-btn ${sources.includes('web') ? 'selected' : ''}`} onClick={() => toggleSource('web')}>🌐 Internet {sources.includes('web') ? '✓' : ''}</button>
                          <button className="toolbar-btn" onClick={() => setIsFilterOpen(true)}>⚙ Filters</button>
                        </div>
                        <div className="toolbar-right">
                          <button id="dockedSendBtn" className="send-btn" onClick={() => submitQuery(query)} disabled={isLoading || !query.trim()}>↑</button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}
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
