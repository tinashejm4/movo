"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type Biker = {
  biker_user_id: number
  id: number
  username: string
  name: string
  profile_picture_url: string
}

type BikerDetails = {
  id: number
  name: string
  username: string
  phone_number1: string | null
  phone_number2: string | null
  address: string | null
  started_on: string | null
  next_of_kin: {
    name: string | null
    phone_number: string | null
    relationship: string | null
  } | null
  profile_picture: string | null
  id_picture: string | null
  id_number: string | null
  licence_picture: string | null
  licence_number: string | null
}

function mediaUrl(path: string | null) {
  if (!path || /^https?:\/\//.test(path)) return path
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`
}

export default function AdminBikersPage() {
  const router = useRouter()
  const [bikers, setBikers] = useState<Biker[]>([])
  const [selectedBiker, setSelectedBiker] = useState<Biker | null>(null)
  const [bikerDetails, setBikerDetails] = useState<BikerDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const [error, setError] = useState("")
  const [detailsError, setDetailsError] = useState("")

  useEffect(() => {
    if (!window.sessionStorage.getItem("movo_access_token")) router.replace("/admin/login")
  }, [router])

  useEffect(() => {
    async function loadBikers() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) return

      try {
        const response = await fetch(`${API_BASE}/api/adminportal/bikers/`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load bikers.")
        setBikers(Array.isArray(data) ? data : [])
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load bikers.")
      } finally {
        setLoading(false)
      }
    }

    void loadBikers()
  }, [])

  async function selectBiker(biker: Biker) {
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) return

    setSelectedBiker(biker)
    setBikerDetails(null)
    setDetailsError("")
    setLoadingDetails(true)
    try {
      const response = await fetch(`${API_BASE}/api/adminportal/bikers/${biker.biker_user_id}/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load driver details.")
      setBikerDetails(data)
    } catch (loadError) {
      setDetailsError(loadError instanceof Error ? loadError.message : "Unable to load driver details.")
    } finally {
      setLoadingDetails(false)
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href="/admin" className={styles.backLink}>Back to dashboard</Link>
          <p className={styles.eyebrow}>Movo administration</p>
          <h1>Bikers</h1>
          <p className={styles.intro}>Manage the bikers responsible for deliveries.</p>
        </div>
        <Link href="/admin/bikers/create" className={styles.createButton}>Add new biker</Link>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}
      <section className={styles.workspace} aria-label="Biker management">
        <aside className={styles.listPanel} aria-labelledby="bikers-heading">
          <h2 id="bikers-heading">Bikers</h2>
          {loading && <p className={styles.status}>Loading bikers...</p>}
          {!loading && !error && bikers.length === 0 && <p className={styles.status}>No bikers found.</p>}
          {!loading && bikers.length > 0 && <ul className={styles.bikerList}>
            {bikers.map((biker) => <li key={biker.id}>
              <button
                type="button"
                className={`${styles.bikerButton} ${selectedBiker?.id === biker.id ? styles.selected : ""}`}
                onClick={() => void selectBiker(biker)}
                aria-pressed={selectedBiker?.id === biker.id}
              >
                {biker.profile_picture_url ? <img className={styles.profilePicture} src={biker.profile_picture_url} alt="" /> : <span className={styles.profileFallback} aria-hidden="true">{biker.name.trim().charAt(0).toUpperCase() || "?"}</span>}
                <span>{biker.name || biker.username}</span>
              </button>
            </li>)}
          </ul>}
        </aside>

        <section className={styles.detailsPanel} aria-labelledby="driver-details-heading">
          <h2 id="driver-details-heading">Driver details</h2>
          {!selectedBiker && <p className={styles.status}>Select a biker to view driver details.</p>}
          {loadingDetails && <p className={styles.status}>Loading driver details...</p>}
          {detailsError && <p className={styles.error} role="alert">{detailsError}</p>}
          {bikerDetails && <div className={styles.detailSections}>
            <section className={styles.detailSection} aria-labelledby="identity-heading">
              <h3 id="identity-heading">Identity</h3>
              <div className={styles.driverIdentity}>
                {mediaUrl(bikerDetails.profile_picture) ? <img className={styles.detailProfilePicture} src={mediaUrl(bikerDetails.profile_picture) ?? ""} alt={`${bikerDetails.name}'s profile`} /> : <span className={styles.detailProfileFallback} aria-hidden="true">{bikerDetails.name.trim().charAt(0).toUpperCase() || "?"}</span>}
                <dl><div><dt>Name</dt><dd>{bikerDetails.name}</dd></div><div><dt>Username</dt><dd>{bikerDetails.username}</dd></div><div><dt>Started on</dt><dd>{bikerDetails.started_on ? new Date(bikerDetails.started_on).toLocaleDateString() : "Not provided"}</dd></div></dl>
              </div>
            </section>

            <section className={styles.detailSection} aria-labelledby="contact-heading">
              <h3 id="contact-heading">Contact</h3>
              <dl className={styles.detailList}><div><dt>Primary phone</dt><dd>{bikerDetails.phone_number1 || "Not provided"}</dd></div><div><dt>Secondary phone</dt><dd>{bikerDetails.phone_number2 || "Not provided"}</dd></div><div><dt>Address</dt><dd>{bikerDetails.address || "Not provided"}</dd></div></dl>
            </section>

            <section className={styles.detailSection} aria-labelledby="next-of-kin-heading">
              <h3 id="next-of-kin-heading">Next of kin</h3>
              <dl className={styles.detailList}><div><dt>Name</dt><dd>{bikerDetails.next_of_kin?.name || "Not provided"}</dd></div><div><dt>Phone number</dt><dd>{bikerDetails.next_of_kin?.phone_number || "Not provided"}</dd></div><div><dt>Relationship</dt><dd>{bikerDetails.next_of_kin?.relationship || "Not provided"}</dd></div></dl>
            </section>

            <section className={styles.detailSection} aria-labelledby="documents-heading">
              <h3 id="documents-heading">Documents</h3>
              <dl className={styles.detailList}><div><dt>ID number</dt><dd>{bikerDetails.id_number || "Not provided"}</dd></div><div><dt>Licence number</dt><dd>{bikerDetails.licence_number || "Not provided"}</dd></div></dl>
              <div className={styles.documentImages}>
                {mediaUrl(bikerDetails.id_picture) && <a href={mediaUrl(bikerDetails.id_picture) ?? "#"} target="_blank" rel="noreferrer"><img src={mediaUrl(bikerDetails.id_picture) ?? ""} alt="Identification document" /></a>}
                {mediaUrl(bikerDetails.licence_picture) && <a href={mediaUrl(bikerDetails.licence_picture) ?? "#"} target="_blank" rel="noreferrer"><img src={mediaUrl(bikerDetails.licence_picture) ?? ""} alt="Driver licence" /></a>}
              </div>
            </section>
          </div>}
        </section>
      </section>
    </main>
  )
}
