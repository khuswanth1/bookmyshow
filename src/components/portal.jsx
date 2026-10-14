import { NavLink } from 'react-router-dom'
import { clsx } from '../lib/format'

export function PortalShell({ title, links, children }) {
  return (
    <div className="container-x py-6">
      <div className="grid gap-6 lg:grid-cols-[14rem_1fr]">
        <nav aria-label={`${title} sections`} className="card h-fit p-2">
          <p className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-gray-400">{title}</p>
          <ul className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible">
            {links.map(([to, label, Icon, end]) => (
              <li key={to}><NavLink to={to} end={end} className={({ isActive }) => clsx('flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium', isActive ? 'bg-brand/10 text-brand' : 'hover:bg-gray-100')}>
                {Icon && <Icon className="h-4 w-4" aria-hidden="true" />}{label}</NavLink></li>
            ))}
          </ul>
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  )
}

/** Minimal accessible bar chart. data: [{label, value}] */
export function BarChart({ data, format = (v) => v, color = '#f84464', height = 160, title }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  if (!data.length) return <p className="py-8 text-center text-sm text-gray-500">No data for this period yet.</p>
  return (
    <figure>
      {title && <figcaption className="sr-only">{title}</figcaption>}
      <div className="flex items-end gap-1 overflow-x-auto" style={{ height }} role="img" aria-label={title || 'Bar chart'}>
        {data.map((d, i) => (
          <div key={i} className="group relative flex h-full min-w-4 max-w-14 flex-1 flex-col justify-end" title={`${d.label}: ${format(d.value)}`}>
            <div className="w-full rounded-t transition-opacity group-hover:opacity-75" style={{ height: `${Math.max(2, (d.value / max) * 100)}%`, background: color }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-gray-500"><span>{data[0].label}</span><span>{data[data.length - 1].label}</span></div>
      <table className="sr-only"><caption>{title}</caption><tbody>{data.map((d, i) => <tr key={i}><th scope="row">{d.label}</th><td>{format(d.value)}</td></tr>)}</tbody></table>
    </figure>
  )
}

export function DataTable({ columns, rows, empty = 'Nothing here yet.', caption }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-left text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-gray-50 text-xs uppercase text-gray-500"><tr>{columns.map((c) => <th key={c.key || c.header} scope="col" className="whitespace-nowrap px-4 py-3">{c.header}</th>)}</tr></thead>
        <tbody className="divide-y">
          {rows.length === 0 && <tr><td colSpan={columns.length} className="px-4 py-10 text-center text-gray-500">{empty}</td></tr>}
          {rows.map((r, i) => <tr key={r.id ?? i} className="hover:bg-gray-50">{columns.map((c) => <td key={c.key || c.header} className="px-4 py-3 align-top">{c.render ? c.render(r) : r[c.key]}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  )
}
