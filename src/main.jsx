import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import { ActionConfirmationProvider } from './components/ActionConfirmationProvider.jsx'
import { EditGuardProvider } from './components/EditGuardProvider.jsx'
import { NotificationProvider } from './components/NotificationProvider.jsx'
import './styles.css'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <NotificationProvider>
      <ActionConfirmationProvider>
        <EditGuardProvider>
          <App />
        </EditGuardProvider>
      </ActionConfirmationProvider>
    </NotificationProvider>
  </StrictMode>,
)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`, { scope: import.meta.env.BASE_URL, updateViaCache: 'none' }).catch(error => {
      console.warn('Fitfinity service worker registration failed:', error)
    })
  })
}
