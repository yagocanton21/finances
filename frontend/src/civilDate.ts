const CIVIL_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})/

export function parseCivilDate(value: string): Date {
  const match = CIVIL_DATE_PATTERN.exec(value)
  if (!match) {
    throw new Error(`Data civil inválida: ${value}`)
  }

  const year = Number(match[1])
  const month = Number(match[2]) - 1
  const day = Number(match[3])
  const date = new Date(year, month, day)

  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month ||
    date.getDate() !== day
  ) {
    throw new Error(`Data civil inválida: ${value}`)
  }

  return date
}

export function todayCivilInput(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
