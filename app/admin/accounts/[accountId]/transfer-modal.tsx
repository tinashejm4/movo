"use client"

import { useEffect, useState, type FormEvent } from "react"
import styles from "./modal.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type AccountOption = { id: number; name: string; number: string; currency: string }

type TransferModalProps = {
  accountId: string
  accountName: string
  currency: string
  onClose: () => void
  onCreated: () => void
}

export function TransferModal({ accountId, accountName, currency, onClose, onCreated }: TransferModalProps) {
  const [accounts, setAccounts] = useState<AccountOption[]>([])
  const [toAccountId, setToAccountId] = useState("")
  const [amount, setAmount] = useState("")
  const [description, setDescription] = useState("")
  const [loadingAccounts, setLoadingAccounts] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) return

    let isMounted = true
    fetch(`${API_BASE}/api/adminportal/accounts/`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then(async (response) => {
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load accounts.")
        if (isMounted) setAccounts(Array.isArray(data?.accounts) ? data.accounts : [])
      })
      .catch((loadError) => {
        if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load accounts.")
      })
      .finally(() => {
        if (isMounted) setLoadingAccounts(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

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

    if (!toAccountId) {
      setError("Select the account to transfer to.")
      return
    }
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
      const response = await fetch(`${API_BASE}/api/adminportal/accounts/create-funds-transfer/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ from_account_id: accountId, to_account_id: toAccountId, amount, description }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to create transfer.")
      onCreated()
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to create transfer.")
      setSubmitting(false)
    }
  }

  const destinations = accounts.filter((account) => String(account.id) !== accountId)

  return (
    <div className={styles.overlay} role="presentation" onClick={() => !submitting && onClose()}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="transfer-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="transfer-title">Transfer funds</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label>
            From
            <input type="text" value={accountName} disabled readOnly />
          </label>
          <label>
            To account
            <select value={toAccountId} onChange={(event) => setToAccountId(event.target.value)} disabled={loadingAccounts}>
              <option value="">{loadingAccounts ? "Loading..." : "Select account"}</option>
              {destinations.map((account) => (
                <option key={account.id} value={account.id}>{account.name} ({account.number}, {account.currency})</option>
              ))}
            </select>
          </label>
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
            <button type="submit" className={styles.primary} disabled={submitting}>{submitting ? "Transferring..." : "Transfer"}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
