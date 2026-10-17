"use client"

import { useEffect, useState, type FormEvent } from "react"
import styles from "./modal.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type AddChargeModalProps = {
  accountId: string
  currency: string
  onClose: () => void
  onCreated: () => void
}

export function AddChargeModal({ accountId, currency, onClose, onCreated }: AddChargeModalProps) {
  const [amount, setAmount] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !submitting) onClose()
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [onClose, submitting])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError("")

    if (!(Number(amount) > 0)) {
      setError("Enter an amount greater than zero.")
      return
    }

    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) {
      setError("Your session has expired. Please log in again.")
      return
    }

    setSubmitting(true)
    try {
      const response = await fetch(`${API_BASE}/api/adminportal/accounts/create-charge/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accountId, amount, description }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to create charge.")
      onCreated()
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to create charge.")
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.overlay} role="presentation" onClick={() => !submitting && onClose()}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="add-charge-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="add-charge-title">Add charge</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label>
            Amount ({currency})
            <input type="number" min="0" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </label>
          <label>
            Description
            <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          {error && <p className={styles.error} role="alert">{error}</p>}
          <div className={styles.footer}>
            <button type="button" onClick={onClose} disabled={submitting}>Cancel</button>
            <button type="submit" className={styles.primary} disabled={submitting}>{submitting ? "Saving..." : "Save charge"}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
