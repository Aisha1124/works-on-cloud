export type RiskLevel = 'low' | 'medium' | 'high'

/**
 * Formats a money value for display only. Prices and totals are computed in
 * Python as Decimal and arrive as strings like "42.50"; this never does maths.
 */
export function formatSGD(value: string | number): string {
  const text = typeof value === 'number' ? value.toFixed(2) : value.trim()
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(text)
  if (!match) return `S$${text}`
  const [, sign, whole, frac = ''] = match
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}S$${grouped}.${frac.padEnd(2, '0').slice(0, 2)}`
}

export function riskLevel(score: number, mediumAt = 30, highAt = 60): RiskLevel {
  if (score >= highAt) return 'high'
  if (score >= mediumAt) return 'medium'
  return 'low'
}
