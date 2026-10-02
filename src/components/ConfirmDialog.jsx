import ModalPortal from './ModalPortal.jsx'

export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  confirmDisabled = false,
  confirmForm,
  hideConfirm = false,
  onConfirm,
  onCancel,
  className = '',
  onKeyDown,
}) {
  if (!open) return null

  return (
    <ModalPortal>
      <div className="modal-backdrop" role="presentation" onMouseDown={event => {
        if (event.target === event.currentTarget) onCancel?.()
      }}>
        <section className={`modal-card${className ? ` ${className}` : ''}`} role="dialog" aria-modal="true" aria-label={title} onKeyDown={onKeyDown}>
          <div className="modal-head">
            <h2>{title}</h2>
            <button type="button" className="icon-button" aria-label="Close dialog" onClick={onCancel}>×</button>
          </div>
          <div className="modal-body">{children}</div>
          <div className="modal-actions">
            <button type="button" className="secondary-button" onClick={onCancel}>{cancelLabel}</button>
            {!hideConfirm && (
              <button
                type={confirmForm ? 'submit' : 'button'}
                form={confirmForm}
                className={danger ? 'danger-button' : 'primary-button'}
                disabled={confirmDisabled}
                onClick={onConfirm}
              >
                {confirmLabel}
              </button>
            )}
          </div>
        </section>
      </div>
    </ModalPortal>
  )
}
