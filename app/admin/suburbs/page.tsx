"use client"

import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent, type PointerEvent } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type City = { id: number; name: string }

type Suburb = {
  id: number
  name: string
  suburb_side: string | null
  is_active: boolean
  x_coord: number | string | null
  y_coord: number | string | null
  aliases?: string[]
}

type ImportResult = {
  message?: string
  city?: string
  suburb?: string
  alias?: string
  created?: number
  updated?: number
  skipped?: number
  total?: number
  error?: string
}

function parseCsv(text: string): Record<string, string>[] {
  const rows = text.trim().split(/\r?\n/).filter(Boolean)
  if (rows.length < 2) return []

  const parseRow = (row: string) => row.split(/,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((value) => value.trim().replace(/^"|"$/g, ""))
  const headers = parseRow(rows[0])
  return rows.slice(1).map((row) => Object.fromEntries(parseRow(row).map((value, index) => [headers[index], value])))
}

async function readAreasFile(file: File) {
  const text = await file.text()
  let rows: Record<string, unknown>[] = []
  try {
    const parsed = JSON.parse(text)
    rows = Array.isArray(parsed) ? parsed : parsed?.suburbs
  } catch {
    rows = parseCsv(text)
  }

  return rows.map((row) => ({
    Areas: row.Areas ?? row.area ?? row.name ?? "",
    x: row.x ?? row.X ?? row.X_coord ?? row.x_coord ?? "",
    y: row.y ?? row.Y ?? row.Y_coord ?? row.y_coord ?? "",
  }))
}

export default function AdminSuburbsPage() {
  const router = useRouter()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const pointsRef = useRef<{ suburb: Suburb; x: number; y: number }[]>([])
  const panRef = useRef({ x: 0, y: 0 })
  const dragRef = useRef({ active: false, moved: false, startX: 0, startY: 0, originX: 0, originY: 0 })
  const [cities, setCities] = useState<City[]>([])
  const [selectedCityId, setSelectedCityId] = useState("")
  const [suburbs, setSuburbs] = useState<Suburb[]>([])
  const [selectedSuburb, setSelectedSuburb] = useState<Suburb | null>(null)
  const [loadingCities, setLoadingCities] = useState(true)
  const [loadingSuburbs, setLoadingSuburbs] = useState(false)
  const [error, setError] = useState("")
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const suburbFileRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [showAliasForm, setShowAliasForm] = useState(false)
  const [aliasName, setAliasName] = useState("")
  const [savingAlias, setSavingAlias] = useState(false)

  useEffect(() => {
    if (!window.sessionStorage.getItem("movo_access_token")) router.replace("/admin/login")
  }, [router])

  useEffect(() => {
    async function loadCities() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) return

      try {
        const response = await fetch(`${API_BASE}/api/adminportal/cities/`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load cities.")
        const nextCities = Array.isArray(data) ? data : []
        setCities(nextCities)
        if (nextCities.length > 0) setSelectedCityId(String(nextCities[0].id))
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load cities.")
      } finally {
        setLoadingCities(false)
      }
    }

    void loadCities()
  }, [])

  useEffect(() => {
    async function loadSuburbs() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken || !selectedCityId) return

      setLoadingSuburbs(true)
      setError("")
      setSelectedSuburb(null)
      try {
        const response = await fetch(`${API_BASE}/api/adminportal/suburbs/${selectedCityId}/`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load suburbs.")
        setSuburbs(Array.isArray(data) ? data : [])
      } catch (loadError) {
        setSuburbs([])
        setError(loadError instanceof Error ? loadError.message : "Unable to load suburbs.")
      } finally {
        setLoadingSuburbs(false)
      }
    }

    void loadSuburbs()
  }, [selectedCityId])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const context = canvas.getContext("2d")
    if (!context) return
    const bounds = canvas.getBoundingClientRect()
    const width = Math.max(1, Math.floor(bounds.width))
    const height = Math.max(1, Math.floor(bounds.height))
    const ratio = window.devicePixelRatio || 1
    canvas.width = width * ratio
    canvas.height = height * ratio
    context.scale(ratio, ratio)
    context.clearRect(0, 0, width, height)
    context.fillStyle = "#fff7ed"
    context.fillRect(0, 0, width, height)

    const coordinates = suburbs.map((suburb) => ({
      suburb,
      x: Number(suburb.x_coord),
      y: Number(suburb.y_coord),
    })).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y))
    pointsRef.current = coordinates.map((point) => ({ ...point, x: 0, y: 0 }))

    if (coordinates.length === 0) return
    const cbdPoint = coordinates.find((point) => point.suburb.name.trim().toLowerCase() === "cbd")
    const originX = cbdPoint?.x ?? (Math.min(...coordinates.map((point) => point.x)) + Math.max(...coordinates.map((point) => point.x))) / 2
    const originY = cbdPoint?.y ?? (Math.min(...coordinates.map((point) => point.y)) + Math.max(...coordinates.map((point) => point.y))) / 2
    const padding = 42
    const maxDistanceX = Math.max(1, ...coordinates.map((point) => Math.abs(point.x - originX)))
    const maxDistanceY = Math.max(1, ...coordinates.map((point) => Math.abs(point.y - originY)))
    const scale = Math.min((width / 2 - padding) / maxDistanceX, (height / 2 - padding) / maxDistanceY) * zoom

    pointsRef.current = coordinates.map((point) => ({
      suburb: point.suburb,
      x: width / 2 + (point.y - originY) * scale + pan.x,
      y: height / 2 - (point.x - originX) * scale + pan.y,
    }))

    const axisX = width / 2 + pan.x
    const axisY = height / 2 + pan.y
    context.strokeStyle = "#ffedd5"
    context.lineWidth = 1
    for (let x = axisX % 40; x <= width; x += 40) {
      context.beginPath()
      context.moveTo(x, 0)
      context.lineTo(x, height)
      context.stroke()
    }
    for (let y = axisY % 40; y <= height; y += 40) {
      context.beginPath()
      context.moveTo(0, y)
      context.lineTo(width, y)
      context.stroke()
    }
    context.strokeStyle = "#fb923c"
    context.lineWidth = 1.5
    context.beginPath()
    context.moveTo(axisX, 0)
    context.lineTo(axisX, height)
    context.moveTo(0, axisY)
    context.lineTo(width, axisY)
    context.stroke()
    for (const point of pointsRef.current) {
      context.beginPath()
      context.arc(point.x, point.y, 8, 0, Math.PI * 2)
      context.fillStyle = point.suburb.is_active ? "#f97316" : "#94a3b8"
      context.fill()
      context.strokeStyle = "#ffffff"
      context.lineWidth = 2
      context.stroke()
      context.fillStyle = "#334155"
      context.font = "600 12px sans-serif"
      context.textAlign = "left"
      context.textBaseline = "middle"
      context.fillText(point.suburb.name, point.x + 14, point.y)
    }
  }, [pan, suburbs, zoom])

  function handleCanvasPointerDown(event: PointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = {
      active: true,
      moved: false,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    }
    setIsPanning(true)
  }

  function handleCanvasPointerMove(event: PointerEvent<HTMLCanvasElement>) {
    if (!dragRef.current.active) return
    const deltaX = event.clientX - dragRef.current.startX
    const deltaY = event.clientY - dragRef.current.startY
    if (Math.hypot(deltaX, deltaY) > 3) dragRef.current.moved = true
    setPan({ x: dragRef.current.originX + deltaX, y: dragRef.current.originY + deltaY })
  }

  function handleCanvasPointerUp(event: PointerEvent<HTMLCanvasElement>) {
    if (!dragRef.current.active) return
    dragRef.current.active = false
    setIsPanning(false)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }

  function handleCanvasClick(event: MouseEvent<HTMLCanvasElement>) {
    if (dragRef.current.moved) {
      dragRef.current.moved = false
      return
    }
    const canvas = canvasRef.current
    if (!canvas) return
    const bounds = canvas.getBoundingClientRect()
    const x = event.clientX - bounds.left
    const y = event.clientY - bounds.top
    const point = pointsRef.current.find((candidate) => Math.hypot(candidate.x - x, candidate.y - y) <= 13)
    setSelectedSuburb(point?.suburb ?? null)
  }

  async function toggleSuburbStatus() {
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken || !selectedSuburb || !selectedCityId) return

    setUpdatingStatus(true)
    setError("")
    try {
      const response = await fetch(`${API_BASE}/api/adminportal/suburbs/${selectedCityId}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          suburb_id: selectedSuburb.id,
          is_active: !selectedSuburb.is_active,
        }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to update suburb status.")

      const updatedSuburb = { ...selectedSuburb, ...data }
      setSelectedSuburb(updatedSuburb)
      setSuburbs((currentSuburbs) => currentSuburbs.map((suburb) => suburb.id === updatedSuburb.id ? updatedSuburb : suburb))
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Unable to update suburb status.")
    } finally {
      setUpdatingStatus(false)
    }
  }

  async function handleSuburbFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ""
    if (!file || !selectedCityId) return

    setImporting(true)
    setError("")
    try {
      const areas = await readAreasFile(file)
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      const response = await fetch(`${API_BASE}/api/adminportal/suburbs/import-areas/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ suburbs: areas, city_id: Number(selectedCityId) }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to import suburbs.")
      setImportResult(data)
      const suburbsResponse = await fetch(`${API_BASE}/api/adminportal/suburbs/${selectedCityId}/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      })
      const refreshedSuburbs = await suburbsResponse.json().catch(() => [])
      if (suburbsResponse.ok && Array.isArray(refreshedSuburbs)) setSuburbs(refreshedSuburbs)
    } catch (importError) {
      setImportResult({ error: importError instanceof Error ? importError.message : "Unable to import suburbs." })
    } finally {
      setImporting(false)
    }
  }

  async function saveAlias() {
    const accessToken = window.sessionStorage.getItem("movo_access_token")
    const trimmedAlias = aliasName.trim()
    if (!accessToken || !selectedSuburb || !trimmedAlias) return

    setSavingAlias(true)
    setError("")
    try {
      const response = await fetch(`${API_BASE}/api/adminportal/suburbs/alias/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ suburb_id: selectedSuburb.id, alias_name: trimmedAlias }),
      })
      const data = await response.json().catch(() => null)
      if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to save suburb alias.")
      setAliasName("")
      setShowAliasForm(false)
      const savedAlias = typeof data?.alias === "string" ? data.alias : trimmedAlias
      const updatedSuburb = {
        ...selectedSuburb,
        aliases: [...(selectedSuburb.aliases ?? []), savedAlias],
      }
      setSelectedSuburb(updatedSuburb)
      setSuburbs((currentSuburbs) => currentSuburbs.map((suburb) => suburb.id === updatedSuburb.id ? updatedSuburb : suburb))
      setImportResult({ suburb: data?.suburb, alias: data?.alias })
    } catch (aliasError) {
      setError(aliasError instanceof Error ? aliasError.message : "Unable to save suburb alias.")
    } finally {
      setSavingAlias(false)
    }
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const handleWheel = (event: globalThis.WheelEvent) => {
      event.preventDefault()
      event.stopPropagation()
      setZoom((currentZoom) => Math.min(24, Math.max(0.75, currentZoom + (event.deltaY < 0 ? 0.25 : -0.25))))
    }

    canvas.addEventListener("wheel", handleWheel, { passive: false })
    return () => canvas.removeEventListener("wheel", handleWheel)
  }, [])

  const selectedCity = cities.find((city) => String(city.id) === selectedCityId)

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href="/admin" className={styles.backLink}>Back to dashboard</Link>
          <p className={styles.eyebrow}>Movo administration</p>
          <h1>Suburbs</h1>
          <p className={styles.intro}>Explore delivery areas by city and inspect each suburb on the map.</p>
        </div>
        <div className={styles.headerControls}>
          <button type="button" className={styles.importButton} onClick={() => suburbFileRef.current?.click()} disabled={importing || !selectedCityId}>{importing ? "Importing..." : "Add suburbs"}</button>
          <input ref={suburbFileRef} className={styles.hiddenInput} type="file" accept=".csv,.json,text/csv,application/json" onChange={handleSuburbFile} />
          <label className={styles.cityPicker} htmlFor="city-select">
            City
            <select id="city-select" value={selectedCityId} onChange={(event) => setSelectedCityId(event.target.value)} disabled={loadingCities || cities.length === 0}>
              {loadingCities && <option>Loading cities...</option>}
              {!loadingCities && cities.length === 0 && <option>No cities found</option>}
              {cities.map((city) => <option key={city.id} value={city.id}>{city.name}</option>)}
            </select>
          </label>
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}
      <section className={styles.workspace}>
        <section className={styles.mapPanel} aria-labelledby="map-heading">
          <div className={styles.panelHeader}>
            <div><h2 id="map-heading">{selectedCity?.name ?? "City map"}</h2><p>{suburbs.length} suburbs</p></div>
            <div className={styles.legend}><span><i className={styles.activeDot} />Active</span><span><i className={styles.disabledDot} />Disabled</span></div>
          </div>
          <div className={styles.mapToolbar} aria-label="Map zoom controls">
            <button type="button" onClick={() => setZoom((currentZoom) => Math.min(24, currentZoom + 0.25))} aria-label="Zoom in">+</button>
            <span>{Math.round(zoom * 100)}%</span>
            <button type="button" onClick={() => setZoom((currentZoom) => Math.max(0.75, currentZoom - 0.25))} aria-label="Zoom out">-</button>
            <button type="button" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} aria-label="Reset zoom">Reset</button>
          </div>
          {loadingSuburbs && <p className={styles.status}>Loading suburbs...</p>}
          {!loadingSuburbs && suburbs.length === 0 && <p className={styles.status}>No suburbs found for this city.</p>}
          <canvas
            ref={canvasRef}
            className={`${styles.canvas} ${isPanning ? styles.canvasPanning : ""}`}
            onClick={handleCanvasClick}
            onPointerDown={handleCanvasPointerDown}
            onPointerMove={handleCanvasPointerMove}
            onPointerUp={handleCanvasPointerUp}
            onPointerCancel={handleCanvasPointerUp}
            aria-label="Suburbs map"
          />
          {!loadingSuburbs && suburbs.length > 0 && <p className={styles.mapHint}>Select a suburb circle to view its details.</p>}
        </section>

        <aside className={styles.detailsPanel} aria-labelledby="details-heading">
          <h2 id="details-heading">Suburb details</h2>
          {!selectedSuburb && <p className={styles.status}>Click a suburb on the map to inspect it.</p>}
          {selectedSuburb && <dl className={styles.details}>
            <div><dt>Name</dt><dd>{selectedSuburb.name}</dd></div>
            <div><dt>Status</dt><dd className={styles.statusControl}><span className={selectedSuburb.is_active ? styles.activeStatus : styles.disabledStatus}>{selectedSuburb.is_active ? "Active" : "Disabled"}</span><button type="button" onClick={toggleSuburbStatus} disabled={updatingStatus}>{updatingStatus ? "Updating..." : selectedSuburb.is_active ? "Deactivate" : "Activate"}</button></dd></div>
            <div><dt>Suburb side</dt><dd>{selectedSuburb.suburb_side || "Not specified"}</dd></div>
            <div><dt>X coordinate</dt><dd>{selectedSuburb.x_coord ?? "Not specified"}</dd></div>
            <div><dt>Y coordinate</dt><dd>{selectedSuburb.y_coord ?? "Not specified"}</dd></div>
            <div><dt>Suburb ID</dt><dd>{selectedSuburb.id}</dd></div>
            <div><dt>Aliases</dt><dd>{selectedSuburb.aliases?.length ? <ul className={styles.aliasList}>{selectedSuburb.aliases.map((alias) => <li key={alias}>{alias}</li>)}</ul> : <span className={styles.muted}>No aliases added.</span>}</dd></div>
            <div className={styles.aliasSection}><dt>Alias</dt><dd>{!showAliasForm && <button type="button" className={styles.aliasButton} onClick={() => setShowAliasForm(true)}>Add alias</button>}{showAliasForm && <div className={styles.aliasForm}><input value={aliasName} onChange={(event) => setAliasName(event.target.value)} placeholder="Enter alias" autoFocus /><div><button type="button" onClick={saveAlias} disabled={savingAlias || !aliasName.trim()}>{savingAlias ? "Saving..." : "Save"}</button><button type="button" onClick={() => { setShowAliasForm(false); setAliasName("") }}>Cancel</button></div></div>}</dd></div>
          </dl>}
        </aside>
      </section>
      {importResult && <div className={styles.modalBackdrop} role="presentation" onClick={() => setImportResult(null)}><section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="import-result-heading" onClick={(event) => event.stopPropagation()}><h2 id="import-result-heading">{importResult.alias ? "Alias added" : "Import result"}</h2>{importResult.error ? <p className={styles.error}>{importResult.error}</p> : importResult.alias ? <dl className={styles.importSummary}><div><dt>Suburb</dt><dd>{importResult.suburb}</dd></div><div><dt>Added alias</dt><dd>{importResult.alias}</dd></div></dl> : <><p className={styles.success}>{importResult.message}</p><dl className={styles.importSummary}><div><dt>City</dt><dd>{importResult.city}</dd></div><div><dt>Created</dt><dd>{importResult.created}</dd></div><div><dt>Updated</dt><dd>{importResult.updated}</dd></div><div><dt>Skipped</dt><dd>{importResult.skipped}</dd></div><div><dt>Total</dt><dd>{importResult.total}</dd></div></dl></>}<button type="button" className={styles.closeButton} onClick={() => setImportResult(null)}>Close</button></section></div>}
    </main>
  )
}
