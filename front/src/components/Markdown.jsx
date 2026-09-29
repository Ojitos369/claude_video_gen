import { useMemo } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ gfm: true, breaks: true })

export default function Markdown({ text, className = '' }) {
  const html = useMemo(() => DOMPurify.sanitize(marked.parse(text || '')), [text])
  return <div className={`md ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}
