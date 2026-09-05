import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { ActionConfirmationProvider } from './components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './components/EditGuardProvider.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ActionConfirmationProvider>
      <EditGuardProvider>
        <App />
      </EditGuardProvider>
    </ActionConfirmationProvider>
  </StrictMode>,
)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(error => {
      console.warn('Fitfinity service worker registration failed:', error)
    })
  })
}
