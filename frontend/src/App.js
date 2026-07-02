import React, { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { v4 as uuidv4 } from 'uuid';
import './App.css';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const DEPT_COLORS = { garment: '#6366f1', denim: '#0d9488', corporate: '#d97706' };
const DEPT_EMOJI  = { garment: '👕', denim: '👖', corporate: '🏢' };
const PTYPE_EMOJI = { hr: '👥', medical: '🏥', leave: '📅', security: '🔒' };

const WELCOME = `**Welcome to the Company Policy Assistant** 🏭

I can answer questions from **all departments** — Garment, Denim, and Corporate — across:

| 👥 HR Policies | 🏥 Medical Policies | 📅 Leave Policies | 🔒 Security Policies |
|---|---|---|---|
| Working hours, grades, performance | Coverage, reimbursement, contacts | Annual, sick, maternity, hajj | Access, CCTV, cyber, emergency |

**Just ask naturally** — no need to select a department first. For example:

- *"What is the reimbursement process?"*
- *"What are garment shift timings?"*
- *"How many days of maternity leave do I get in corporate?"*
- *"Who do I call for a medical emergency in denim?"*

What would you like to know?`;

function newSession() {
  return {
    id: uuidv4(),
    title: 'New Chat',
    createdAt: new Date(),
    messages: [{
      id: uuidv4(), role: 'assistant', content: WELCOME,
      sources: [], departments: [], policy_types: [], timestamp: new Date(),
    }],
  };
}

// ── Sub-components ──────────────────────────────────────────────────────────

function TypingDots() {
  return <div className="typing"><span/><span/><span/></div>;
}

function MetaBadges({ departments, policy_types, sources }) {
  if (!departments?.length && !policy_types?.length) return null;
  return (
    <div className="meta-badges">
      {departments?.map(d => (
        <span key={d} className="badge" style={{background: DEPT_COLORS[d?.toLowerCase()]+'22',
          border:`1px solid ${DEPT_COLORS[d?.toLowerCase()]+'55'}`, color: DEPT_COLORS[d?.toLowerCase()] || '#818cf8'}}>
          {DEPT_EMOJI[d?.toLowerCase()] || '🏭'} {d}
        </span>
      ))}
      {policy_types?.map(p => (
        <span key={p} className="badge badge-ptype">
          {PTYPE_EMOJI[p?.toLowerCase()] || '📄'} {p?.toUpperCase()}
        </span>
      ))}
      {sources?.map(s => (
        <span key={s} className="badge badge-src" title={s}>📎 {s}</span>
      ))}
    </div>
  );
}

function FeedbackBtns({ id, onFeedback }) {
  const [v, setV] = useState(null);
  return (
    <div className="feedback">
      {['👍','👎'].map((emoji, i) => {
        const val = i === 0 ? 'up' : 'down';
        return (
          <button key={val} className={`fb ${v === val ? 'fb-active' : ''}`}
            onClick={() => { setV(val); onFeedback(id, val); }}>
            {emoji}
          </button>
        );
      })}
    </div>
  );
}

function Msg({ msg, onFeedback }) {
  const bot = msg.role === 'assistant';
  return (
    <div className={`row ${bot ? 'row-bot' : 'row-user'}`}>
      <div className="avatar">{bot ? '🤖' : '👤'}</div>
      <div className={`bubble ${bot ? 'bubble-bot' : 'bubble-user'}`}>
        {bot
          ? <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown></div>
          : <p>{msg.content}</p>
        }
        {bot && (
          <>
            <MetaBadges departments={msg.departments} policy_types={msg.policy_types} sources={msg.sources}/>
            <FeedbackBtns id={msg.id} onFeedback={onFeedback}/>
          </>
        )}
        <span className="ts">
          {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : ''}
        </span>
      </div>
    </div>
  );
}

// ── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [sessions,    setSessions]    = useState([newSession()]);
  const [activeId,    setActiveId]    = useState(sessions[0].id);
  const [input,       setInput]       = useState('');
  const [loading,     setLoading]     = useState(false);
  const [streaming,   setStreaming]   = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const bottomRef = useRef(null);
  const inputRef  = useRef(null);
  const abortRef  = useRef(null);

  const active = sessions.find(s => s.id === activeId);

  useEffect(() => { bottomRef.current?.scrollIntoView({behavior:'smooth'}); },
    [active?.messages, streaming]);

  const updateActive = useCallback((updater) => {
    setSessions(prev => prev.map(s => s.id === activeId ? updater(s) : s));
  }, [activeId]);

  const addMsg = useCallback((msg) => {
    updateActive(s => ({...s, messages: [...s.messages, msg]}));
  }, [updateActive]);

  const newChat = useCallback(() => {
    const s = newSession();
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
    setStreaming('');
    setLoading(false);
    abortRef.current?.abort();
  }, []);

  const sendMessage = async (text) => {
    const msg = (text || input).trim();
    if (!msg || loading || !active) return;
    setInput('');

    const userMsg = {id:uuidv4(), role:'user', content:msg, timestamp:new Date()};

    // Auto-title from first user message
    const userCount = active.messages.filter(m => m.role==='user').length;
    if (userCount === 0) {
      const title = msg.length > 45 ? msg.slice(0,45)+'…' : msg;
      updateActive(s => ({...s, title}));
    }

    // Snapshot history BEFORE adding the new user message
    const history = active.messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-12)
      .map(m => ({role: m.role, content: m.content}));

    updateActive(s => ({...s, messages: [...s.messages, userMsg]}));

    setLoading(true);
    setStreaming('');
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`${API_BASE}/stream-chat`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({message: msg, history}),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let full = '', meta = null;

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const obj = JSON.parse(line.slice(6));
            if (obj.done) { meta = obj; }
            else if (obj.token) { full += obj.token; setStreaming(full); }
          } catch {}
        }
      }

      setStreaming('');
      addMsg({
        id: uuidv4(), role:'assistant', content: full,
        sources:      meta?.sources      || [],
        departments:  meta?.departments  || [],
        policy_types: meta?.policy_types || [],
        timestamp: new Date(),
      });
    } catch (err) {
      if (err.name !== 'AbortError') {
        setStreaming('');
        addMsg({
          id:uuidv4(), role:'assistant', timestamp:new Date(),
          content:'⚠️ Could not reach the server. Please make sure the backend is running on port 8000.',
          sources:[], departments:[], policy_types:[],
        });
      }
    } finally {
      setLoading(false);
      setStreaming('');
    }
  };

  const onKey = e => { if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } };
  const onFeedback = (id, v) => console.log('feedback', id, v);

  const QUICK = [
    {label:'👕 Garment policies',    q:'What are the main HR policies in the garment department?'},
    {label:'👖 Denim medical',       q:'What medical coverage does the denim department provide?'},
    {label:'📅 Leave entitlements',  q:'How many days of annual leave do employees get?'},
    {label:'🔒 Emergency contacts',  q:'What are the emergency security and medical contact numbers?'},
    {label:'💊 Reimbursement',       q:'What is the medical reimbursement process and required documents?'},
    {label:'🤰 Maternity leave',     q:'What is the maternity leave policy?'},
  ];

  return (
    <div className="layout">

      {/* ── Sidebar ── */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sb-head">
          <div className="logo">🏭 <span>PolicyBot</span></div>
          <button className="ico-btn" onClick={() => setSidebarOpen(false)}>✕</button>
        </div>

        <button className="new-btn" onClick={newChat}>＋ New Conversation</button>

        <nav className="sess-list">
          {sessions.map(s => (
            <div key={s.id} className={`sess-item ${s.id === activeId ? 'sess-active' : ''}`}
              onClick={() => { setActiveId(s.id); abortRef.current?.abort(); setStreaming(''); setLoading(false); }}>
              <span className="sess-icon">💬</span>
              <div className="sess-info">
                <div className="sess-title">{s.title}</div>
                <div className="sess-date">{new Date(s.createdAt).toLocaleDateString()}</div>
              </div>
              <button className="del-btn" onClick={e => {
                e.stopPropagation();
                const remaining = sessions.filter(x => x.id !== s.id);
                setSessions(remaining.length ? remaining : [newSession()]);
                if (activeId === s.id) setActiveId((remaining[0] || newSession()).id);
              }}>🗑</button>
            </div>
          ))}
        </nav>

        <div className="sb-foot">
          <div className="sb-dept-tags">
            {Object.entries(DEPT_EMOJI).map(([d,e]) => (
              <span key={d} className="dept-tag" style={{borderColor: DEPT_COLORS[d]+'88', color: DEPT_COLORS[d]}}>
                {e} {d.charAt(0).toUpperCase()+d.slice(1)}
              </span>
            ))}
          </div>
          <p className="sb-hint">Ask about any department — no selection needed</p>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">

        {/* Topbar */}
        <header className="topbar">
          {!sidebarOpen && (
            <button className="ico-btn" onClick={() => setSidebarOpen(true)}>☰</button>
          )}
          <div className="topbar-title">
            <span className="topbar-icon">🏭</span>
            <div>
              <div className="topbar-name">Company Policy Assistant</div>
              <div className="topbar-sub">Search across all departments &amp; policy types</div>
            </div>
          </div>
          <button className="outline-btn" onClick={newChat}>🆕 New Chat</button>
        </header>

        {/* Messages */}
        <div className="msgs-wrap">
          <div className="msgs-inner">
            {active?.messages.map(m => (
              <Msg key={m.id} msg={m} onFeedback={onFeedback}/>
            ))}

            {loading && streaming && (
              <div className="row row-bot">
                <div className="avatar">🤖</div>
                <div className="bubble bubble-bot">
                  <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{streaming}</ReactMarkdown></div>
                </div>
              </div>
            )}
            {loading && !streaming && (
              <div className="row row-bot">
                <div className="avatar">🤖</div>
                <div className="bubble bubble-bot"><TypingDots/></div>
              </div>
            )}
            <div ref={bottomRef}/>
          </div>
        </div>

        {/* Quick suggestions — show only on first message */}
        {active?.messages.filter(m=>m.role==='user').length === 0 && !loading && (
          <div className="quick-wrap">
            <p className="quick-label">Suggested questions:</p>
            <div className="quick-grid">
              {QUICK.map(q => (
                <button key={q.label} className="quick-card" onClick={() => sendMessage(q.q)}>
                  {q.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Action bar — after bot has replied */}
        {active?.messages.filter(m=>m.role==='assistant').length > 1 && !loading && (
          <div className="action-bar">
            {[
              {label:'📋 More details', q:'Can you give more details about that?'},
              {label:'📞 Contact info', q:'What are the contact numbers and emails for this?'},
              {label:'🔄 New question', fn: () => inputRef.current?.focus()},
              {label:'🆕 New chat',    fn: newChat},
            ].map(a => (
              <button key={a.label} className="action-btn"
                onClick={() => a.fn ? a.fn() : sendMessage(a.q)}>
                {a.label}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="input-wrap">
          <div className="input-box">
            <textarea ref={inputRef} className="input-ta"
              value={input} onChange={e => setInput(e.target.value)} onKeyDown={onKey}
              placeholder="Ask anything about company policies… e.g. 'What is the reimbursement process?'"
              rows={1} disabled={loading}/>
            <button className={`send-btn ${loading?'send-loading':''}`}
              onClick={() => sendMessage()} disabled={loading||!input.trim()}>
              {loading ? '⏳' : '➤'}
            </button>
          </div>
          <p className="input-hint">Enter to send &nbsp;·&nbsp; Shift+Enter for new line &nbsp;·&nbsp; Searches all departments automatically</p>
        </div>
      </main>
    </div>
  );
}
