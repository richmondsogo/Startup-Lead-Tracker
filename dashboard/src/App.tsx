import React, { useState, useEffect, useMemo } from 'react';
import { 
  Briefcase, 
  GraduationCap, 
  Zap, 
  Search, 
  Calendar, 
  Building2, 
  ExternalLink, 
  Copy, 
  Check, 
  Mail, 
  Sparkles, 
  Table as TableIcon,
  LayoutGrid,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  RefreshCw,
  FileSpreadsheet,
  X
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

export interface Lead {
  score: number;
  score_breakdown: string;
  intent_type: string;
  posted_at: string;
  found_at: string;
  source: string;
  company_or_author: string;
  title_or_role: string;
  domain?: string;
  guessed_emails?: string;
  other_contact?: string;
  summary_snippet: string;
  tailored_pitch: string;
  quick_action: string;
  article_link: string;
}

const SENIOR_RE = /\b(senior|sr\.|staff|principal|lead engineer|lead developer|director|vp of|vice president|head of engineering|head of product|architect|5\+\s*years|7\+\s*years|10\+\s*years)\b/i;

export default function App() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  // Filters & State
  const [search, setSearch] = useState('');
  const [activeTab, setActiveTab] = useState<'all' | 'intern' | 'contract' | 'high' | 'contact'>('all');
  const [minScore, setMinScore] = useState(20);
  const [hideSenior, setHideSenior] = useState(false);
  const [sortBy, setSortBy] = useState<'score' | 'posted_date' | 'company'>('score');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [expandedPitches, setExpandedPitches] = useState<Record<number, boolean>>({});
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  useEffect(() => {
    fetchLeads();
  }, []);

  async function fetchLeads() {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch('/leads.json');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setLeads(data);
    } catch (err: any) {
      console.warn('Could not load /leads.json', err);
      setErrorMsg('Could not load /leads.json directly. Run tracker.py to refresh leads data.');
    } finally {
      setLoading(false);
    }
  }

  function handleCopyPitch(pitch: string, index: number, e?: React.MouseEvent) {
    if (e) e.stopPropagation();
    navigator.clipboard.writeText(pitch);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  }

  function toggleExpandPitch(index: number, e?: React.MouseEvent) {
    if (e) e.stopPropagation();
    setExpandedPitches(prev => ({ ...prev, [index]: !prev[index] }));
  }

  const filteredLeads = useMemo(() => {
    return leads.filter(lead => {
      // Score filter
      if (lead.score < minScore) return false;

      // Seniority filter
      if (hideSenior && SENIOR_RE.test(`${lead.title_or_role} ${lead.summary_snippet}`)) {
        return false;
      }

      // Tab filter
      if (activeTab === 'intern' && lead.intent_type !== 'internship') return false;
      if (activeTab === 'contract' && lead.intent_type !== 'contract_hiring') return false;
      if (activeTab === 'high' && lead.score < 70) return false;
      if (activeTab === 'contact' && !lead.domain && !lead.other_contact) return false;

      // Search
      if (search.trim()) {
        const query = search.toLowerCase();
        const hay = `${lead.company_or_author} ${lead.title_or_role} ${lead.summary_snippet} ${lead.source} ${lead.domain || ''}`.toLowerCase();
        if (!hay.includes(query)) return false;
      }

      return true;
    }).sort((a, b) => {
      if (sortBy === 'score') return b.score - a.score;
      if (sortBy === 'posted_date') {
        const da = a.posted_at || '';
        const db = b.posted_at || '';
        return db.localeCompare(da);
      }
      if (sortBy === 'company') {
        return (a.company_or_author || '').localeCompare(b.company_or_author || '');
      }
      return 0;
    });
  }, [leads, search, activeTab, minScore, hideSenior, sortBy]);

  // Statistics
  const stats = useMemo(() => {
    const total = leads.length;
    const highFit = leads.filter(l => l.score >= 70).length;
    const internships = leads.filter(l => l.intent_type === 'internship').length;
    const contracts = leads.filter(l => l.intent_type === 'contract_hiring').length;
    const contacts = leads.filter(l => l.domain || l.other_contact).length;
    return { total, highFit, internships, contracts, contacts };
  }, [leads]);

  function renderChips(breakdown: string) {
    if (!breakdown) return null;
    return breakdown.split('|').map((part, i) => {
      const isNeg = part.includes(':-') || part.includes('Senior:');
      const isBoost = part.includes('Junior') || part.includes('Intern');
      return (
        <span 
          key={i} 
          className={`text-[10px] px-1.5 py-0.5 rounded font-mono border ${
            isNeg 
              ? 'bg-rose-500/10 text-rose-300 border-rose-500/20' 
              : isBoost 
              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25 font-semibold'
              : 'bg-slate-800/80 text-slate-400 border-slate-700/50'
          }`}
        >
          {part}
        </span>
      );
    });
  }

  return (
    <div className="min-h-screen text-slate-100 flex flex-col">
      {/* Top Navigation */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-xl sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
                Startup Lead Tracker
                <span className="text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30 px-2 py-0.5 rounded-full font-mono">v3.0 PRO</span>
              </h1>
              <p className="text-xs text-slate-400">Active hiring intent scanner & 1-click outreach</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button 
              variant="outline" 
              size="sm" 
              onClick={fetchLeads} 
              className="gap-1.5 text-xs text-slate-300"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <a href="/leads.csv" download className="hidden sm:inline-flex">
              <Button variant="secondary" size="sm" className="gap-1.5 text-xs">
                <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-400" />
                Export CSV
              </Button>
            </a>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-6">
        {errorMsg && (
          <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-200 text-xs flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Metric Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 sm:gap-4">
          <Card className="p-4 border-slate-800/80 bg-slate-900/50 backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Total Leads</span>
              <Building2 className="h-4 w-4 text-slate-500" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-white mt-1">{stats.total}</div>
            <div className="text-[11px] text-slate-500 mt-1">Multi-source scraped</div>
          </Card>

          <Card className="p-4 border-slate-800/80 bg-slate-900/50 backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">High Fit (70+)</span>
              <Sparkles className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-emerald-400 mt-1">{stats.highFit}</div>
            <div className="text-[11px] text-slate-500 mt-1">High conversion potential</div>
          </Card>

          <Card className="p-4 border-slate-800/80 bg-slate-900/50 backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wider">Internships</span>
              <GraduationCap className="h-4 w-4 text-indigo-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-indigo-400 mt-1">{stats.internships}</div>
            <div className="text-[11px] text-slate-500 mt-1">SWE, Data & AI student roles</div>
          </Card>

          <Card className="p-4 border-slate-800/80 bg-slate-900/50 backdrop-blur-md">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">Contracts</span>
              <Briefcase className="h-4 w-4 text-blue-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-blue-400 mt-1">{stats.contracts}</div>
            <div className="text-[11px] text-slate-500 mt-1">Freelance, bounty & gigs</div>
          </Card>

          <Card className="p-4 border-slate-800/80 bg-slate-900/50 backdrop-blur-md col-span-2 md:col-span-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-purple-400 uppercase tracking-wider">With Contact</span>
              <Mail className="h-4 w-4 text-purple-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-purple-400 mt-1">{stats.contacts}</div>
            <div className="text-[11px] text-slate-500 mt-1">Email, GitHub or domain</div>
          </Card>
        </div>

        {/* Toolbar & Filter Bar */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-xl p-4 space-y-4 backdrop-blur-md shadow-xl">
          <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center justify-between">
            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                type="text"
                placeholder="Search company, skills (Python, Playwright, AI), title..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9 bg-slate-950/60 border-slate-700/80 focus:border-blue-500 text-sm h-10"
              />
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0">
              <Button
                variant={activeTab === 'all' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveTab('all')}
                className="text-xs font-semibold whitespace-nowrap"
              >
                All Leads ({stats.total})
              </Button>
              <Button
                variant={activeTab === 'intern' ? 'success' : 'ghost'}
                size="sm"
                onClick={() => setActiveTab('intern')}
                className="text-xs font-semibold whitespace-nowrap"
              >
                🎓 Internships ({stats.internships})
              </Button>
              <Button
                variant={activeTab === 'contract' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveTab('contract')}
                className="text-xs font-semibold whitespace-nowrap"
              >
                💼 Contracts ({stats.contracts})
              </Button>
              <Button
                variant={activeTab === 'high' ? 'amber' : 'ghost'}
                size="sm"
                onClick={() => setActiveTab('high')}
                className="text-xs font-semibold whitespace-nowrap"
              >
                ⭐ High Fit ({stats.highFit})
              </Button>
            </div>
          </div>

          {/* Sub-Filters: Score Slider, Senior Toggle, Sort, View Mode */}
          <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-slate-800/60 text-xs">
            <div className="flex flex-wrap items-center gap-5">
              {/* Min Score Slider */}
              <div className="flex items-center gap-2.5">
                <span className="text-slate-400 font-medium">Min Score:</span>
                <input
                  type="range"
                  min="0"
                  max="90"
                  step="5"
                  value={minScore}
                  onChange={e => setMinScore(Number(e.target.value))}
                  className="w-24 accent-blue-500 cursor-pointer"
                />
                <Badge variant={minScore >= 70 ? 'highScore' : minScore >= 40 ? 'midScore' : 'lowScore'} className="font-mono">
                  {minScore}+
                </Badge>
              </div>

              {/* Hide Senior Toggle */}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={hideSenior}
                  onChange={e => setHideSenior(e.target.checked)}
                  className="rounded border-slate-700 text-blue-600 focus:ring-blue-500 bg-slate-900"
                />
                <span className="text-slate-300 font-medium flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3 text-amber-400" />
                  Hide Senior Roles
                </span>
              </label>
            </div>

            <div className="flex items-center gap-3">
              {/* Sort By */}
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400">Sort:</span>
                <select
                  value={sortBy}
                  onChange={e => setSortBy(e.target.value as any)}
                  className="bg-slate-950/70 border border-slate-700/80 rounded-md px-2 py-1 text-slate-200 outline-none cursor-pointer"
                >
                  <option value="score">Score (High to Low)</option>
                  <option value="posted_date">Posted Date (Newest)</option>
                  <option value="company">Company (A-Z)</option>
                </select>
              </div>

              {/* View Toggle */}
              <div className="flex items-center bg-slate-950/80 rounded-md border border-slate-800 p-0.5">
                <button
                  onClick={() => setViewMode('grid')}
                  className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                  title="Grid View"
                >
                  <LayoutGrid className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setViewMode('table')}
                  className={`p-1.5 rounded ${viewMode === 'table' ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'}`}
                  title="Table View"
                >
                  <TableIcon className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Results Counter */}
        <div className="flex items-center justify-between text-xs text-slate-400 px-1">
          <span>
            Showing <strong className="text-white">{filteredLeads.length}</strong> of {leads.length} leads
          </span>
          {activeTab !== 'all' && (
            <button 
              onClick={() => { setActiveTab('all'); setSearch(''); setMinScore(20); setHideSenior(false); }}
              className="text-blue-400 hover:underline"
            >
              Reset Filters
            </button>
          )}
        </div>

        {/* Lead Grid / Table View */}
        {filteredLeads.length === 0 ? (
          <div className="bg-slate-900/50 border border-slate-800/80 rounded-2xl p-12 text-center space-y-3">
            <div className="h-12 w-12 rounded-full bg-slate-800/80 flex items-center justify-center mx-auto text-slate-400">
              <Search className="h-6 w-6" />
            </div>
            <h3 className="text-base font-semibold text-white">No leads match your active filters</h3>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Try adjusting the minimum score slider, resetting your search keyword, or clearing the filter tabs.
            </p>
            <Button variant="outline" size="sm" onClick={() => { setSearch(''); setMinScore(0); setHideSenior(false); setActiveTab('all'); }}>
              Clear All Filters
            </Button>
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredLeads.map((lead, idx) => {
              const isIntern = lead.intent_type === 'internship';
              const isSenior = SENIOR_RE.test(`${lead.title_or_role} ${lead.summary_snippet}`);
              const isExpanded = expandedPitches[idx] || false;

              return (
                <Card 
                  key={idx}
                  onClick={() => setSelectedLead(lead)}
                  className={`flex flex-col justify-between overflow-hidden transition-all duration-200 hover:translate-y-[-2px] hover:shadow-2xl cursor-pointer ${
                    isIntern 
                      ? 'border-emerald-500/30 hover:border-emerald-500/50' 
                      : isSenior 
                      ? 'border-slate-800 opacity-90' 
                      : 'border-slate-800 hover:border-blue-500/40'
                  }`}
                >
                  <CardHeader className="pb-2.5">
                    {/* Badge Row */}
                    <div className="flex flex-wrap items-center gap-1.5 mb-2">
                      <Badge variant={lead.score >= 70 ? 'highScore' : lead.score >= 50 ? 'midScore' : 'lowScore'}>
                        {lead.score} PTS
                      </Badge>
                      <Badge variant="outline" className="text-[11px] font-mono">
                        {lead.source}
                      </Badge>
                      {isIntern && (
                        <Badge variant="intern">🎓 INTERN</Badge>
                      )}
                      {isSenior && (
                        <Badge variant="senior">⚠️ SENIOR</Badge>
                      )}
                    </div>

                    {/* Score Breakdown Chips */}
                    <div className="flex flex-wrap gap-1 mb-2">
                      {renderChips(lead.score_breakdown)}
                    </div>

                    {/* Role Title & Company */}
                    <CardTitle className="text-base font-bold line-clamp-2 leading-snug">
                      {lead.title_or_role}
                    </CardTitle>
                    <div className="flex flex-wrap items-center gap-y-1 gap-x-3 text-xs text-slate-400 pt-1">
                      <span className="font-semibold text-slate-200 flex items-center gap-1">
                        <Building2 className="h-3 w-3 text-blue-400" />
                        {lead.company_or_author}
                      </span>
                      {lead.posted_at && (
                        <span className="flex items-center gap-1">
                          <Calendar className="h-3 w-3 text-slate-500" />
                          {lead.posted_at}
                        </span>
                      )}
                    </div>
                  </CardHeader>

                  <CardContent className="space-y-3 flex-1 flex flex-col justify-between pt-1">
                    {/* Snippet */}
                    <p className="text-xs text-slate-300/90 line-clamp-3 bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/60 leading-relaxed font-sans">
                      {lead.summary_snippet || 'No description snippet available.'}
                    </p>

                    {/* Pitch Hook Box */}
                    {lead.tailored_pitch && (
                      <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5 space-y-1.5 text-xs">
                        <div className="flex items-center justify-between text-slate-400 font-medium">
                          <span className="flex items-center gap-1 text-[11px] text-blue-400">
                            {isIntern ? '✉️ Student Cover Intro' : '🎯 Tailored Pitch Hook'}
                          </span>
                          <button
                            onClick={e => handleCopyPitch(lead.tailored_pitch, idx, e)}
                            className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-white bg-slate-800/60 hover:bg-slate-800 px-2 py-0.5 rounded transition-colors"
                          >
                            {copiedIndex === idx ? (
                              <>
                                <Check className="h-3 w-3 text-emerald-400" />
                                <span className="text-emerald-400 font-semibold">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                        <p className={`text-slate-300 italic text-[11px] leading-relaxed ${isExpanded ? '' : 'line-clamp-2'}`}>
                          &ldquo;{lead.tailored_pitch}&rdquo;
                        </p>
                        {lead.tailored_pitch.length > 120 && (
                          <button
                            onClick={e => toggleExpandPitch(idx, e)}
                            className="text-[10px] text-blue-400 hover:underline flex items-center gap-0.5 pt-0.5"
                          >
                            {isExpanded ? (
                              <>Show less <ChevronUp className="h-3 w-3" /></>
                            ) : (
                              <>Show full pitch <ChevronDown className="h-3 w-3" /></>
                            )}
                          </button>
                        )}
                      </div>
                    )}

                    {/* Card Actions */}
                    <div className="flex items-center gap-2 pt-2" onClick={e => e.stopPropagation()}>
                      <a 
                        href={lead.quick_action} 
                        target="_blank" 
                        rel="noreferrer" 
                        className="flex-1"
                      >
                        <Button
                          variant={isIntern ? 'success' : 'default'}
                          size="sm"
                          className="w-full text-xs font-semibold gap-1.5 shadow-md"
                        >
                          {isIntern ? (
                            <>
                              <GraduationCap className="h-3.5 w-3.5" />
                              Apply Now
                            </>
                          ) : (
                            <>
                              <Zap className="h-3.5 w-3.5" />
                              1-Click Outreach
                            </>
                          )}
                        </Button>
                      </a>
                      <a
                        href={lead.article_link}
                        target="_blank"
                        rel="noreferrer"
                        title="View original listing"
                      >
                        <Button variant="outline" size="sm" className="px-2.5">
                          <ExternalLink className="h-3.5 w-3.5 text-slate-400" />
                        </Button>
                      </a>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          /* Table View */
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl backdrop-blur-md">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/80 border-b border-slate-800 text-slate-400 uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-3 px-4">Score</th>
                    <th className="py-3 px-4">Role / Title</th>
                    <th className="py-3 px-4">Company</th>
                    <th className="py-3 px-4">Source</th>
                    <th className="py-3 px-4">Posted</th>
                    <th className="py-3 px-4">Contact</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredLeads.map((lead, idx) => (
                    <tr 
                      key={idx} 
                      onClick={() => setSelectedLead(lead)}
                      className="hover:bg-slate-800/40 transition-colors cursor-pointer"
                    >
                      <td className="py-3 px-4">
                        <Badge variant={lead.score >= 70 ? 'highScore' : lead.score >= 50 ? 'midScore' : 'lowScore'}>
                          {lead.score}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-100 max-w-xs truncate">
                        {lead.title_or_role}
                      </td>
                      <td className="py-3 px-4 text-slate-300 font-medium">
                        {lead.company_or_author}
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="text-[10px]">
                          {lead.source}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-slate-400 whitespace-nowrap">
                        {lead.posted_at || 'Recent'}
                      </td>
                      <td className="py-3 px-4 text-slate-400 max-w-[150px] truncate">
                        {lead.other_contact || lead.domain || '—'}
                      </td>
                      <td className="py-3 px-4 text-right whitespace-nowrap space-x-1.5" onClick={e => e.stopPropagation()}>
                        <a href={lead.quick_action} target="_blank" rel="noreferrer">
                          <Button size="sm" variant={lead.intent_type === 'internship' ? 'success' : 'default'} className="h-7 text-xs px-2.5">
                            {lead.intent_type === 'internship' ? 'Apply' : 'Reach Out'}
                          </Button>
                        </a>
                        <button
                          onClick={e => handleCopyPitch(lead.tailored_pitch, idx, e)}
                          className="h-7 px-2 border border-slate-700 bg-slate-800/60 rounded text-slate-300 hover:text-white"
                          title="Copy tailored pitch"
                        >
                          {copiedIndex === idx ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Modal / Dialog for Detailed Lead Inspection */}
      {selectedLead && (
        <div 
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setSelectedLead(null)}
        >
          <div 
            className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 animate-in fade-in zoom-in-95 duration-150"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant={selectedLead.score >= 70 ? 'highScore' : selectedLead.score >= 50 ? 'midScore' : 'lowScore'}>
                    {selectedLead.score} PTS
                  </Badge>
                  <Badge variant="outline">{selectedLead.source}</Badge>
                  {selectedLead.intent_type === 'internship' && <Badge variant="intern">🎓 INTERN</Badge>}
                </div>
                <h2 className="text-lg font-bold text-white pt-1">{selectedLead.title_or_role}</h2>
                <div className="text-xs text-slate-400 flex items-center gap-3">
                  <span className="text-slate-200 font-semibold">{selectedLead.company_or_author}</span>
                  <span>• Posted: {selectedLead.posted_at || 'Recent'}</span>
                  <span>• Found: {selectedLead.found_at}</span>
                </div>
              </div>
              <button 
                onClick={() => setSelectedLead(null)}
                className="p-1 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Score Breakdown */}
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Score Breakdown</span>
              <div className="flex flex-wrap gap-1.5">
                {renderChips(selectedLead.score_breakdown)}
              </div>
            </div>

            {/* Description Snippet */}
            <div className="space-y-1.5">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Opportunity Overview</span>
              <p className="text-xs text-slate-300 bg-slate-950/60 p-3 rounded-lg border border-slate-800 leading-relaxed font-sans max-h-44 overflow-y-auto">
                {selectedLead.summary_snippet}
              </p>
            </div>

            {/* Tailored Pitch Hook */}
            {selectedLead.tailored_pitch && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-blue-400 uppercase tracking-wider">
                    {selectedLead.intent_type === 'internship' ? 'Student Cover Letter Hook' : 'Personalized Pitch Hook'}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleCopyPitch(selectedLead.tailored_pitch, 9999)}
                    className="h-7 text-xs gap-1"
                  >
                    {copiedIndex === 9999 ? (
                      <>
                        <Check className="h-3 w-3 text-emerald-400" />
                        <span className="text-emerald-400">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        <span>Copy Pitch</span>
                      </>
                    )}
                  </Button>
                </div>
                <div className="bg-slate-950/80 p-3 rounded-lg border border-blue-500/20 text-xs text-slate-200 italic leading-relaxed">
                  &ldquo;{selectedLead.tailored_pitch}&rdquo;
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-3 pt-3 border-t border-slate-800">
              <a href={selectedLead.quick_action} target="_blank" rel="noreferrer" className="flex-1">
                <Button 
                  variant={selectedLead.intent_type === 'internship' ? 'success' : 'default'}
                  className="w-full gap-2 font-semibold"
                >
                  {selectedLead.intent_type === 'internship' ? (
                    <>
                      <GraduationCap className="h-4 w-4" />
                      Apply on Company Portal
                    </>
                  ) : (
                    <>
                      <Zap className="h-4 w-4" />
                      1-Click Compose Outreach
                    </>
                  )}
                </Button>
              </a>
              <a href={selectedLead.article_link} target="_blank" rel="noreferrer">
                <Button variant="outline" className="gap-1.5">
                  <ExternalLink className="h-4 w-4" />
                  View Source
                </Button>
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950/60 py-6 mt-12 text-center text-xs text-slate-500">
        <p>Startup Lead Tracker &copy; 2026. Built with Python, React, Tailwind CSS & shadcn/ui.</p>
        <p className="mt-1 text-[11px] text-slate-600">Continuously monitoring Hacker News, Reddit, and intern-list.com</p>
      </footer>
    </div>
  );
}
