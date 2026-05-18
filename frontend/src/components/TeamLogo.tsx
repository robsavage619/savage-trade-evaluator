import { teamLogoUrl } from '../lib/format'

type Props = {
  team: string
  size?: number
  className?: string
  title?: string
}

export function TeamLogo({ team, size = 24, className = '', title }: Props) {
  const url = teamLogoUrl(team)
  if (!url) {
    return (
      <span
        className={`grid place-items-center rounded-sm bg-ink-700 text-[10px] font-bold text-ink-300 ${className}`}
        style={{ width: size, height: size }}
      >
        {team}
      </span>
    )
  }
  return (
    <img
      src={url}
      alt={title ?? `${team} logo`}
      title={title ?? team}
      width={size}
      height={size}
      className={`inline-block shrink-0 select-none ${className}`}
      style={{ width: size, height: size }}
      loading="lazy"
    />
  )
}
