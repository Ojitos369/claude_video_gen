import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

try { document.documentElement.dataset.theme = localStorage.getItem('vs-theme') || 'dark' } catch { document.documentElement.dataset.theme = 'dark' }

createRoot(document.getElementById('root')).render(<App />)
