import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

function App() {
  return (
    <main className="shell">
      <p className="eyebrow">BenchWitness</p>
      <h1>Trace the data. Challenge the score. Prove the recovery.</h1>
      <p>
        The application foundation is ready. Dataset lineage and evidence views arrive in later
        milestones.
      </p>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
