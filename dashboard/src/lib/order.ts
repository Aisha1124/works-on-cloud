/** The token from a status link /o/{id}?t={token}, so a page can ask for updates. */
export function tokenOf(statusUrl: string): string {
  try {
    return new URL(statusUrl).searchParams.get('t') ?? ''
  } catch {
    return ''
  }
}
