import React, { useState, useEffect } from 'react';

const QUALITY_STEPS = ['Q1', 'Q2', 'Q3', 'Q4', 'All'];

function FilterPanel({ isOpen, onClose, sources, toggleSource, onFiltersChange }) {
  const [expanded, setExpanded] = useState({
    citations: true, quality: true, pubTypes: true, database: true, dates: true
  });
  const toggle = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }));

  const [minCitations, setMinCitations] = useState(0);
  const [journalQuality, setJournalQuality] = useState(4);

  const [pubTypes, setPubTypes] = useState({
    journal: true, review: true, conference: true, preprint: false, books: false
  });

  const [dbPapers, setDbPapers] = useState({
    semanticScholar: true, openAlex: true, pubmed: false, arxiv: false, clinicalTrials: false
  });

  const [dbWeb, setDbWeb] = useState({ all: true, gov: false, edu: false });
  const [dbMain, setDbMain] = useState({ patents: false, medicare: false, myLibrary: false });
  const [dates, setDates] = useState({ start: '', end: '' });

  const handleWebFilter = (which) => {
    if (which === 'all') setDbWeb({ all: true, gov: false, edu: false });
    else setDbWeb(prev => ({ ...prev, [which]: !prev[which], all: false }));
  };

  useEffect(() => {
    if (onFiltersChange) {
      onFiltersChange({
        minCitations,
        journalQuality,
        pubTypes,
        dbPapers,
        dbWeb,
        dbMain,
        dates
      });
    }
  }, [minCitations, journalQuality, pubTypes, dbPapers, dbWeb, dbMain, dates, onFiltersChange]);

  const qualPct = (journalQuality / (QUALITY_STEPS.length - 1)) * 100;
  const isPapersOn = sources.includes('papers');
  const isWebOn    = sources.includes('web');

  return (
    <>
      <div className={`filter-overlay ${isOpen ? 'open' : ''}`} onClick={onClose} />
      <div className={`filter-panel ${isOpen ? 'open' : ''}`}>

        <div className="filter-head">
          <div className="filter-head-row">
            <div className="filter-title">Research Paper Filter</div>
            <button className="filter-close" onClick={onClose} aria-label="Close">✕</button>
          </div>
        </div>

        <div className="filter-body">

          {/* Minimum Citations */}
          <div className="fp-section">
            <button className="fp-trigger" aria-expanded={expanded.citations} onClick={() => toggle('citations')}>
              Minimum Citations <span className="fp-chevron">▲</span>
            </button>
            <div className={`fp-content ${!expanded.citations ? 'collapsed' : ''}`}>
              <div className="fp-slider-wrap">
                <div className="fp-slider-header">
                  <span className="fp-slider-label">Current value:</span>
                  <span className="fp-slider-val">{minCitations}</span>
                </div>
                <input
                  type="range" className="fp-range" min="0" max="20" value={minCitations}
                  onChange={e => setMinCitations(Number(e.target.value))}
                  style={{ background: `linear-gradient(to right, var(--maroon) 0%, var(--maroon) ${(minCitations/20)*100}%, #e8dde0 ${(minCitations/20)*100}%, #e8dde0 100%)` }}
                />
                <div className="fp-range-bounds"><span>0</span><span>20</span></div>
              </div>
            </div>
          </div>

          {/* Journal Quality */}
          <div className="fp-section">
            <button className="fp-trigger" aria-expanded={expanded.quality} onClick={() => toggle('quality')}>
              Journal quality <span style={{fontSize:'11px',color:'var(--ink-faint)',fontWeight:400,marginLeft:'4px'}}>ⓘ</span>
              <span className="fp-chevron">▲</span>
            </button>
            <div className={`fp-content ${!expanded.quality ? 'collapsed' : ''}`}>
              <div className="fp-quality-wrap">
                <div className="fp-quality-track" onClick={e => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                  setJournalQuality(Math.round(pct * (QUALITY_STEPS.length - 1)));
                }}>
                  <div className="fp-quality-fill" style={{ width: `${qualPct}%` }} />
                  <div className="fp-quality-thumb" style={{ left: `${qualPct}%` }} />
                </div>
                <div className="fp-quality-labels">
                  {QUALITY_STEPS.map((l, i) => (
                    <span key={i} onClick={() => setJournalQuality(i)} style={{ cursor: 'pointer' }}>{l}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Publication Types */}
          <div className="fp-section">
            <button className="fp-trigger" aria-expanded={expanded.pubTypes} onClick={() => toggle('pubTypes')}>
              Publication Types <span className="fp-chevron">▲</span>
            </button>
            <div className={`fp-content ${!expanded.pubTypes ? 'collapsed' : ''}`}>
              <p className="fp-hint">Select the types of publications to include in your search</p>
              <div className="fp-checkbox-list">
                {[['journal','Journal Articles'],['review','Review Articles'],['conference','Conference Papers'],['preprint','Preprints'],['books','Books & Chapters']].map(([k, label]) => (
                  <label key={k} className="fp-cb-label">
                    <input type="checkbox" checked={pubTypes[k]} onChange={e => setPubTypes(p => ({...p,[k]:e.target.checked}))} />
                    <span className="fp-custom-cb" />{label}
                  </label>
                ))}
              </div>
            </div>
          </div>

          {/* Database */}
          <div className="fp-section">
            <button className="fp-trigger" aria-expanded={expanded.database} onClick={() => toggle('database')}>
              Database <span className="fp-chevron">▲</span>
            </button>
            <div className={`fp-content ${!expanded.database ? 'collapsed' : ''}`}>
              <div className="fp-hint-tag">Select internet as well for more sources</div>

              {/* Research papers toggle */}
              <div className="fp-toggle-row">
                <span className="fp-db-header-label">Research papers</span>
                <label className="fp-toggle-switch">
                  <input type="checkbox" checked={isPapersOn} onChange={() => toggleSource('papers')} />
                  <span className="fp-toggle-track"><span className="fp-toggle-thumb" /></span>
                </label>
              </div>
              {isPapersOn && (
                <div className="fp-internet-filter visible">
                  <div className="fp-checkbox-list">
                    {[['semanticScholar','📚 Semantic Scholar'],['openAlex','🔬 OpenAlex'],['pubmed','🧬 PubMed'],['arxiv','📄 arXiv'],['clinicalTrials','🏥 ClinicalTrials.gov']].map(([k,label]) => (
                      <label key={k} className="fp-cb-label">
                        <input type="checkbox" checked={dbPapers[k]} onChange={e => setDbPapers(p => ({...p,[k]:e.target.checked}))} />
                        <span className="fp-custom-cb" />{label}
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Web searches toggle */}
              <div className="fp-toggle-list">
                <div className="fp-toggle-row">
                  <span className="fp-toggle-label">Web Searches</span>
                  <label className="fp-toggle-switch">
                    <input type="checkbox" checked={isWebOn} onChange={() => toggleSource('web')} />
                    <span className="fp-toggle-track"><span className="fp-toggle-thumb" /></span>
                  </label>
                </div>
                {isWebOn && (
                  <div className="fp-internet-filter visible">
                    <div className="fp-internet-filter-label">Internet Filter:</div>
                    <div className="fp-checkbox-list" style={{ padding: '10px 12px', background: '#f5f5f5', borderRadius: '8px' }}>
                      {[['all','🌐 All websites'],['gov','🏛 .gov (Government)'],['edu','🎓 .edu (Education)']].map(([k,label]) => (
                        <label key={k} className="fp-cb-label">
                          <input type="checkbox" checked={dbWeb[k]} onChange={() => handleWebFilter(k)} />
                          <span className="fp-custom-cb" />{label}
                        </label>
                      ))}
                    </div>
                  </div>
                )}
                {[['patents','Patents'],['medicare','Medicare Coverage'],['myLibrary','My Library']].map(([k,label]) => (
                  <div key={k} className="fp-toggle-row">
                    <span className="fp-toggle-label">{label}</span>
                    <label className="fp-toggle-switch">
                      <input type="checkbox" checked={dbMain[k]} onChange={e => setDbMain(p => ({...p,[k]:e.target.checked}))} />
                      <span className="fp-toggle-track"><span className="fp-toggle-thumb" /></span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Publication Date */}
          <div className="fp-section">
            <button className="fp-trigger" aria-expanded={expanded.dates} onClick={() => toggle('dates')}>
              Publication Date <span className="fp-chevron">▲</span>
            </button>
            <div className={`fp-content ${!expanded.dates ? 'collapsed' : ''}`}>
              <div className="fp-date-group">
                <div className="fp-date-field">
                  <label>Start Date:</label>
                  <input type="date" className="fp-date-input" value={dates.start} onChange={e => setDates(p => ({...p, start: e.target.value}))} />
                </div>
                <div className="fp-date-field">
                  <label>End Date:</label>
                  <input type="date" className="fp-date-input" value={dates.end} onChange={e => setDates(p => ({...p, end: e.target.value}))} />
                </div>
              </div>
            </div>
          </div>

        </div>

        <div className="filter-foot">
          <button className="btn-primary" onClick={onClose} style={{ width: '100%', justifyContent: 'center' }}>Submit Search</button>
        </div>

      </div>
    </>
  );
}

export default FilterPanel;
