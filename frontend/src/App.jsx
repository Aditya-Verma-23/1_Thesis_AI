import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';
import ReactQuill, { Quill } from 'react-quill';
import ImageResize from 'quill-image-resize-module-react';
import { CustomResize } from './CustomResize';
import 'react-quill/dist/quill.snow.css';

window.Quill = Quill;
Quill.register('modules/imageResize', ImageResize);
import { marked } from 'marked';
import TurndownService from 'turndown';
import FilterPanel from './components/FilterPanel';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import remarkGfm from 'remark-gfm';

// ── Shared thesis markdown renderers ─────────────────────────────────────────
const thesisComponents = {
  img: ({ src, alt }) => (
    <figure className="thesis-figure">
      <img src={src} alt={alt || 'Figure'} className="thesis-img" />
      {alt && <figcaption className="thesis-figcaption">{alt}</figcaption>}
    </figure>
  ),
  table: ({ children }) => (
    <div className="thesis-table-wrapper">
      <table className="thesis-table">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="thesis-th">{children}</th>,
  td: ({ children }) => <td className="thesis-td">{children}</td>,
  p: ({ children }) => <p className="thesis-p">{children}</p>,
  h1: ({ children }) => <h1 className="thesis-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="thesis-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="thesis-h3">{children}</h3>,
};

function ThesisMarkdown({ content }) {
  const processed = (content || '')
    .replace(/&nbsp;/g, ' ')
    .replace(/^[ \t]+(https?:\/\/)/gm, '$1')
    .replace(/\[(\d+)\](?!\()/g, '<span class="cite-chip">[$1]</span>');
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={thesisComponents}
      urlTransform={(url) => {
        if (url.startsWith('data:image/')) return url;
        return defaultUrlTransform(url);
      }}
    >
      {processed}
    </ReactMarkdown>
  );
}

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
  const [editingIndex, setEditingIndex] = useState(null);
  const [editDraft, setEditDraft] = useState('');
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
  const [topPanelHeight, setTopPanelHeight] = useState(50); // percentage of right panel height
  const isDragging = useRef(false);
  const isVDragging = useRef(false);
  const splitContainerRef = useRef(null);
  const rightPanelRef = useRef(null);
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
  const [isSourcesMenuOpen, setIsSourcesMenuOpen] = useState(false);
  const [insertMenuOpen, setInsertMenuOpen] = useState(false);
  const [sourcesEnabled, setSourcesEnabled] = useState(true);

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

  // ── Vertical resizer drag logic (Sources / Chat split in right panel) ──
  const handleVResizerMouseDown = useCallback((e) => {
    e.preventDefault();
    isVDragging.current = true;
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';

    const onMouseMove = (ev) => {
      if (!isVDragging.current || !rightPanelRef.current) return;
      const rect = rightPanelRef.current.getBoundingClientRect();
      let newTopPct = ((ev.clientY - rect.top) / rect.height) * 100;
      // Clamp: neither section less than 30%
      newTopPct = Math.max(30, Math.min(70, newTopPct));
      setTopPanelHeight(newTopPct);
    };

    const onMouseUp = () => {
      isVDragging.current = false;
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
      } catch { }
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

  // Close options menus on outside click
  useEffect(() => {
    const handleClick = (e) => {
      setOpenMenuKey(null);
      if (!e.target.closest('.sources-menu-container')) {
        setIsSourcesMenuOpen(false);
      }
    };
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, []);

  const handleScroll = () => {
    if (!contentRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
    // Show FAB only when user has scrolled up and there's hidden content below
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    setShowScrollDown(distanceFromBottom > 80);
  };

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (!showScrollDown && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, stage]);

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

  const handleEditSubmit = async (idx, newText) => {
    if (!newText.trim()) {
      setEditingIndex(null);
      return;
    }
    // Truncate messages up to the edited message
    const truncatedMessages = messages.slice(0, idx);
    setMessages(truncatedMessages);
    setEditingIndex(null);
    // Wait for state to settle, then submit
    setTimeout(() => submitQuery(newText), 50);
  };

  const submitQuery = useCallback(async (text) => {
    const q = text.trim();
    if (!q || isLoading) return;

    // Detect if this is a follow-up within an existing session
    const currentThesis = getLatestThesis();
    const isFollowUp = chatStarted && activeChat && !!currentThesis;
    const currentChatKey = isFollowUp ? activeChat : q;
    // Grab the plain thesis text to send as context
    const thesisContext = isFollowUp && currentThesis ? currentThesis.content : null;

    setChatStarted(true);
    setIsLoading(true);
    setQuery('');
    setStage('Connecting to backend…');

    setMessages(prev => [
      ...prev,
      { role: 'user', content: q },
      { role: 'assistant', content: '', results: [], sessionId: null },
    ]);

    if (!isFollowUp) {
      setActiveChat(q);
      const newRecents = [
        { text: q, time: timeStr(), messages: [] },
        ...recentQueries.filter(r => r.text !== q)
      ];
      setRecentQueries(newRecents);
      localStorage.setItem('thesisai_recent', JSON.stringify(newRecents));
    }

    const persistMessages = (finalMessages) => {
      setRecentQueries(prev => {
        const updated = prev.map(r => r.text === currentChatKey ? { ...r, messages: finalMessages } : r);
        localStorage.setItem('thesisai_recent', JSON.stringify(updated));
        return updated;
      });
    };

    try {
      // Use direct /api/chat endpoint for follow-ups, /api/query for initial thesis
      const endpoint = isFollowUp ? '/api/chat' : '/api/query';
      const res = await fetch(`${BACKEND_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q,
          filters: filters,
          sources: (isFollowUp && !sourcesEnabled) ? [] : sources,
          is_followup: isFollowUp,
          thesis_context: thesisContext,
          original_query: isFollowUp ? activeChat : null,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      if (isFollowUp) {
        // Direct response (non-streaming) for follow-ups
        const data = await res.json();
        const updateLast = (fn) =>
          setMessages(prev => {
            const next = [...prev];
            next[next.length - 1] = { ...next[next.length - 1], ...fn(next[next.length - 1]) };
            return next;
          });

        updateLast(p => ({
          ...p,
          content: data.answer || '',
          results: data.results || [],
          sessionId: null  // Don't overwrite thesis session
        }));
        setStage('');
        setIsLoading(false);
        setMessages(prev => { persistMessages(prev); return prev; });
      } else {
        // Streaming response for initial thesis generation
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
                setMessages(prev => { persistMessages(prev); return prev; });
              }
              else if (data.type === 'error') { setStage(`Error: ${data.message}`); setIsLoading(false); }
            } catch { /* skip */ }
          }
        }
      }
    } catch (err) {
      setStage(`Connection failed: ${err.message}`);
      setIsLoading(false);
    }
  }, [isLoading, recentQueries, messages, chatStarted, activeChat, filters, sources, sourcesEnabled]);

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
          return (
            <div className="split-container" ref={splitContainerRef}>

              {/* ─── LEFT PANEL: Thesis Document ─── */}
              <div className="thesis-doc-panel" style={{ flex: `0 0 ${leftPanelWidth}%`, width: `${leftPanelWidth}%` }}>

                {/* Custom Quill Toolbar (Primary) */}
                {thesisEditMode && (
                  <div id="custom-toolbar" className="doc-toolbar-primary">
                    <select className="ql-header" defaultValue="">
                      <option value="1">Heading 1</option>
                      <option value="2">Heading 2</option>
                      <option value="3">Heading 3</option>
                      <option value="">Normal Text</option>
                    </select>
                    <span className="ql-divider"></span>
                    <button className="ql-bold"></button>
                    <button className="ql-italic"></button>
                    <button className="ql-underline"></button>
                    <button className="ql-code-block"></button>
                    <span className="ql-divider"></span>
                    <select className="ql-align"></select>
                    <span className="ql-divider"></span>
                    <button className="ql-list" value="ordered"></button>
                    <button className="ql-list" value="bullet"></button>
                    <span className="ql-divider"></span>
                    <button className="ql-link"></button>
                    <button className="ql-image"></button>

                    {/* Custom + Dropdown Menu */}
                    <div className="insert-dropdown-container"
                      onMouseEnter={() => setInsertMenuOpen(true)}
                      onMouseLeave={() => setInsertMenuOpen(false)}>
                      <button className="insert-plus-btn">+</button>
                      {insertMenuOpen && (
                        <div className="insert-dropdown-menu">
                          <button className="ql-list" value="bullet">Bullet List</button>
                          <button className="ql-list" value="ordered">Numbered List</button>
                          <button className="ql-image">Insert Image</button>
                          <button className="ql-link">Insert Link</button>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Secondary Action Bar */}
                <div className="doc-toolbar-secondary">
                  <div className="action-bar-left">
                    {thesisEditMode && (
                      <select className="style-select-dropdown">
                        <option>Style: IEEE</option>
                        <option>Style: APA</option>
                        <option>Style: MLA</option>
                      </select>
                    )}
                    <button className="action-btn-styled" onClick={() => handleCopyThesis(thesis.content)}>
                      <span className="icon-copy">📄</span> Copy
                    </button>
                    <button className="action-btn-styled">
                      <span className="icon-share">↗️</span> Share
                    </button>
                    {thesisEditMode && (
                      <button className="action-btn-styled">
                        <span className="icon-reformat">🔄</span> Reformat
                      </button>
                    )}
                    <button className="action-btn-styled" onClick={() => handleDownload(thesis.content, thesis.sessionId)}>
                      <span className="icon-export">⬇️</span> Export
                    </button>
                  </div>

                  <div className="action-bar-right">
                    {thesisEditMode ? (
                      <>
                        <button className="doc-action-btn primary" onClick={() => {
                          const turndownService = new TurndownService({ headingStyle: 'atx' });
                          turndownService.addRule('keep-img', {
                            filter: 'img',
                            replacement: (content, node) => node.outerHTML
                          });
                          let markdownContent = turndownService.turndown(thesisEditContent);

                          // Fix escaped citations: \[1\] -> [1]
                          markdownContent = markdownContent.replace(/\\\[(\d+)\\\]/g, '[$1]');

                          setMessages(prev => {
                            const next = [...prev];
                            for (let i = next.length - 1; i >= 0; i--) {
                              if (next[i].role === 'assistant' && next[i].sessionId) {
                                next[i] = { ...next[i], content: markdownContent };
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
                      <button className="doc-action-btn" title="Click Edit, then click anywhere in the document to edit" onClick={() => {
                        const htmlContent = marked.parse(thesis.content);
                        setThesisEditContent(htmlContent);
                        setThesisEditMode(true);
                      }}>✏️ Edit</button>
                    )}
                  </div>
                </div>

                {/* Document Body */}
                <div className={`thesis-doc-body${thesisEditMode ? ' thesis-edit-active' : ''}`} ref={thesisRef}>
                  {thesisEditMode ? (
                    <ReactQuill
                      theme="snow"
                      value={thesisEditContent}
                      onChange={setThesisEditContent}
                      modules={{
                        toolbar: { container: '#custom-toolbar' },
                        imageResize: {
                          parchment: Quill.import('parchment'),
                          modules: [CustomResize, 'DisplaySize']
                        }
                      }}
                      style={{ height: '100%', minHeight: '500px' }}
                    />
                  ) : (
                    <div className="thesis-doc-content">
                      <ThesisMarkdown content={thesis.content} />
                    </div>
                  )}
                </div>
              </div>

              {/* ─── RESIZER ─── */}
              <div
                className="panel-resizer"
                onMouseDown={handleResizerMouseDown}
                title="Drag to resize panels"
              >
                <div className="panel-resizer-handle">
                  <span /><span /><span /><span /><span />
                </div>
              </div>

              {/* ─── RIGHT PANEL: Sources + Chat ─── */}
              <div className="sources-chat-panel" style={{ flex: '1 1 0%', minWidth: 0 }} ref={rightPanelRef}>

                {/* Sources section */}
                {thesis.results && thesis.results.length > 0 && (
                  <div className="right-sources-section" style={{ flex: `0 0 ${topPanelHeight}%`, height: `${topPanelHeight}%`, overflow: 'hidden' }}>
                    <div className="sources-header">
                      📄 Research Sources
                      <span className="sources-count">{thesis.results.length} found</span>
                    </div>
                    <div className="right-sources-list">
                      {thesis.results.map((r, i) => (
                        <div key={i} className="source-card source-card-compact">
                          <div className="src-header-row">
                            <span className="src-badge">[{r.index}] {r.url ? domainOf(r.url).toUpperCase() : r.source}</span>
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

                {/* ─── VERTICAL RESIZER (only when sources visible) ─── */}
                {thesis.results && thesis.results.length > 0 && (
                  <div
                    className="v-panel-resizer"
                    onMouseDown={handleVResizerMouseDown}
                    title="Drag to resize"
                  >
                    <div className="v-panel-resizer-handle">
                      <span /><span /><span /><span /><span />
                    </div>
                  </div>
                )}

                {/* Chat section: messages + always-visible composer */}
                <div className="right-chat-section" style={{ flex: '1 1 0%', minHeight: 0 }}>

                  {/* Follow-up chat messages */}
                  <div className="right-chat-messages" ref={contentRef} onScroll={handleScroll}>
                    {messages.map((msg, idx) => {
                      // The generated thesis itself is shown in the left panel, but we leave a placeholder here so the chat doesn't look broken
                      if (msg.role === 'assistant' && msg.sessionId) {
                        return (
                          <div key={idx} className="right-assistant-msg" style={{ fontStyle: 'italic', color: 'var(--ink-soft)' }}>
                            ✨ I've generated a comprehensive research document based on your query. You can view, edit, and download it in the left panel. Feel free to ask any follow-up questions below!
                          </div>
                        );
                      }

                      return (
                        <div key={idx}>
                          {msg.role === 'user' && (
                            <div className="right-user-msg-container" style={{ position: 'relative' }}>
                              {editingIndex === idx ? (
                                <div className="edit-message-box">
                                  <textarea
                                    className="edit-message-textarea"
                                    value={editDraft}
                                    onChange={(e) => setEditDraft(e.target.value)}
                                    autoFocus
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleEditSubmit(idx, editDraft);
                                      } else if (e.key === 'Escape') {
                                        setEditingIndex(null);
                                      }
                                    }}
                                  />
                                  <div className="edit-message-actions">
                                    <button className="edit-btn cancel" onClick={() => setEditingIndex(null)}>Cancel</button>
                                    <button className="edit-btn save" onClick={() => handleEditSubmit(idx, editDraft)}>Save & Submit</button>
                                  </div>
                                </div>
                              ) : (
                                <div className="right-user-msg msg-wrapper">
                                  <button
                                    className="msg-edit-btn"
                                    title="Edit query"
                                    onClick={() => {
                                      setEditingIndex(idx);
                                      setEditDraft(msg.content);
                                    }}
                                  >
                                    ✏️
                                  </button>
                                  {msg.content}
                                </div>
                              )}
                            </div>
                          )}
                          {msg.role === 'assistant' && msg.content && (
                            <div className="right-assistant-msg">
                              <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{msg.content}</ReactMarkdown>
                            </div>
                          )}
                        </div>
                      );
                    })}
                    {stage && isLoading && (
                      <div className="stage-line">
                        <span className="stage-dot" /><span>{stage}</span>
                      </div>
                    )}
                    <div ref={chatEndRef} />
                  </div>

                  {/* Scroll-to-bottom FAB — only when content is hidden below */}
                  {showScrollDown && (
                    <button
                      className="chat-scroll-fab"
                      onClick={() => {
                        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
                        setShowScrollDown(false);
                      }}
                      title="Scroll to bottom"
                    >↓</button>
                  )}

                  {/* Docked follow-up composer — always visible */}
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
                      <div className="toolbar-left" style={{ gap: '12px' }}>
                        <div className="sources-menu-container" style={{ position: 'relative' }}>
                          {/* The toggle and Sources button */}
                          <div
                            className="sources-toggle-btn"
                            onClick={() => setIsSourcesMenuOpen(!isSourcesMenuOpen)}
                          >
                            <div
                              className={`toggle-switch ${sourcesEnabled ? 'on' : 'off'}`}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSourcesEnabled(!sourcesEnabled);
                              }}
                            >
                              <div className="toggle-thumb" />
                            </div>
                            <span className="sources-label">Sources</span>
                            <span className="sources-chevron">{isSourcesMenuOpen ? '⌄' : '⌃'}</span>
                          </div>

                          {/* The Popover Menu */}
                          {isSourcesMenuOpen && (
                            <div className="sources-popover-menu">
                              <div
                                className="popover-item"
                                onClick={() => toggleSource('papers')}
                              >
                                📑 Papers {sources.includes('papers') && <span className="check">✓</span>}
                              </div>
                              <div
                                className="popover-item"
                                onClick={() => toggleSource('web')}
                              >
                                🌐 Internet {sources.includes('web') && <span className="check">✓</span>}
                              </div>
                              <div className="popover-item">
                                📁 Library
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Additional tool buttons */}
                        <button className="icon-btn" title="Attach file">📎</button>
                        <button className="icon-btn" title="Filters" onClick={() => setIsFilterOpen(true)}>⚙</button>
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

                            {msg.results && msg.results.length > 0 && (
                              <>
                                <div className="sources-header">📄 Research Sources <span className="sources-count">{msg.results.length} found</span></div>
                                <div className="sources-grid">
                                  {msg.results.map((r, i) => (
                                    <div key={i} className="source-card">
                                      <span className="src-badge">[{r.index}] {r.url ? domainOf(r.url).toUpperCase() : r.source}</span>
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
                                <ThesisMarkdown content={msg.content} />
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
