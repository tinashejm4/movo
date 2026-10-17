"use client"

import Link from "next/link"
import { useEffect, useState, type FormEvent } from "react"
import { useRouter } from "next/navigation"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type Branch = {
  branch_id: number
  name: string
  address: string
}

type BikerForm = {
  first_name: string
  last_name: string
  username: string
  branch: string
  profile_picture: File | null
  phone_number1: string
  phone_number2: string
  address: string
  next_of_kin_name: string
  next_of_kin_phone_number: string
  next_of_kin_relationship: string
  id_picture: File | null
  id_number: string
  licence_picture: File | null
  licence_number: string
}

const initialForm: BikerForm = {
  first_name: "", last_name: "", username: "", branch: "", profile_picture: null,
  phone_number1: "", phone_number2: "", address: "",
  next_of_kin_name: "", next_of_kin_phone_number: "", next_of_kin_relationship: "",
  id_picture: null, id_number: "", licence_picture: null, licence_number: "",
}

const steps = ["Driver profile", "Contact", "Next of kin", "Documents"]

export default function CreateBikerPage() {
  const router = useRouter()
  const [form, setForm] = useState<BikerForm>(initialForm)
  const [branches, setBranches] = useState<Branch[]>([])
  const [step, setStep] = useState(0)
  const [loadingBranches, setLoadingBranches] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!window.sessionStorage.getItem("movo_access_token")) router.replace("/admin/login")
  }, [router])

  useEffect(() => {
    async function loadBranches() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) return

      try {
        const response = await fetch(`${API_BASE}/api/users/branches/`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load branches.")
        setBranches(Array.isArray(data) ? data : [])
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load branches.")
      } finally {
        setLoadingBranches(false)
      }
    }

    void loadBranches()
  }, [])

  function updateField(field: keyof BikerForm, value: string | File | null) {
    setForm((currentForm) => ({ ...currentForm, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setSubmitting(true)
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) return

    const payload = new FormData()
    for (const [field, value] of Object.entries(form)) {
      if (value instanceof File) payload.append(field, value)
      else if (typeof value === "string") payload.append(field, value)
    }

    try {
      const response = await fetch(`${API_BASE}/api/adminportal/bikers/create/`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        body: payload,
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to create biker.")
      router.push("/admin/bikers")
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to create biker.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/admin/bikers" className={styles.backLink}>Back to bikers</Link>
        <p className={styles.eyebrow}>Movo administration</p>
        <h1>Create biker</h1>
        <p className={styles.intro}>Add a new driver to the delivery team.</p>
      </header>

      <form className={styles.panel} onSubmit={handleSubmit} aria-labelledby="create-biker-heading">
        <div className={styles.formHeader}>
          <h2 id="create-biker-heading">New biker</h2>
          <span>Step {step + 1} of {steps.length}</span>
        </div>
        <nav className={styles.stepNav} aria-label="Creation steps">
          {steps.map((label, index) => <button key={label} type="button" className={index === step ? styles.activeStep : ""} onClick={() => setStep(index)}>{index + 1}. {label}</button>)}
        </nav>

        {error && <p className={styles.error} role="alert">{error}</p>}

        {step === 0 && <section className={styles.section} aria-labelledby="profile-heading">
          <h3 id="profile-heading">Driver profile</h3>
          <div className={styles.fieldGrid}>
            <label>First name<input value={form.first_name} onChange={(event) => updateField("first_name", event.target.value)} required /></label>
            <label>Last name<input value={form.last_name} onChange={(event) => updateField("last_name", event.target.value)} required /></label>
            <label>Username<input value={form.username} onChange={(event) => updateField("username", event.target.value)} autoComplete="username" required /></label>
            <label>Branch<select value={form.branch} onChange={(event) => updateField("branch", event.target.value)} disabled={loadingBranches} required><option value="">{loadingBranches ? "Loading branches..." : "Select branch"}</option>{branches.map((branch) => <option key={branch.branch_id} value={branch.branch_id}>{branch.name} - {branch.address}</option>)}</select></label>
            <label className={styles.fullField}>Profile picture<input type="file" accept="image/*" onChange={(event) => updateField("profile_picture", event.target.files?.[0] ?? null)} /></label>
          </div>
        </section>}

        {step === 1 && <section className={styles.section} aria-labelledby="contact-heading">
          <h3 id="contact-heading">Contact details</h3>
          <div className={styles.fieldGrid}>
            <label>Primary phone number<input type="tel" value={form.phone_number1} onChange={(event) => updateField("phone_number1", event.target.value)} required /></label>
            <label>Secondary phone number<input type="tel" value={form.phone_number2} onChange={(event) => updateField("phone_number2", event.target.value)} /></label>
            <label className={styles.fullField}>Address<textarea value={form.address} onChange={(event) => updateField("address", event.target.value)} rows={4} required /></label>
          </div>
        </section>}

        {step === 2 && <section className={styles.section} aria-labelledby="kin-heading">
          <h3 id="kin-heading">Next of kin</h3>
          <div className={styles.fieldGrid}>
            <label>Full name<input value={form.next_of_kin_name} onChange={(event) => updateField("next_of_kin_name", event.target.value)} required /></label>
            <label>Phone number<input type="tel" value={form.next_of_kin_phone_number} onChange={(event) => updateField("next_of_kin_phone_number", event.target.value)} required /></label>
            <label className={styles.fullField}>Relationship<input value={form.next_of_kin_relationship} onChange={(event) => updateField("next_of_kin_relationship", event.target.value)} required /></label>
          </div>
        </section>}

        {step === 3 && <section className={styles.section} aria-labelledby="documents-heading">
          <h3 id="documents-heading">Driver documents</h3>
          <div className={styles.fieldGrid}>
            <label>ID number<input value={form.id_number} onChange={(event) => updateField("id_number", event.target.value)} required /></label>
            <label>Identification picture<input type="file" accept="image/*" onChange={(event) => updateField("id_picture", event.target.files?.[0] ?? null)} required /></label>
            <label>Licence number<input value={form.licence_number} onChange={(event) => updateField("licence_number", event.target.value)} required /></label>
            <label>Licence picture<input type="file" accept="image/*" onChange={(event) => updateField("licence_picture", event.target.files?.[0] ?? null)} required /></label>
          </div>
        </section>}

        <div className={styles.formActions}>
          <button type="button" className={styles.secondaryButton} onClick={() => setStep((currentStep) => Math.max(0, currentStep - 1))} disabled={step === 0 || submitting}>Back</button>
          {step < steps.length - 1 ? <button type="button" onClick={() => setStep((currentStep) => currentStep + 1)}>Continue</button> : <button type="submit" disabled={submitting}>{submitting ? "Creating..." : "Create biker"}</button>}
        </div>
      </form>
    </main>
  )
}
