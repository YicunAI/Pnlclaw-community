/**
 * RSA-OAEP public-key encryption for secret transport.
 *
 * Fetches the backend's ephemeral RSA public key (JWK) and encrypts
 * sensitive values before they are sent over HTTP.  The backend holds
 * the matching private key in memory and decrypts on receipt.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080"

const ENCRYPTED_PREFIX = "enc:"

interface JwkPublicKey {
  kty: string
  alg: string
  use: string
  n: string
  e: string
}

let _cachedKey: CryptoKey | null = null

export async function fetchPublicKey(): Promise<CryptoKey> {
  if (_cachedKey) return _cachedKey

  const res = await fetch(`${API_BASE}/api/v1/settings/public-key`, {
    headers: { "Content-Type": "application/json" },
  })
  if (!res.ok) {
    throw new Error(`Failed to fetch public key: HTTP ${res.status}`)
  }

  const json = await res.json()
  const jwk: JwkPublicKey = json.data ?? json

  _cachedKey = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  )
  return _cachedKey
}

export function clearCachedKey(): void {
  _cachedKey = null
}

export async function encryptSecret(plaintext: string): Promise<string> {
  const key = await fetchPublicKey()
  const encoded = new TextEncoder().encode(plaintext)
  const cipherBuf = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    key,
    encoded,
  )
  const b64 = btoa(String.fromCharCode(...new Uint8Array(cipherBuf)))
  return `${ENCRYPTED_PREFIX}${b64}`
}

export async function encryptIfNonEmpty(value: string): Promise<string> {
  const trimmed = value.trim()
  if (!trimmed) return trimmed
  return encryptSecret(trimmed)
}
