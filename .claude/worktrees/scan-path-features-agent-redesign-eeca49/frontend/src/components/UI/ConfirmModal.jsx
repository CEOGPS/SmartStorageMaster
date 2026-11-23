import React from 'react';
import './ConfirmModal.css';

export default function ConfirmModal({ visible, title, message, onConfirm, onCancel, confirmLabel = 'Confirm', cancelLabel = 'Cancel', loading = false }) {
  if (!visible) return null;

  return (
    <div className="confirm-modal-backdrop">
      <div className="confirm-modal">
        <h3 className="confirm-title">{title}</h3>
        <p className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button className="btn-cancel" onClick={onCancel} disabled={loading}>{cancelLabel}</button>
          <button className="btn-confirm" onClick={onConfirm} disabled={loading}>{loading ? 'Processing...' : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
