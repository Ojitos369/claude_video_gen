// Small inline icon set (stroke icons, 1.75px), sized by the parent font-size
const I = ({ d, children, ...p }) => (
  <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...p}>
    {d ? <path d={d} /> : children}
  </svg>
)
export const Plus = () => <I d="M12 5v14M5 12h14" />
export const Upload = () => <I><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></I>
export const X = () => <I d="M6 6l12 12M18 6L6 18" />
export const Send = () => <I><path d="M5 12h14M13 6l6 6-6 6" /></I>
export const Terminal = () => <I><path d="M4 17l6-5-6-5" /><path d="M12 19h8" /></I>
export const FileText = () => <I><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></I>
export const Pencil = () => <I><path d="M4 20h4L19 9l-4-4L4 16z" /><path d="M13 7l4 4" /></I>
export const Search = () => <I><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></I>
export const Globe = () => <I><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17M12 3.5c2.5 2.6 2.5 14.4 0 17M12 3.5c-2.5 2.6-2.5 14.4 0 17" /></I>
export const List = () => <I d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" />
export const Bot = () => <I><rect x="4" y="8" width="16" height="11" rx="3" /><path d="M12 4v4M9 13h.01M15 13h.01" /></I>
export const Check = () => <I d="M5 12.5l4.5 4.5L19 7" />
export const Alert = () => <I><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17h.01" /></I>
export const Film = () => <I><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 5v14M17 5v14M3 9.5h4M3 14.5h4M17 9.5h4M17 14.5h4" /></I>
export const Stop = () => <I><rect x="6" y="6" width="12" height="12" rx="2" /></I>
export const Trash = () => <I><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" /></I>
export const Download = () => <I><path d="M12 4v12M7 11l5 5 5-5" /><path d="M5 20h14" /></I>
export const Chevron = ({ open }) => <I d="M9 6l6 6-6 6" style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }} />
export const Spark = () => <I d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" />
export const Menu = () => <I d="M4 7h16M4 12h16M4 17h16" />
export const Gear = () => <I><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3M12 18.5v3M4.2 7l2.6 1.5M17.2 15.5l2.6 1.5M4.2 17l2.6-1.5M17.2 8.5l2.6-1.5" /></I>
export const Image = () => <I><rect x="3.5" y="4.5" width="17" height="15" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M20.5 16l-5-5L6 19.5" /></I>
export const Mic = () => <I><rect x="9" y="3.5" width="6" height="11" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" /></I>
export const Key = () => <I><circle cx="8" cy="15" r="3.5" /><path d="M10.5 12.5L20 3M16 7l2.5 2.5M14 9l2 2" /></I>
export const Phone = () => <I><rect x="7" y="2.5" width="10" height="19" rx="2.5" /><path d="M11 18.5h2" /></I>
export const Cpu = () => <I><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" /></I>
export const Sun = () => <I><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></I>
export const Moon = () => <I d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
export const User = () => <I><circle cx="12" cy="8" r="3.5" /><path d="M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5" /></I>

export const toolIcon = (name) => ({
  Bash: <Terminal />, Read: <FileText />, Write: <Pencil />, Edit: <Pencil />, NotebookEdit: <Pencil />,
  Grep: <Search />, Glob: <Search />, WebSearch: <Globe />, WebFetch: <Globe />, TodoWrite: <List />, Agent: <Bot />, Task: <Bot />,
}[name] || <Spark />)
