"use client"

import { useEffect, useState, type FormEvent } from "react"
import styles from "./modal.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type ExpenseClass = { id: number; name: string }

type AddExpenseModalProps = {
  accountId: string
  currency: string
  onClose: () => void
  onCreated: () => void
}

export function AddExpenseModal({ accountId, currency, onClose, onCreated }: AddExpenseModalProps) {
  const [expenseClasses, setExpenseClasses] = useState<ExpenseClass[]>([])
  const [expenseTypeId, setExpenseTypeId] = useState("")
  const [amount, setAmount] = useState("")
  const [supplier, setSupplier] = useState("")
  const [description, setDescription] = useState("")
  const [image, setImage] = useState<File | null>(null)
  const [loadingClasses, setLoadingClasses] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) return

    let isMounted = true
    fetch(`${API_BASE}/api/adminportal/accounts/expense-classes/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then(async (response) => {
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load expense types.")
        if (isMounted) setExpenseClasses(Array.isArray(data?.expense_classes) ? data.expense_classes : [])
      })
      .catch((loadError) => {
        if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load expense types.")
      })
      .finally(() => {
        if (isMounted) setLoadingClasses(false)
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

    if (!expenseTypeId) {
      setError("Select an expense type.")
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

    const body = new FormData()
    body.append("account_id", accountId)
    body.append("expense_type_id", expenseTypeId)
    body.append("amount", amount)
    body.append("description", description)
    body.append("supplier", supplier)
    if (image) body.append("image", image)

    setSubmitting(true)
    try {
      const response = await fetch(`${API_BASE}/api/adminportal/accounts/create-expense/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body,
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to create expense.")
      onCreated()
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to create expense.")
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.overlay} role="presentation" onClick={() => !submitting && onClose()}>
      <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="add-expense-title" onClick={(event) => event.stopPropagation()}>
        <h2 id="add-expense-title">Add expense</h2>
        <form onSubmit={handleSubmit} className={styles.form}>
          <label>
            Expense type
            <select value={expenseTypeId} onChange={(event) => setExpenseTypeId(event.target.value)} disabled={loadingClasses}>
              <option value="">{loadingClasses ? "Loading..." : "Select type"}</option>
              {expenseClasses.map((expenseClass) => (
                <option key={expenseClass.id} value={expenseClass.id}>{expenseClass.name}</option>
              ))}
            </select>
          </label>
          <label>
            Amount ({currency})
            <input type="number" min="0" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </label>
          <label>
            Supplier
            <input type="text" value={supplier} onChange={(event) => setSupplier(event.target.value)} />
          </label>
          <label>
            Description
            <textarea rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </label>
          <label>
            Receipt image (optional)
            <input type="file" accept="image/*" onChange={(event) => setImage(event.target.files?.[0] ?? null)} />
          </label>
          {error && <p className={styles.error} role="alert">{error}</p>}
          <div className={styles.footer}>
            <button type="button" onClick={onClose} disabled={submitting}>Cancel</button>
            <button type="submit" className={styles.primary} disabled={submitting}>{submitting ? "Saving..." : "Save expense"}</button>
          </div>
        </form>
      </div>
    </div>
  )
}
